# Threaded Rendering example port — design

## Goal

Port `Donut-Samples/examples/threaded_rendering/threaded_rendering.cpp` to a new
top-level `threaded_rendering.py`, following the same conventions as the existing
examples — closest in shape to `variable_shading.py` (also an `ApplicationBase`
subclass loading Sponza via `Scene`/`ForwardShadingPass`/`FramebufferFactory`/
`InstancedOpaqueDrawStrategy`/`RenderCompositeView`).

The C++ sample renders the Sponza scene into the 6 faces of a cube texture (one
`ForwardShadingPass` draw per face), each face recorded into its own deferred
command list, optionally in parallel across 6 `taskflow` worker threads, then
composites all 6 faces into a 4×3 window-space grid via a single blit pass. Space
bar toggles threaded vs. sequential recording; the window title reflects the
current mode.

## Decisions made during brainstorming

- **Real GIL release, not a structural-only port.** pydonut currently holds the GIL
  during every native call, so naively spawning `threading.Thread`s around the
  existing bindings would not reproduce the C++ sample's actual point (comparing
  threaded vs. non-threaded recording performance). `py::call_guard<py::
  gil_scoped_release>()` is added to exactly the calls the 6 worker threads make —
  `CommandList.open/close`, the two (now view-scoped) clears, the three barrier
  calls, `ForwardShadingPass.PrepareLights`, and `RenderCompositeView` — nothing
  else. This is scoped narrowly to what this example exercises concurrently, not a
  blanket change across every `CommandList` method.
- **`CubemapView` faces reuse the existing `PlanarView` binding.** Donut's
  `engine::CubemapView` stores its 6 faces as a plain `PlanarView m_FaceViews[6]`
  internally and `GetChildView` returns a pointer into that array. So
  `CubemapView.GetFaceView(face) -> PlanarView` is a thin wrapper (`return_value_
  policy::reference_internal`) rather than a new view type — every existing
  `PlanarView`-accepting binding (`RenderCompositeView`, `FramebufferFactory.
  GetFramebuffer`, the new view-scoped clears) works with it unchanged.
- **`SetTransformFromCamera` instead of exposing `dm::affine3`.** Consistent with
  the existing convention of never binding math vector/matrix types directly
  (`FirstPersonCamera.LookAt` takes flat floats, not `float3`), `CubemapView` gets
  one combinator method that fetches the camera's world-to-view transform on the
  C++ side and forwards it to `SetTransform`, rather than exposing `affine3`
  itself or a raw `FirstPersonCamera.GetWorldToViewMatrix()`.
