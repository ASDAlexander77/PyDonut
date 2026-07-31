# Work Graphs example, part 1: procedural scene + dispatch-based deferred shading — design

## Goal

Port the non-work-graph half of `Donut-Samples/examples/work_graphs/work_graphs_d3d12.cpp` to
a new top-level `work_graphs.py`: the procedural "dancing crowd" scene (multiple floors, 8
material types, animated spot lights, animated cuboids/spheres) and its standard
dispatch-based deferred shading path (tiled light culling → uber-shader deferred lighting).

This is sub-project 1 of 2 for the full Work Graphs example port (approved after
`work_graphs_prototype.py` proved the D3D12 interop feasible — see
`docs/superpowers/specs/2026-07-31-workgraphs-interop-prototype-design.md`). No ImGui, no
technique toggle, and no work-graph dispatch happen here — this produces a working, complete
`work_graphs.py` that always renders via the plain compute-dispatch path. Sub-project 2 later
extends this same file to add the work-graph broadcasting-launch path plus the
Options/Stats ImGui window that switches between the two.

## Decisions made during brainstorming

- **Almost no new native bindings needed.** The scene's data model
  (`Material`/`Instance`/`Light`/`AnimState`, defined in the C++ sample's `scene.h` and
  mirrored flat in `scene_data.hlsli`) is plain, tightly-packed PODs. Verified the C++
  `Material` struct's union (`PhongParams`/`VelvetParams`/`FlakesParams`/`StanParams`/
  `CheckerParams`) is byte-layout-compatible with the shader's flattened
  `float3 baseColor; uint materialType; float3 param1; float param2; float param3;` by
  design (each union variant's fields land in the same `param1`/`param2`/`param3` byte
  ranges the shader reads). This means the whole scene data model is `struct.pack`-able
  directly from Python, exactly like `bindless_rendering.py` already does for its instance
  data — no new C++ binding class for "the scene" is needed, unlike engine-`SceneGraph`-based
  examples (`deferred_shading.py`, `variable_shading.py`).
- **Pure Python scene/mesh generation, no numpy.** `GeneratePlane`/`GenerateBox`/
  `GenerateSphere` and `PopulateWorld` are ported directly from `scene.cpp`'s algorithms.
  The densest mesh (box, 100×100 subdivisions/face) is ~60K vertices — one-time generation
  cost at startup, well within plain-Python loop performance (no per-vertex native call, just
  arithmetic + one batched `struct.pack` per buffer). Introducing numpy as a new dependency
  (this project currently has none beyond `pybind11`) isn't justified by this cost.
- **RNG determinism, not RNG fidelity.** The C++ sample seeds with `srand(0)` for a
  deterministic *layout*, not because bit-for-bit reproduction with a Python port matters.
  Python's own `random.Random(seed)` (Mersenne Twister) will not produce the same sequence
  as C's `rand()`, but gives the same property that matters here: a fixed, reproducible scene
  layout across runs of the Python port.
- **Kept the original scene density constants as-authored** (3 floors, 500-unit floor size,
  100 box subdivisions, 100/50 sphere sides/slices, 10 materials per type) — this is
  deliberately a stress-test scene per the sample's own README, and sub-project 2 needs the
  same scene to make the work-graph-vs-dispatch comparison meaningful.
- **Shaders compiled at runtime via DXC**, matching `rt_reflections.py`'s convention (not
  CMake/ShaderMake precompilation, which is reserved for donut's own framework shaders).
  `shaders/work_graphs/*.hlsl` are read from disk and compiled via
  `pyd.CompileShader`/`CompileShaderLibrary` at `Init()` time.
