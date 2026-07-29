# Deferred Shading example port — design

## Goal

Port `Donut-Samples/examples/deferred_shading/deferred_shading.cpp` to a new top-level
`deferred_shading.py`, following the same conventions as the four existing examples
(`basic_triangle.py`, `meshlets.py`, `rt_triangle.py`, `bindless_rendering.py`).

The C++ sample renders a single textured, rotating cube lit by one directional light,
using Donut's G-buffer fill pass followed by a compute-shader deferred lighting pass.
Unlike the previous ports, none of the engine types it needs (`GBufferRenderTargets`,
`GBufferFillPass`, `DeferredLightingPass`, `SceneGraph`/`MeshInstance`/`Material`,
lights, `DrawItem`/`PassthroughDrawStrategy`, `RenderView`) are currently exposed by
`_pydonut.cpp`, so this port requires meaningful new binding surface.

## Decisions made during brainstorming

- **Granular bindings** over one opaque C++ helper class: bind the individual engine
  types (`GBufferRenderTargets`, `GBufferFillPass`, `DeferredLightingPass`,
  `SceneGraph`/`SceneGraphNode`/`MeshInstance`/`MeshInfo`/`MeshGeometry`/`BufferGroup`/
  `Material`, `Light`/`DirectionalLight`, `DrawItem`/`PassthroughDrawStrategy`,
  `RenderView`) individually, matching how `deferred_shading.cpp` itself is structured,
  and making these pieces reusable for future examples (shadow mapping, forward+, etc.
  all build on GBuffer/lights).
- No math vector/matrix types (`float3`, `box3`, `affine3`, ...) get bound — consistent
  with the existing convention (see `FirstPersonCamera.LookAt`, which flattens
  `float3` into three float args). Anywhere the C++ code builds a vector/matrix, the
  binding takes flattened floats and does the math on the C++ side.
- Buffer creation (vertex/index/instance) reuses the simpler pattern already
  established in `rt_triangle.py` — `BufferDesc(initialState=ShaderResource,
  keepInitialState=True)` + plain `commandList.writeBuffer(...)` — rather than porting
  the C++ example's manual `beginTrackingBufferState`/`setPermanentBufferState` calls.
  No new `CommandList` bindings needed for this.
- `MaterialConstants`/`InstanceData` (generated shader-side POD structs) are not
  bound as Python-visible types:
  - `InstanceData` (112 bytes: 4×uint32 + two 3×4 float transforms) is packed directly
    with `struct.pack`, the same technique `bindless_rendering.py` already uses for
    push constants.
  - `MaterialConstants` packing is hidden behind a new combinator helper,
    `CreateMaterialConstantBuffer(device, commandList, material) -> Buffer`, mirroring
    the existing `CreateVolatileConstantBufferDesc`/`CreateBindingSetAndLayout`
    precedent of exposing a helper function instead of the raw struct.