- **Sequential warm-up frame before the first threaded frame (see "Known upstream
  hazard" below).** `FramebufferFactory.GetFramebuffer` and `ForwardShadingPass`'s
  internal pipeline/binding-set caches are lazily-populated `std::unordered_map`s.
  The original C++ sample never warms them before spawning threads, so its very
  first frame races 6 threads inserting into the same maps concurrently —
  previously masked in a naive Python port by the GIL, but a real hazard once the
  GIL is actually released (which this design does, per the choice above). `Init()`
  renders all 6 faces once, sequentially, before the thread pool is ever used, so
  every cache entry already exists by the time real concurrent frames begin — only
  reads happen concurrently after that. This is a deliberate, narrow deviation from
  1:1 fidelity (an extra startup frame), not a change to vendored engine code.
- **`concurrent.futures.ThreadPoolExecutor(max_workers=6)`**, created once in
  `Init()` and reused every frame — mirrors `tf::Executor` being a long-lived
  member rather than recreated per frame. `RenderCubeFace(face)` is submitted as a
  plain closure; `concurrent.futures.wait(futures)` followed by `.result()` on each
  future (not just `.wait()`) so a face-render exception surfaces on the main
  thread instead of being silently swallowed.
- **No new HLSL.** Like `deferred_shading.py`/`variable_shading.py`, this only
  consumes Donut's precompiled framework shaders — `ForwardShadingPass`'s shaders
  (`forward_ps.bin`, `forward_vs_*.bin`) already exist under
  `bin/shaders/framework/{dxbc,dxil,spirv}/passes/`, confirmed already in use by
  `variable_shading.py`.
- **No new assets.** Sponza (`media/glTF-Sample-Assets/Models/Sponza/glTF/
  Sponza.gltf`) is already vendored from the `variable_shading.py`/
  `bindless_rendering.py` ports.

### Known upstream hazard (documented, not "fixed")

`ForwardShadingPass`'s `m_Pipelines`/`m_ShadingBindingSets`/`m_InputBindingSets`
caches use double-checked locking around pipeline *creation*, but the
`std::unordered_map::operator[]` insertion of a *new key* happens before the lock
is taken — technically racy for concurrent first-time insertion of different keys,
independent of Python. This is present in NVIDIA's original C++ sample as shipped;
the warm-up frame above sidesteps it for this port (all keys exist before threads
ever run concurrently) without touching `extern/donut` engine internals, which are
out of scope for an example port.

## New native bindings (`src/cpp/_pydonut.cpp`)

### Views
- `CubemapView`: `SetTransformFromCamera(camera: FirstPersonCamera, zNear: float,
  cullDistance: float, useReverseInfiniteProjections: bool = True) -> None`,
  `SetArrayViewports(resolution: int, firstArraySlice: int) -> None`,
  `UpdateCache() -> None`, `GetFaceView(face: int) -> PlanarView`.

### Command lists
- `CommandListParameters`: `__init__()`, `setEnableImmediateExecution(value: bool)
  -> CommandListParameters` (fluent, matching nvrhi's own builder style; only this
  one field is bound — nothing else in `CommandListParameters` is used by this
  example).
- `Device.createCommandList(params: CommandListParameters = CommandListParameters())
  -> CommandList` — new default-valued overload of the existing no-arg method.
- `Device.executeCommandLists(commandLists: list[CommandList], executionQueue:
  CommandQueue = CommandQueue.Graphics) -> int` — batched submission (new; the
  existing `executeCommandList` singular method is unchanged).
- `CommandList.setEnableAutomaticBarriers(enable: bool) -> None`,
  `setResourceStatesForFramebuffer(framebuffer: Framebuffer) -> None`,
  `commitBarriers() -> None`.
- `CommandList.clearTextureFloat`/`clearDepthStencilTexture` gain an optional
  trailing `view: Optional[PlanarView] = None` parameter; when given, the clear is
  scoped to `view.GetSubresources()` instead of the whole texture. Existing 2-/5-arg
  call sites (every other example) are unaffected — this is a new overload, not a
  signature change.

### Blit
- `BlitParameters`: `targetFramebuffer: Framebuffer`, `targetViewport: Viewport`,
  `sourceTexture: Texture`, `sourceArraySlice: int = 0` (only the fields this
  example uses; other upstream `BlitParameters` fields like `sourceBox` stay
  unbound, matching the existing "intentionally left unbound" convention used for
  `TemporalAntiAliasingCreateParameters.historyClampRelax`).
- `CommonRenderPasses.BlitTexture` gains an overload accepting `(commandList,
  params: BlitParameters, bindingCache: Optional[BindingCache] = None)` alongside
  the existing simple 3-/4-arg overload.

### GIL release
`py::call_guard<py::gil_scoped_release>()` added to: `CommandList.open`,
`CommandList.close`, both view-scoped clears, `CommandList.
setEnableAutomaticBarriers`, `CommandList.setResourceStatesForFramebuffer`,
`CommandList.commitBarriers`, `ForwardShadingPass.PrepareLights`,
`RenderCompositeView`. No other bindings change.

All new bindings get exported from `src/pydonut/__init__.py` (`__all__` + `from
pydonut._pydonut import ...`) and documented in `_pydonut.pyi`, matching the
existing pattern for every other bound type.

## `threaded_rendering.py` structure

- `ThreadedRendering(pyd.ApplicationBase)`, matching `variable_shading.py`'s shape:
  `LoadScene`/`SceneLoaded` overrides, `FirstPersonCamera`, `InstancedOpaqueDraw
  Strategy`, `ForwardShadingPass`.
- `Init()`: standard shader-factory/common-passes/binding-cache/texture-cache setup
  (framework shaders from `bin/shaders/framework`, same mount pattern as
  `variable_shading.py`); loads Sponza via `BeginLoadingScene`; creates the shared
  1024×1024×6 color (`SRGBA8_UNORM`) + depth (`D32`) cube textures and their
  `FramebufferFactory`; creates the composite command list plus 6 deferred face
  command lists (`CommandListParameters().setEnableImmediateExecution(False)`);
  creates the `ThreadPoolExecutor`; creates `CubemapView` and calls
  `SetArrayViewports(1024, 0)`; runs the sequential warm-up frame (all 6
  `RenderCubeFace` calls, once, before the pool is ever touched).
- `KeyboardUpdate`: forwards to camera; Space toggles `self.useThreads`.
- `Animate`: advances camera, sets window title with the
  `"(With threads)"`/`"(No threads)"` suffix.
- `RenderCubeFace(face)`: opens that face's command list, view-scoped clears,
  `PrepareLights`, manual barrier sequence, `RenderCompositeView`, close — identical
  code whether called from a pool thread or the main thread.
- `Render(framebuffer)`: rebuilds the `CubemapView` transform from the camera;
  dispatches the 6 faces (pool-submitted + `wait()` + `.result()` each, or
  sequential, depending on `self.useThreads`); opens the composite command list,
  blits each face into its `faceLayout` tile via the new `BlitParameters` overload,
  closes it; submits all 7 command lists in one `executeCommandLists` call.
- Same CLI/bootstrap boilerplate as the other examples (`pyd.log.
  ConsoleApplicationMode()`, `GetGraphicsAPIFromCommandLine`, D3D11-unsupported
  guard with `pyd.log.fatal` + exit, `-debug` flag, `DeviceCreationParameters`
  sized 1024×768, `DeviceManager` create/run/shutdown).

## Verification

- `uv sync --reinstall-package pydonut` to rebuild the native module after each
  round of binding changes.
- Run `threaded_rendering.py` unbuffered under a bounded `timeout`, capturing
  stdout, confirming it reaches "DeviceManager created successfully" and renders at
  least one frame with no exception/traceback — once with the warm-up path only
  (startup), and once forcing `self.useThreads = False` at construction to verify
  the sequential path independently of the threaded path (the Space-bar toggle
  itself just switches which of these two already-verified paths runs per frame,
  so it isn't separately scripted).
- Regression check: after the native rebuild, run `basic_triangle.py` once to
  confirm the new bindings and GIL-release changes didn't break existing examples.
- No automated test suite beyond the visual/log-based run — matches how every
  other example in this repo is verified.