- **One new native binding: `PlanarView.SetMatricesLookAt`.** The sample's camera has its eye
  position *and* look-at target independently orbiting the scene at different speeds/radii/
  heights — not reducible to the existing `PlanarView.SetMatricesOrbit` (fixed target at
  origin, yaw/pitch/distance) or `SetMatricesFromCamera` (donut's usual reverse-Z, infinite-far
  convention). This sample explicitly needs a **regular** (non-reverse-Z), **finite**-far-plane
  projection: the shader's sky test is `depth == 1.0`, and the depth buffer's clear value is
  `1.0` — both assume the standard (not reversed) convention where far maps to 1.0. New method:
  `SetMatricesLookAt(posX,posY,posZ, targetX,targetY,targetZ, upX,upY,upZ, aspectRatio,
  fovYRadians, zNear, zFar)`. The orbit math itself (`cosf`/`sinf` position and target curves)
  is computed in Python each frame with plain `math` calls — consistent with the existing
  convention of never exposing vector/matrix types to Python (see `FirstPersonCamera.LookAt`,
  `PlanarView.SetMatricesOrbit`) — and only the resulting 6 floats + up vector cross into C++.
- **No donut `GBufferRenderTargets`.** The sample's own G-buffer is much simpler than donut's
  built-in one (just Depth + one `RGBA16_UINT` texture encoding world-space normal + material
  index, vs. donut's diffuse/specular/normals/emissive/motion-vectors set). Built directly from
  already-bound primitives: `device.createTexture(TextureDesc)` ×2 + `FramebufferFactory`
  (already bound: `__init__(device)`, `.SetRenderTargets([...])`, `.depthTarget`,
  `.GetFramebuffer(view) -> Framebuffer`).
- **No GPU timers, no UI.** The original sample's frame/shading-time timer queries only feed
  the ImGui Options/Stats window, which doesn't exist yet in this sub-project. Window title
  shows basic info via the existing `SetInformativeWindowTitle`, matching every other example.
- **1920×1080 window**, matching the original — this is a deliberately heavy scene and
  sub-project 2 needs the same window size for a fair technique comparison.
- **Runs on both D3D12 and Vulkan.** Nothing in this sub-project is D3D12-specific — the
  work-graph path (D3D12-only) doesn't exist here yet.

## New native bindings (`src/cpp/_pydonut.cpp`)

- `PlanarView.SetMatricesLookAt(posX: float, posY: float, posZ: float, targetX: float,
  targetY: float, targetZ: float, upX: float, upY: float, upZ: float, aspectRatio: float,
  fovYRadians: float, zNear: float, zFar: float) -> None` — builds a look-at view matrix and a
  **regular** (non-reverse-Z) D3D-style perspective projection with the given finite `zFar`,
  reusing the existing internal `lookToD3DStyle`/`perspProjD3DStyle`-equivalent math already
  used by `SetMatricesOrbit`'s projection half (same projection convention; different
  view-matrix construction — explicit look-at instead of yaw/pitch-around-origin).

Exported from `src/pydonut/__init__.py` and documented in `_pydonut.pyi`, matching the
existing pattern for every other `PlanarView` method.

No other new bindings. Reused as-is: `Device.createBuffer`/`createTexture`, `FramebufferFactory`,
`BindingLayoutDesc`/`BindingSetDesc` (structured buffer SRV/UAV, typed buffer UAV, texture SRV/
UAV, push constants), `ComputePipelineDesc`/`GraphicsPipelineDesc`, `InputLayout` (position+
normal vertex attributes), `CommandList.dispatch`/`drawIndexed`/`writeBuffer`/`copyTexture`,
`ShaderFactory`-free runtime compilation (`pyd.CompileShader`/`CompileShaderLibrary`,
`Device.createShader`/`createShaderLibrary`), `CommonRenderPasses.BlitTexture`.

## New HLSL (`shaders/work_graphs/`)

Ported directly from the C++ sample, no logic changes:
- `scene_data.hlsli` — shared structs (`Instance`/`Light`/`Material`/`AnimState`), the
  `SceneConstantBuffer`, `Random`/`NormalizeRandom`/`RotateY` helpers.
- `materials.hlsli` — the 8 `EvaluateMaterial_*` BRDF functions.
- `lighting.hlsli` — `Unproject`, `PointInSpotLight`, `EvaluateSpotLight`, `EvaluateSky`.
- `animation.hlsl` — `CSMainObjects` (object animation state machine: rotate/dance) and
  `CSMainLights` (spot light target orbit).