- The manual, non-camera view matrix setup (`yawPitchRoll` × 2 + `translation`,
  `perspProjD3DStyle`) becomes one new `PlanarView` method,
  `SetMatricesOrbit(yawRadians, pitchRadians, distance, aspectRatio, fovYRadians,
  zNear, zFar)`. The two chained `yawPitchRoll` calls in the C++ source are
  mathematically equivalent to a single `yawPitchRoll(yaw, pitch, 0)` call (verified:
  `yawPitchRoll(a,0,0) * yawPitchRoll(0,b,0) == yawPitchRoll(a,b,0)` under the
  library's composition order), so one method covers it. This uses a *regular*
  (non-reverse-Z) projection, unlike `SetMatricesFromCamera` — kept as a separate
  method rather than a flag, since reverse-vs-not changes the depth-clear value and
  `GBufferRenderTargets::Init`'s `useReverseProjection` parameter must match.
- No new HLSL/shader files are needed. `GBufferFillPass` and `DeferredLightingPass`
  only consume Donut's precompiled framework shaders, and all of them
  (`gbuffer_ps.bin`, `gbuffer_vs_buffer_loads.bin`, `gbuffer_vs_input_assembler.bin`,
  `deferred_lighting_cs.bin`) already exist under `bin/shaders/framework/{dxbc,dxil,
  spirv}/passes/` for all three backends — confirmed by listing the build output.
- `nvidia-logo.png` (the cube's texture, referenced by the C++ example) is not yet
  present in `PyDonut/media/` and will be copied in from
  `Donut-Samples/media/nvidia-logo.png`.

## New native bindings (`src/cpp/_pydonut.cpp`)

### Render targets & passes
- `GBufferRenderTargets`: `Init(device, size, sampleCount, enableMotionVectors,
  useReverseProjection)`, `Clear(commandList)`, `GetSize()`, read-only texture handles
  (`Depth`, `GBufferDiffuse`, `GBufferSpecular`, `GBufferNormals`, `GBufferEmissive`,
  `MotionVectors`), and `GBufferFramebuffer` (a thin `FramebufferFactory` binding
  exposing just `GetFramebuffer(view)`).
- `GBufferFillPass`: ctor(device, commonPasses), `Init(shaderFactory,
  CreateParameters)`, `ResetBindingCache()`. `CreateParameters` bound as a plain
  default-constructible struct — no fields need setting for this example.
- `GBufferFillPass.Context` (derives `GeometryPassContext`): default-constructible,
  opaque.
- `DeferredLightingPass`: ctor(device, commonPasses), `Init(shaderFactory)`,
  `Render(commandList, view, Inputs)`, `ResetBindingCache()`.
- `DeferredLightingPass.Inputs`: `SetGBuffer(targets)`, `ambientColorTop`/
  `ambientColorBottom` as `(r,g,b)` float tuples, `lights` (accepts the list returned
  by `SceneGraph.GetLights()`), `output` (texture).
- `DrawItem` (POD: `instance`, `mesh`, `geometry`, `material`, `buffers`,
  `distanceToCamera`, `cullMode`) and `PassthroughDrawStrategy.SetData(items)`.
- Free function `RenderView(commandList, view, viewPrev, framebuffer, drawStrategy,
  pass, context, materialEvents=False)`.

### Scene-graph pieces
- `VertexAttribute` enum: `Position`, `TexCoord1`, `Normal`, `Tangent` (only the
  values this example needs).
- `BufferGroup`: `indexBuffer`/`vertexBuffer`/`instanceBuffer` fields,
  `getVertexBufferRange(attr) -> BufferRange` (settable `byteOffset`/`byteSize`).
- `LoadedTexture`: minimal binding, enough to null-check `.texture`.
- `Material`: `name`, `useSpecularGlossModel`, `enableBaseOrDiffuseTexture`,
  `baseOrDiffuseTexture`, `materialConstants`.
- `MeshGeometry`: `material`, `numIndices`, `numVertices`.
- `MeshInfo`: `name`, `buffers`, `totalIndices`, `totalVertices`, `geometries` (list),
  plus `SetObjectSpaceBounds(minX,minY,minZ,maxX,maxY,maxZ)` instead of exposing
  `dm::box3`.
- `MeshInstance`: ctor from `MeshInfo`, `GetMesh()`.
- `SceneGraphNode`: `SetLeaf(leaf)`, `SetName(name)`.
- `SceneGraph`: `SetRootNode(node)`, `AttachLeafNode(parent, leaf)`,
  `Refresh(frameIndex)`, `GetLights()`.
- `Light`/`DirectionalLight`: `SetDirection(x,y,z)`, `SetName(name)`, `angularSize`,
  `irradiance`.
- `TextureCache.LoadTextureFromFile(path, sRGB, commonPasses, commandList) ->
  LoadedTexture`.

### Helper functions
- `CreateMaterialConstantBuffer(device, commandList, material) -> Buffer`.
- `PlanarView.SetMatricesOrbit(yawRadians, pitchRadians, distance, aspectRatio,
  fovYRadians, zNear, zFar) -> None`.

All new bindings get exported from `src/pydonut/__init__.py` (`__all__` +
`from pydonut._pydonut import ...`) and documented in `_pydonut.pyi`, matching the
existing pattern for every other bound type.

## `deferred_shading.py` structure

Mirrors `deferred_shading.cpp` at the Python level, following the same file shape as
`bindless_rendering.py`:

- A `DeferredShading(pyd.IRenderPass)` class (this example has no scene *file* to
  load asynchronously, so it doesn't need `pyd.ApplicationBase` — `pyd.IRenderPass`
  is sufficient, matching `basic_triangle.py`/`meshlets.py`/`rt_triangle.py`).
- `Init()`: builds the shader factory / common passes / binding cache pointed at
  `bin/shaders/framework` (same mount pattern as `rt_triangle.py`/
  `bindless_rendering.py`), constructs `DeferredLightingPass`, `TextureCache`, and a
  `CommandList`, then builds the manual cube scene (vertex/index/instance buffers,
  material + texture load, `MeshInfo`/`MeshGeometry`/`MeshInstance`, `SceneGraph` with
  a `DirectionalLight` sun).
- A small `RenderTargets`-equivalent: the base `GBufferRenderTargets` plus a
  Python-owned `ShadedColor` texture attribute (no C++ subclass needed — the extra
  UAV texture is created directly via the already-bound `Device.createTexture` +
  `TextureDesc`).
- `SetupView()`: uses `PlanarView.SetMatricesOrbit(...)`.
- `Render()`: same sequence as the C++ source — (re)create render targets and
  `GBufferFillPass` on resize, clear G-buffer, build a `DrawItem` for the cube, run it
  through `PassthroughDrawStrategy` + `RenderView`, run `DeferredLightingPass.Render`
  into `ShadedColor`, blit to the backbuffer via `CommonRenderPasses.BlitTexture`.
- `Animate()`: advances rotation, sets the window title.
- Same CLI/bootstrap boilerplate as the other four examples (`pyd.log.
  ConsoleApplicationMode()`, `GetGraphicsAPIFromCommandLine`, `-debug` flag,
  `DeviceManager` create/run/shutdown).

## Assets

Copy `Donut-Samples/media/nvidia-logo.png` → `PyDonut/media/nvidia-logo.png`.

## Verification

- `uv sync` to rebuild the native module with the new bindings.
- `uv run deferred_shading.py` (and `-vk` where relevant) — confirm a lit, rotating,
  textured cube renders with directional sun lighting, no black/corrupt G-buffer or
  lighting artifacts, and the window resizes cleanly (render targets and
  `GBufferFillPass` get recreated).
- No automated test is planned beyond the visual run — matches how the other four
  examples are verified (there's no existing example-level test suite; `uv run
  pytest` covers unrelated unit tests only).