- `gbuffer_fill.hlsl` — `VSMain`/`PSMain`, per-instance transform from `Instance`+`AnimState`,
  encodes world-normal + material index into the G-buffer.
- `light_culling.hlsl` — `CSMain`, tiled (8×4) light culling into a per-tile culled-lights
  buffer (`c_MaxLightsPerTile = 64`, shared constant between Python buffer sizing and HLSL).
- `deferred_shading.hlsl` — `CSMain`, per-tile uber-shader evaluating all 8 material types
  against culled lights, plus the procedural sky for `depth == 1.0` pixels.

## `work_graphs.py` structure

- `Scene` (plain Python class, not a `pyd`-derived type): `CreateAssets(device, commandList)`
  generates meshes/materials/instances/lights via ported `scene.cpp` algorithms and uploads
  them via `device.createBuffer` + `commandList.writeBuffer`; exposes the same accessors the
  C++ `Scene` class does (`GetMaterialsBuffer()`, `GetWorldObjectsBuffer()`, `GetLightsBuffer()`,
  `GetAnimStateBuffer()`, `GetMeshVertexBuffer(meshType)`, `GetMeshIndexBuffer(meshType)`,
  `GetSceneSize()`, `GetSceneHeight()`).
- `RenderTargets`: Depth (D32) + GBuffer (RGBA16_UINT) textures, `FramebufferFactory`, LDR
  output texture (RGBA8_UNORM, UAV) — recreated on resize, matching every other example's
  render-target lifecycle pattern.
- `WorkGraphsExample(pyd.IRenderPass)`:
  - `Init()`: creates the scene (`Scene().CreateAssets(...)`), the null SRV/UAV placeholder
    buffer+texture (matching the C++ sample's unused-slot fill pattern).
  - `LoadScenePipelines()`: compiles all 4 HLSL files via `pyd.CompileShader`/
    `CompileShaderLibrary`, builds the shared `BindingLayoutDesc` (push constants + volatile
    constant buffer + the SRV/UAV slots `gbuffer_fill.hlsl`/`light_culling.hlsl`/
    `deferred_shading.hlsl`/`animation.hlsl` collectively need), the input layout, the 4
    pipelines (2 compute animation, 1 graphics G-buffer fill, 2 compute light-culling/shading),
    the culled-lights buffer, the per-pass binding sets.
  - `UpdateSceneConstants()`: computes camera position/target via the orbit math (Python
    `math.sin`/`cos`), calls the new `PlanarView.SetMatricesLookAt`, packs the
    `SceneConstantBuffer` (viewProj, viewProjInverse, camPos+sceneTime, camDir,
    viewportSizeXY) via `struct.pack`, writes it via `commandList.writeBuffer`.
  - `Render(framebuffer)`: (re)creates `RenderTargets`+pipelines on resize, animation compute
    passes, G-buffer fill draw loop (per-instance push-constant index, batched by mesh-type
    run like the C++ source), light-culling compute, deferred-shading compute, blit LDR→
    backbuffer via `CommonRenderPasses.BlitTexture`.
  - `Animate()`: advances scene time, sets window title via `SetInformativeWindowTitle`.
- Same CLI/bootstrap boilerplate as every other example (`pyd.log.ConsoleApplicationMode()`,
  `GetGraphicsAPIFromCommandLine`, `-debug` flag, `DeviceCreationParameters` at 1920×1080,
  `DeviceManager` create/run/shutdown).

## Verification

- `uv sync --reinstall-package pydonut` to rebuild the native module after the new
  `PlanarView.SetMatricesLookAt` binding is added.
- Run `work_graphs.py` (and `-vk`) unbuffered under a bounded timeout: confirm it reaches
  "DeviceManager created successfully", renders at least several frames with no exception, and
  visually resembles the original sample's screenshot (multiple floors, moving spot lights,
  animated cuboids/spheres, procedural sky) — this needs a visual check since there's no
  reference pixel output to assert against, same as every other example in this repo.
- Regression check: run `headless.py` once after the rebuild to confirm the new binding didn't
  break anything else.
- No automated test beyond the visual/log-based run, matching every existing example.
