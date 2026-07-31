# Work Graphs Example Part 1: Scene + Dispatch Shading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a working `work_graphs.py` that renders the procedural "dancing crowd" scene from `Donut-Samples/examples/work_graphs/` via the standard dispatch-based deferred shading path (tiled light culling → uber-shader shading) — no work graphs yet (that's a separate later plan), no ImGui.

**Architecture:** A plain-Python `Scene` class generates meshes/materials/instances/lights (ported from `scene.cpp`'s C++ algorithms) and uploads them via existing `pydonut` buffer bindings. Four HLSL files (animation, G-buffer fill, light culling, deferred shading) are ported byte-for-byte from the C++ sample and compiled at runtime via DXC, matching `rt_reflections.py`'s convention. Two new native bindings on `PlanarView` supply what's missing: `SetMatricesLookAt` (the camera's regular, non-reverse-Z, explicit look-at projection the sample's sky/depth logic depends on) and `GetViewProjMatrixBytes` (the raw viewProj/viewProjInverse matrices this sample's own `SceneConstantBuffer` layout needs, built from `PlanarView`'s already-existing `GetViewProjectionMatrix`/`GetInverseViewProjectionMatrix`).

**Tech Stack:** pybind11 (`_pydonut.cpp`), nvrhi compute/graphics pipelines, DXC runtime shader compilation (`pyd.CompileShader`/`CompileShaderLibrary`), plain Python (`struct`, `random`, `math` — no numpy).

## Global Constraints

- No donut `GBufferRenderTargets`/`SceneGraph` — this sample's G-buffer and scene model are
  both bespoke and simpler than donut's built-in engine types; build them from already-bound
  primitives (`device.createTexture`, `FramebufferFactory`, plain buffers).
- Shaders compile at runtime via `pyd.CompileShader`/`CompileShaderLibrary` (DXC), not
  CMake/ShaderMake precompilation — matches `rt_reflections.py`.
- No vector/matrix types cross into Python — every new binding takes flat floats, matching
  the existing convention (`FirstPersonCamera.LookAt`, `PlanarView.SetMatricesOrbit`).
- Scene density constants kept as-authored in the C++ sample (3 floors, 500-unit floor size,
  100 box subdivisions, 100/50 sphere sides/slices, 10 materials per type).
- RNG determinism (a fixed, reproducible scene layout via a seeded `random.Random`), not RNG
  fidelity with the C++ `rand()`/`srand(0)` sequence — a different but equally deterministic
  PRNG is expected and fine.
- Runs on both D3D12 and Vulkan — nothing in this plan is D3D12-specific.
- Reference design: `docs/superpowers/specs/2026-07-31-work-graphs-scene-dispatch-design.md`.
- Reference source (read-only, for comparison during review — do not modify):
  `E:\Gits\Donut-Samples\examples\work_graphs\` (`work_graphs_d3d12.cpp`, `scene.cpp`,
  `scene.h`, `scene_data.hlsli`, `materials.hlsli`, `lighting.hlsli`, `animation.hlsl`,
  `gbuffer_fill.hlsl`, `light_culling.hlsl`, `deferred_shading.hlsl`).

---

## Task 1: `PlanarView.SetMatricesLookAt` + `GetViewProjMatrixBytes` native bindings

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (add right after the existing `planarView.def("SetMatricesOrbit", ...)` binding)
- Modify: `src/pydonut/_pydonut.pyi` (add stubs after `SetMatricesOrbit`'s stub)

**Interfaces:**
- Produces: `PlanarView.SetMatricesLookAt(posX, posY, posZ, targetX, targetY, targetZ, upX, upY, upZ, aspectRatio, fovYRadians, zNear, zFar) -> None` and `PlanarView.GetViewProjMatrixBytes() -> bytes` (128 bytes: `viewProj` float4x4 then `viewProjInverse` float4x4, both row-major as donut's `float4x4` stores them — built from the already-existing `PlanarView::GetViewProjectionMatrix()`/`GetInverseViewProjectionMatrix()` virtuals declared in `donut/engine/View.h:77-78`, not new math). Tasks 4/5 consume `SetMatricesLookAt` every frame to point the camera at the orbiting crowd scene, and `GetViewProjMatrixBytes` to pack `work_graphs.py`'s own `SceneConstantBuffer` (a different byte layout than donut's `PlanarViewConstants`/`FillPlanarViewConstants`).

- [ ] **Step 1: Add the C++ binding**

In `src/cpp/_pydonut.cpp`, find:
```cpp
    planarView.def("SetMatricesOrbit", [](donut::engine::PlanarView &self, float yawRadians, float pitchRadians, float distance,
            float aspectRatio, float fovYRadians, float zNear, float zFar) {
        donut::math::affine3 viewMatrix = donut::math::yawPitchRoll(yawRadians, 0.f, 0.f)
            * donut::math::yawPitchRoll(0.f, pitchRadians, 0.f)
            * donut::math::translation(donut::math::float3(0.f, 0.f, distance));
        donut::math::float4x4 projection = donut::math::perspProjD3DStyle(fovYRadians, aspectRatio, zNear, zFar);
        self.SetMatrices(viewMatrix, projection);
    }, py::arg("yawRadians"), py::arg("pitchRadians"), py::arg("distance"), py::arg("aspectRatio"),
       py::arg("fovYRadians"), py::arg("zNear"), py::arg("zFar"));
```

Add immediately after it:
```cpp
    // Explicit look-at, regular (non-reverse-Z) D3D-style perspective, for subjects whose eye
    // AND target both move independently (unlike SetMatricesOrbit's fixed-target-at-origin
    // yaw/pitch/distance parameterization -- see work_graphs.py, whose camera orbits both its
    // position and its look-at target on separate paths). The view matrix is built directly
    // (basis vectors from cross products, exactly the classic D3D "look-to" construction) and
    // packed into affine3's row-vector layout: m_linear's rows are (x.x,y.x,z.x), (x.y,y.y,z.y),
    // (x.z,y.z,z.z) -- the transpose of the natural [x;y;z] row layout -- and m_translation is
    // (dot(x,-eye), dot(y,-eye), dot(z,-eye)), matching how PlanarView::transformPoint applies
    // v*m_linear+m_translation in the same row-vector convention HLSL's mul(vec,matrix) uses.
    planarView.def("SetMatricesLookAt", [](donut::engine::PlanarView &self,
            float posX, float posY, float posZ, float targetX, float targetY, float targetZ,
            float upX, float upY, float upZ, float aspectRatio, float fovYRadians, float zNear, float zFar) {
        using namespace donut::math;
        const float3 eye(posX, posY, posZ);
        const float3 target(targetX, targetY, targetZ);
        const float3 up(upX, upY, upZ);

        const float3 z = normalize(target - eye);
        const float3 x = normalize(cross(up, z));
        const float3 y = cross(z, x);
        const float3 negEye = -eye;

        const affine3 viewMatrix(
            float3(x.x, y.x, z.x),
            float3(x.y, y.y, z.y),
            float3(x.z, y.z, z.z),
            float3(dot(x, negEye), dot(y, negEye), dot(z, negEye)));
        const float4x4 projection = perspProjD3DStyle(fovYRadians, aspectRatio, zNear, zFar);
        self.SetMatrices(viewMatrix, projection);
    }, py::arg("posX"), py::arg("posY"), py::arg("posZ"), py::arg("targetX"), py::arg("targetY"), py::arg("targetZ"),
       py::arg("upX"), py::arg("upY"), py::arg("upZ"), py::arg("aspectRatio"), py::arg("fovYRadians"),
       py::arg("zNear"), py::arg("zFar"));

    // Raw bytes of viewProj and its inverse, in work_graphs.py's own SceneConstantBuffer layout
    // (NOT donut's PlanarViewConstants layout that FillPlanarViewConstants above returns) --
    // GetViewProjectionMatrix/GetInverseViewProjectionMatrix already exist on PlanarView
    // (donut/engine/View.h:77-78), this just exposes them as one 128-byte blob.
    planarView.def("GetViewProjMatrixBytes", [](const donut::engine::PlanarView &self) {
        struct { donut::math::float4x4 viewProj, viewProjInverse; } out {
            self.GetViewProjectionMatrix(),
            self.GetInverseViewProjectionMatrix()
        };
        return py::bytes(reinterpret_cast<const char*>(&out), sizeof(out));
    });
```

Separately (not adjacent in the file — these go alongside the *existing* `StructuredBuffer_SRV`/
`TypedBuffer_UAV` bindings, found via the two greps below), add the missing UAV counterpart to
`StructuredBuffer_SRV`. `nvrhi::BindingLayoutItem::StructuredBuffer_UAV` and
`nvrhi::BindingSetItem::StructuredBuffer_UAV(slot, buffer, format=UNKNOWN, range=EntireBuffer)`
already exist natively in nvrhi (`extern/donut/nvrhi/include/nvrhi/nvrhi.h:1947,2275`) — only
the Python binding is missing. `work_graphs.py` needs this for `u_AnimStateData`/`u_LightData`/
`u_CulledLightsDataRW`, which are all `RWStructuredBuffer<T>` of a multi-field struct or a
struct-strided scalar — not expressible via the already-bound `TypedBuffer_UAV` (which only
covers single-format resources like `RWBuffer<uint>`, not `RWStructuredBuffer<AnimState>`).

Find (around `src/cpp/_pydonut.cpp:1074`):
```cpp
        .def_static("TypedBuffer_UAV", &nvrhi::BindingLayoutItem::TypedBuffer_UAV, py::arg("slot"))
```
Add immediately after it:
```cpp
        .def_static("StructuredBuffer_UAV", &nvrhi::BindingLayoutItem::StructuredBuffer_UAV, py::arg("slot"))
```

Find (around `src/cpp/_pydonut.cpp:1140-1142`):
```cpp
        .def_static("TypedBuffer_UAV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::TypedBuffer_UAV(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
```
Add immediately after it (matching the same lambda-wrapping style used for the other
`BindingSetItem` factories that take a buffer):
```cpp
        .def_static("StructuredBuffer_UAV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::StructuredBuffer_UAV(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
```

Add both corresponding `.pyi` stubs in Step 2 below, next to the existing
`StructuredBuffer_SRV`/`TypedBuffer_UAV` stubs in `BindingLayoutItem` and `BindingSetItem`:
```python
    @staticmethod
    def StructuredBuffer_UAV(slot: int) -> BindingLayoutItem: ...
```
```python
    @staticmethod
    def StructuredBuffer_UAV(slot: int, buffer: Buffer) -> BindingSetItem: ...
```

- [ ] **Step 2: Add the `.pyi` stubs**

In `src/pydonut/_pydonut.pyi`, find the `SetMatricesOrbit` stub (right after `SetMatricesFromCamera`'s stub, inside `class PlanarView`) and add immediately after it:
```python
    # Explicit look-at + regular (non-reverse-Z), finite-far D3D-style perspective, for
    # subjects whose eye AND look-at target both move independently (see work_graphs.py).
    def SetMatricesLookAt(
        self: PlanarView,
        posX: float, posY: float, posZ: float,
        targetX: float, targetY: float, targetZ: float,
        upX: float, upY: float, upZ: float,
        aspectRatio: float, fovYRadians: float, zNear: float, zFar: float,
    ) -> None: ...
    # 128 raw bytes: viewProj (float4x4, 64 bytes) followed by viewProjInverse (float4x4, 64
    # bytes), both row-major. work_graphs.py's own SceneConstantBuffer layout, not donut's
    # PlanarViewConstants (see FillPlanarViewConstants above).
    def GetViewProjMatrixBytes(self: PlanarView) -> bytes: ...
```

- [ ] **Step 3: Rebuild**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds.

- [ ] **Step 4: Verify with a standalone sanity check**

Run:
```
uv run python -c "from src import pydonut as pyd; v = pyd.PlanarView(); v.SetMatricesLookAt(0,10,-20, 0,0,0, 0,1,0, 16/9, 0.9, 0.5, 100.0); v.SetViewport(pyd.Viewport(0,1920,0,1080,0,1)); v.UpdateCache(); print('OK', len(v.FillPlanarViewConstants()), len(v.GetViewProjMatrixBytes()))"
```
Expected: prints `OK <n> 128` with no exception — `GetViewProjMatrixBytes` must always be exactly
128 bytes (two 64-byte `float4x4`s); `<n>` (the unrelated `PlanarViewConstants` size) isn't
asserted here. Whether the *matrices themselves* are numerically correct is proven later, in
Task 5's real render loop, via visual inspection.

- [ ] **Step 5: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi
git commit -m "Add PlanarView.SetMatricesLookAt for independently-orbiting eye/target cameras"
```

---

## Task 2: Port the 4 HLSL shader files + 3 shared includes

Byte-for-byte ports from the C++ sample — no logic changes, since the Python-side binding
layout (Task 4) is built to match these files' existing register assignments exactly.

**Files:**
- Create: `shaders/work_graphs/scene_data.hlsli`
- Create: `shaders/work_graphs/materials.hlsli`
- Create: `shaders/work_graphs/lighting.hlsli`
- Create: `shaders/work_graphs/animation.hlsl`
- Create: `shaders/work_graphs/gbuffer_fill.hlsl`
- Create: `shaders/work_graphs/light_culling.hlsl`
- Create: `shaders/work_graphs/deferred_shading.hlsl`

**Interfaces:**
- Produces: 7 HLSL source files with entry points `CSMainObjects`/`CSMainLights`
  (`animation.hlsl`), `VSMain`/`PSMain` (`gbuffer_fill.hlsl`), `CSMain` (`light_culling.hlsl`
  and `deferred_shading.hlsl`, distinct files). Task 4 consumes these entry point names when
  compiling shaders and building pipelines.

- [ ] **Step 1: Copy the 7 files byte-for-byte from the reference C++ sample**

```bash
mkdir -p shaders/work_graphs
cp "E:/Gits/Donut-Samples/examples/work_graphs/scene_data.hlsli"     shaders/work_graphs/scene_data.hlsli
cp "E:/Gits/Donut-Samples/examples/work_graphs/materials.hlsli"      shaders/work_graphs/materials.hlsli
cp "E:/Gits/Donut-Samples/examples/work_graphs/lighting.hlsli"       shaders/work_graphs/lighting.hlsli
cp "E:/Gits/Donut-Samples/examples/work_graphs/animation.hlsl"       shaders/work_graphs/animation.hlsl
cp "E:/Gits/Donut-Samples/examples/work_graphs/gbuffer_fill.hlsl"    shaders/work_graphs/gbuffer_fill.hlsl
cp "E:/Gits/Donut-Samples/examples/work_graphs/light_culling.hlsl"   shaders/work_graphs/light_culling.hlsl
cp "E:/Gits/Donut-Samples/examples/work_graphs/deferred_shading.hlsl" shaders/work_graphs/deferred_shading.hlsl
```

- [ ] **Step 2: Verify each file is an exact copy**

```bash
diff "E:/Gits/Donut-Samples/examples/work_graphs/scene_data.hlsli"      shaders/work_graphs/scene_data.hlsli
diff "E:/Gits/Donut-Samples/examples/work_graphs/materials.hlsli"       shaders/work_graphs/materials.hlsli
diff "E:/Gits/Donut-Samples/examples/work_graphs/lighting.hlsli"        shaders/work_graphs/lighting.hlsli
diff "E:/Gits/Donut-Samples/examples/work_graphs/animation.hlsl"        shaders/work_graphs/animation.hlsl
diff "E:/Gits/Donut-Samples/examples/work_graphs/gbuffer_fill.hlsl"     shaders/work_graphs/gbuffer_fill.hlsl
diff "E:/Gits/Donut-Samples/examples/work_graphs/light_culling.hlsl"    shaders/work_graphs/light_culling.hlsl
diff "E:/Gits/Donut-Samples/examples/work_graphs/deferred_shading.hlsl" shaders/work_graphs/deferred_shading.hlsl
```
Expected: no output from any `diff` (all 7 identical).

- [ ] **Step 3: Verify each compiles via the existing DXC bindings**

```bash
uv run python -c "
from src import pydonut as pyd
from pathlib import Path
api = pyd.GraphicsAPI.D3D12
d = Path('shaders/work_graphs')
inc = [str(d)]
anim = pyd.CompileShaderLibrary((d/'animation.hlsl').read_text(), api, sourceName='animation.hlsl', includePaths=inc) if False else None
a1 = pyd.CompileShader((d/'animation.hlsl').read_text(), 'CSMainObjects', pyd.ShaderType.Compute, api, sourceName='animation.hlsl', includePaths=inc)
a2 = pyd.CompileShader((d/'animation.hlsl').read_text(), 'CSMainLights', pyd.ShaderType.Compute, api, sourceName='animation.hlsl', includePaths=inc)
gvs = pyd.CompileShader((d/'gbuffer_fill.hlsl').read_text(), 'VSMain', pyd.ShaderType.Vertex, api, sourceName='gbuffer_fill.hlsl', includePaths=inc)
gps = pyd.CompileShader((d/'gbuffer_fill.hlsl').read_text(), 'PSMain', pyd.ShaderType.Pixel, api, sourceName='gbuffer_fill.hlsl', includePaths=inc)
lc = pyd.CompileShader((d/'light_culling.hlsl').read_text(), 'CSMain', pyd.ShaderType.Compute, api, sourceName='light_culling.hlsl', includePaths=inc)
ds = pyd.CompileShader((d/'deferred_shading.hlsl').read_text(), 'CSMain', pyd.ShaderType.Compute, api, sourceName='deferred_shading.hlsl', includePaths=inc)
for name, bc in [('CSMainObjects',a1),('CSMainLights',a2),('VSMain',gvs),('PSMain',gps),('light_culling.CSMain',lc),('deferred_shading.CSMain',ds)]:
    assert len(bc) > 0, name
print('OK all 6 entry points compiled')
"
```
Expected: prints `OK all 6 entry points compiled`, no exception. (`pyd.CompileShader` needs an
`includePaths` argument pointing at `shaders/work_graphs` so the `#include "scene_data.hlsli"`
etc. directives in the copied files resolve — pass `includePaths=[str(d)]` as shown.)

- [ ] **Step 4: Commit**

```bash
git add shaders/work_graphs/
git commit -m "Port work_graphs example HLSL shaders (animation, gbuffer fill, light culling, deferred shading)"
```

---

## Task 3: `Scene` class — procedural mesh/material/instance/light generation

Pure-Python port of `scene.cpp`'s `GeneratePlane`/`GenerateBox`/`GenerateSphere` and
`PopulateWorld`, plus GPU buffer upload matching `Scene::CreateAssets`.

**Files:**
- Create: `work_graphs.py` (this task creates the file with only the `Scene` class in it;
  Tasks 4-5 extend the same file)

**Interfaces:**
- Consumes: `device.createBuffer(BufferDesc) -> Buffer`, `commandList.writeBuffer(buffer, bytes)` (existing).
- Produces: `Scene` class with `CreateAssets(device, commandList) -> None`,
  `GetMaterialsBuffer() -> Buffer`, `GetWorldObjectsBuffer() -> Buffer`, `GetLightsBuffer() -> Buffer`,
  `GetAnimStateBuffer() -> Buffer`, `GetMeshVertexBuffer(meshType: int) -> Buffer`,
  `GetMeshIndexBuffer(meshType: int) -> Buffer`, `GetIndexCount(meshType: int) -> int`,
  `GetInstances() -> list`, `GetLights() -> list`, `GetSceneSize() -> float` (returns 500.0),
  `GetSceneHeight() -> float` (returns 210.0 = 70*3). Also module-level constants
  `MESH_PLANE=0`, `MESH_BOX=1`, `MESH_SPHERE=2` and struct byte sizes
  `MATERIAL_STRIDE=36`, `INSTANCE_STRIDE=40`, `LIGHT_STRIDE=56`, `ANIM_STATE_STRIDE=44`.
  Tasks 4-5 consume all of the above.

- [ ] **Step 1: Write the mesh generation functions**

Create `work_graphs.py` with:

```python
if __name__ == "__main__":
    import math
    import random
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    folder = Path(__file__).resolve().parent

    # MeshType
    MESH_PLANE = 0
    MESH_BOX = 1
    MESH_SPHERE = 2
    MESH_COUNT = 3

    # MaterialType
    BT_LAMBERT = 0
    BT_PHONG = 1
    BT_METALLIC = 2
    BT_VELVET = 3
    BT_FLAKES = 4
    BT_FACETED = 5
    BT_STAN = 6
    BT_CHECKER = 7

    # AnimType
    AT_STATIC = 0
    AT_ROTATEY = 1
    AT_DANCE = 2

    MATERIAL_STRIDE = 36   # 3f baseColor, u32 materialType, 3f param1, f param2, f param3
    INSTANCE_STRIDE = 40   # 3f position, f rotationY, 3f size, u32 meshType, u32 material, u32 animType
    LIGHT_STRIDE = 56      # 3f position, 3f target, 3f targetOffset, 3f color, f innerAngle, f outerAngle
    ANIM_STATE_STRIDE = 44 # u32 state, u32 stateRepeats, f statePeriod, f timeInState, 3f scale, f rotationY, f offsetY, f twist

    # Scene generation constants, matching scene.cpp exactly.
    SceneParam_MaterialCountOfEachType = 10
    SceneParam_Floors = 3
    SceneParam_FloorToCeilingHeight = 70.0
    SceneParam_FloorSize = 500.0
    SceneParam_ObjectRoomSize = 50.0
    SceneParam_BallRoomSize = 120.0
    SceneParam_BallSize = 15.0
    SceneParam_LightsPerBall = 3
    SceneParam_BoxSubdivisions = 100
    SceneParam_SphereSides = 100
    SceneParam_SphereSlices = 50
    SceneParam_GroundColor = (0.5, 0.5, 0.5)
    SceneParam_PhongSpecularColorScale = 0.05
    SceneParam_PhongSpecularPowerMin = 15.0
    SceneParam_PhongSpecularPowerRange = 25.0
    SceneParam_VelvetRoughnessMin = 0.45
    SceneParam_VelvetRoughnessRange = 0.1
    SceneParam_FlakesSpecularColorScale = 0.05
    SceneParam_FlakesSpecularPowerMin = 15.0
    SceneParam_FlakesSpecularPowerRange = 25.0
    SceneParam_FlakesGranularityMin = 0.3
    SceneParam_FlakesGranularityRange = 0.1
    SceneParam_StanLineThicknessMin = 0.2
    SceneParam_StanLineThicknessRange = 0.4
    SceneParam_StanLineSpacingMin = 1.0
    SceneParam_StanLineSpacingRange = 3.0
    SceneParam_CheckersSize = 4.0
    SceneParam_CheckersSpecularPowerMin = 15.0
    SceneParam_CheckersSpecularPowerRange = 25.0

    def GeneratePlaneInternal(y: float, sign: float, positions: list, normals: list, indices: list) -> None:
        baseVtx = len(positions)
        positions.extend([
            (-0.5 * sign, y, -0.5),
            (-0.5 * sign, y, 0.5),
            (0.5 * sign, y, 0.5),
            (0.5 * sign, y, -0.5),
        ])
        normals.extend([(0.0, sign, 0.0)] * 4)
        indices.extend([baseVtx + 0, baseVtx + 1, baseVtx + 2, baseVtx + 2, baseVtx + 3, baseVtx + 0])

    def GeneratePlane() -> tuple:
        positions, normals, indices = [], [], []
        GeneratePlaneInternal(0.0, 1.0, positions, normals, indices)
        GeneratePlaneInternal(0.0, -1.0, positions, normals, indices)
        return positions, normals, indices

    def GenerateBox(faceSubdivisions: int) -> tuple:
        positions, normals, indices = [], [], []

        def GenerateSide(coord0: int, coord1: int, posInit: tuple, nrm: tuple, sign: float) -> None:
            baseVtx = len(positions)
            pos = list(posInit)
            for y in range(faceSubdivisions + 1):
                pos[coord1] = y / faceSubdivisions - 0.5
                for x in range(faceSubdivisions + 1):
                    pos[coord0] = (x / faceSubdivisions - 0.5) * sign
                    positions.append((pos[0], pos[1], pos[2]))
                    normals.append(nrm)
            for y in range(faceSubdivisions):
                for x in range(faceSubdivisions):
                    faceBaseVtx = baseVtx + y * (faceSubdivisions + 1) + x
                    indices.append(faceBaseVtx + 0)
                    indices.append(faceBaseVtx + (faceSubdivisions + 1) + 0)
                    indices.append(faceBaseVtx + (faceSubdivisions + 1) + 1)
                    indices.append(faceBaseVtx + (faceSubdivisions + 1) + 1)
                    indices.append(faceBaseVtx + 1)
                    indices.append(faceBaseVtx + 0)

        GenerateSide(0, 1, (0.0, 0.0, -0.5), (0.0, 0.0, -1.0), 1.0)   # Front
        GenerateSide(2, 1, (0.5, 0.0, 0.0), (1.0, 0.0, 0.0), 1.0)     # Right
        GenerateSide(0, 1, (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), -1.0)    # Back
        GenerateSide(2, 1, (-0.5, 0.0, 0.0), (-1.0, 0.0, 0.0), -1.0)  # Left
        GeneratePlaneInternal(0.5, 1.0, positions, normals, indices)   # Top
        GeneratePlaneInternal(-0.5, -1.0, positions, normals, indices) # Bottom
        return positions, normals, indices

    def GenerateSphere(sides: int, slices: int) -> tuple:
        positions, normals, indices = [], [], []
        baseVtx = len(positions)

        positions.append((0.0, -0.5, 0.0))
        normals.append((0.0, -1.0, 0.0))
        for y in range(1, slices):
            py = y / slices - 0.5
            ringRadius = math.sqrt(max(0.0, 1.0 - py * py * 4.0)) * 0.5
            for x in range(sides):
                angle = (x / sides) * math.pi * 2.0
                px = math.cos(angle) * ringRadius
                pz = math.sin(angle) * ringRadius
                positions.append((px, py, pz))
                length = math.sqrt(px * px + py * py + pz * pz) or 1.0
                normals.append((px / length, py / length, pz / length))

        capVtx = len(positions)
        positions.append((0.0, 0.5, 0.0))
        normals.append((0.0, 1.0, 0.0))

        for i in range(sides):
            indices.append(baseVtx + 0)
            indices.append(baseVtx + 1 + i)
            indices.append(baseVtx + 1 + (i + 1) % sides)

        for y in range(slices - 2):
            sliceBaseVtx = baseVtx + 1 + y * sides
            for x in range(sides):
                indices.append(sliceBaseVtx + x + 0)
                indices.append(sliceBaseVtx + x + 0 + sides)
                indices.append(sliceBaseVtx + (x + 1) % sides + sides)
                indices.append(sliceBaseVtx + (x + 1) % sides + sides)
                indices.append(sliceBaseVtx + (x + 1) % sides)
                indices.append(sliceBaseVtx + x + 0)

        capBaseVtx = baseVtx + 1 + (slices - 2) * sides
        for i in range(sides):
            indices.append(capBaseVtx + i)
            indices.append(capVtx)
            indices.append(capBaseVtx + (i + 1) % sides)

        return positions, normals, indices
```

- [ ] **Step 2: Run a quick mesh-generation sanity check**

```bash
uv run python -c "
import sys; sys.argv = ['work_graphs.py']
import importlib.util
spec = importlib.util.spec_from_file_location('wg', 'work_graphs.py')
" 2>&1 | head -5
```
This won't actually execute the `if __name__ == \"__main__\":` block (importlib doesn't set
`__name__` to `'__main__'`), so instead verify directly with a small standalone script:
```bash
uv run python -c "
import math
def GenerateBox(n):
    positions = []
    def GenerateSide(coord0,coord1,posInit,nrm,sign):
        baseVtx = len(positions)
        pos = list(posInit)
        for y in range(n+1):
            pos[coord1] = y/n-0.5
            for x in range(n+1):
                pos[coord0] = (x/n-0.5)*sign
                positions.append((pos[0],pos[1],pos[2]))
    GenerateSide(0,1,(0,0,-0.5),(0,0,-1),1)
    GenerateSide(2,1,(0.5,0,0),(1,0,0),1)
    GenerateSide(0,1,(0,0,0.5),(0,0,1),-1)
    GenerateSide(2,1,(-0.5,0,0),(-1,0,0),-1)
    return positions
positions = GenerateBox(100)
print('box vertices (4 side faces only, sanity):', len(positions), 'expected', 4*(101*101))
assert len(positions) == 4*(101*101)
print('OK')
"
```
Expected: prints `OK`. (This step exists to catch an off-by-one in the subdivision loop before
it's buried inside the full `Scene` class; the full class's actual vertex counts — including
the two cap planes and the sphere — are verified in Step 6 below.)

- [ ] **Step 3: Write the randomization helpers and `PopulateWorld`**

Append to `work_graphs.py`, inside the `if __name__ == "__main__":` block, after the mesh
generation functions:

```python
    class Scene:
        def __init__(self) -> None:
            self.materials: list[dict] = []
            self.instances: list[dict] = []
            self.lights: list[dict] = []
            self._vertex_buffers: list = [None] * MESH_COUNT
            self._index_buffers: list = [None] * MESH_COUNT
            self._index_counts: list = [0] * MESH_COUNT
            self._materials_buffer = None
            self._instances_buffer = None
            self._lights_buffer = None
            self._anim_state_buffer = None

        def GetSceneSize(self) -> float:
            return SceneParam_FloorSize

        def GetSceneHeight(self) -> float:
            return SceneParam_FloorToCeilingHeight * SceneParam_Floors

        def GetMaterialsBuffer(self):
            return self._materials_buffer

        def GetWorldObjectsBuffer(self):
            return self._instances_buffer

        def GetLightsBuffer(self):
            return self._lights_buffer

        def GetAnimStateBuffer(self):
            return self._anim_state_buffer

        def GetMeshVertexBuffer(self, meshType: int):
            return self._vertex_buffers[meshType]

        def GetMeshIndexBuffer(self, meshType: int):
            return self._index_buffers[meshType]

        def GetIndexCount(self, meshType: int) -> int:
            return self._index_counts[meshType]

        def _populate_world(self, rnd: random.Random) -> None:
            def random_color(normalized: bool) -> tuple:
                c = (rnd.random(), rnd.random(), rnd.random())
                if not normalized:
                    return c
                length = math.sqrt(c[0] * c[0] + c[1] * c[1] + c[2] * c[2]) or 1.0
                return (c[0] / length, c[1] / length, c[2] / length)

            def random01() -> float:
                return rnd.random()

            def random_angle() -> float:
                return rnd.random() * math.pi * 2.0

            def random_pos_xz(extentsX: float, y: float, extentsZ: float) -> tuple:
                return ((rnd.random() - 0.5) * extentsX * 2.0, y, (rnd.random() - 0.5) * extentsZ * 2.0)

            def random_size(height: float, size: float, heightVariation: float, sizeVariation: float) -> tuple:
                return (
                    size + (rnd.random() - 0.5) * sizeVariation,
                    height + (rnd.random() - 0.5) * heightVariation,
                    size + (rnd.random() - 0.5) * sizeVariation,
                )

            # Materials 0 and 1 are hard-coded (ground Lambert, Faceted).
            self.materials.append({"baseColor": SceneParam_GroundColor, "materialType": BT_LAMBERT, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})
            self.materials.append({"baseColor": (1.0, 1.0, 1.0), "materialType": BT_FACETED, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                self.materials.append({"baseColor": random_color(True), "materialType": BT_LAMBERT, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                specColor = tuple(c * SceneParam_PhongSpecularColorScale for c in random_color(True))
                specPower = random01() * SceneParam_PhongSpecularPowerRange + SceneParam_PhongSpecularPowerMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_PHONG, "param1": specColor, "param2": specPower, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                self.materials.append({"baseColor": random_color(True), "materialType": BT_METALLIC, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                roughness = random01() * SceneParam_VelvetRoughnessRange + SceneParam_VelvetRoughnessMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_VELVET, "param1": (roughness, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                specColor = tuple(c * SceneParam_FlakesSpecularColorScale for c in random_color(True))
                specPower = random01() * SceneParam_FlakesSpecularPowerRange + SceneParam_FlakesSpecularPowerMin
                granularity = random01() * SceneParam_FlakesGranularityRange + SceneParam_FlakesGranularityMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_FLAKES, "param1": specColor, "param2": specPower, "param3": granularity})

            for _ in range(SceneParam_MaterialCountOfEachType):
                linesColor = random_color(False)
                linesThickness = random01() * SceneParam_StanLineThicknessRange + SceneParam_StanLineThicknessMin
                linesSpacing = random01() * SceneParam_StanLineSpacingRange + SceneParam_StanLineSpacingMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_STAN, "param1": linesColor, "param2": linesThickness, "param3": linesSpacing})

            for _ in range(SceneParam_MaterialCountOfEachType):
                baseColor2 = random_color(False)
                specPower = random01() * SceneParam_CheckersSpecularPowerRange + SceneParam_CheckersSpecularPowerMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_CHECKER, "param1": baseColor2, "param2": SceneParam_CheckersSize, "param3": specPower})

            for floor in range(SceneParam_Floors):
                floorHeight = floor * SceneParam_FloorToCeilingHeight
                ceilingHeight = (floor + 1) * SceneParam_FloorToCeilingHeight

                self.instances.append({"position": (0.0, floorHeight, 0.0), "rotationY": 0.0, "size": (SceneParam_FloorSize, 0.0, SceneParam_FloorSize), "meshType": MESH_PLANE, "material": 0, "animType": AT_STATIC})

                roomCount1D = int(SceneParam_FloorSize / SceneParam_BallRoomSize)
                ballHeight = ceilingHeight - SceneParam_BallSize * 0.5
                for roomX in range(roomCount1D):
                    for roomZ in range(roomCount1D):
                        roomCenterX = -SceneParam_FloorSize * 0.5 + roomX * SceneParam_BallRoomSize + SceneParam_BallRoomSize * 0.5
                        roomCenterZ = -SceneParam_FloorSize * 0.5 + roomZ * SceneParam_BallRoomSize + SceneParam_BallRoomSize * 0.5
                        bx, by, bz = random_pos_xz((SceneParam_BallRoomSize - SceneParam_BallSize) * 0.3, ballHeight, (SceneParam_BallRoomSize - SceneParam_BallSize) * 0.3)
                        ballPos = (bx + roomCenterX, by, bz + roomCenterZ)
                        self.instances.append({"position": ballPos, "rotationY": random_angle(), "size": (SceneParam_BallSize,) * 3, "meshType": MESH_SPHERE, "material": 1, "animType": AT_ROTATEY})

                        for _ in range(SceneParam_LightsPerBall):
                            dx, dy, dz = random_size(-1.0, 0.0, 0.8, 2.0)
                            dlen = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                            dx, dy, dz = dx / dlen, dy / dlen, dz / dlen
                            length = random01() * SceneParam_FloorSize * 0.35 + SceneParam_FloorToCeilingHeight
                            tgt = (dx * length + ballPos[0], dy * length + ballPos[1], dz * length + ballPos[2])
                            angle1 = random_angle() * 0.25 + 0.25
                            angle2 = random_angle() * 0.25 + 0.25
                            innerAngle = min(angle1, angle2)
                            outerAngle = max(angle1, angle2) + random_angle() * 0.1
                            self.lights.append({"position": ballPos, "target": tgt, "targetOffset": (0.0, 0.0, 0.0), "color": random_color(True), "innerAngle": innerAngle, "outerAngle": outerAngle})

                roomCount1D = int(SceneParam_FloorSize / SceneParam_ObjectRoomSize)
                for roomX in range(roomCount1D):
                    for roomZ in range(roomCount1D):
                        roomCenterX = -SceneParam_FloorSize * 0.5 + roomX * SceneParam_ObjectRoomSize + SceneParam_ObjectRoomSize * 0.5
                        roomCenterZ = -SceneParam_FloorSize * 0.5 + roomZ * SceneParam_ObjectRoomSize + SceneParam_ObjectRoomSize * 0.5
                        size = random_size(SceneParam_FloorToCeilingHeight * 0.35, SceneParam_ObjectRoomSize * 0.20, SceneParam_FloorToCeilingHeight * 0.1, SceneParam_ObjectRoomSize * 0.05)
                        px, py, pz = random_pos_xz((SceneParam_ObjectRoomSize - size[0]) * 0.5, floorHeight + size[1] * 0.5, (SceneParam_ObjectRoomSize - size[2]) * 0.5)
                        pos = (px + roomCenterX, py + 0.01, pz + roomCenterZ)
                        material = rnd.randrange(len(self.materials) - 2) + 2
                        self.instances.append({"position": pos, "rotationY": random_angle(), "size": size, "meshType": MESH_BOX, "material": material, "animType": AT_DANCE})

        def CreateAssets(self, device, commandList) -> None:
            rnd = random.Random(0)  # Deterministic layout, not bit-identical to the C++ srand(0) sequence.
            self._populate_world(rnd)

            mesh_generators = {
                MESH_PLANE: GeneratePlane(),
                MESH_BOX: GenerateBox(SceneParam_BoxSubdivisions),
                MESH_SPHERE: GenerateSphere(SceneParam_SphereSides, SceneParam_SphereSlices),
            }

            for meshType, (positions, normals, indices) in mesh_generators.items():
                vertexFloats = []
                for p, n in zip(positions, normals):
                    vertexFloats.extend(p)
                    vertexFloats.extend(n)
                vertexBytes = struct.pack(f"<{len(vertexFloats)}f", *vertexFloats)

                vbDesc = pyd.BufferDesc()
                vbDesc.byteSize = len(vertexBytes)
                vbDesc.isVertexBuffer = True
                vbDesc.initialState = pyd.ResourceStates.VertexBuffer
                vbDesc.keepInitialState = True
                vbDesc.debugName = f"MeshVB{meshType}"
                vb = device.createBuffer(vbDesc)
                commandList.writeBuffer(vb, vertexBytes)
                self._vertex_buffers[meshType] = vb

                indexBytes = struct.pack(f"<{len(indices)}H", *indices)
                ibDesc = pyd.BufferDesc()
                ibDesc.byteSize = len(indexBytes)
                ibDesc.isIndexBuffer = True
                ibDesc.initialState = pyd.ResourceStates.IndexBuffer
                ibDesc.keepInitialState = True
                ibDesc.debugName = f"MeshIB{meshType}"
                ib = device.createBuffer(ibDesc)
                commandList.writeBuffer(ib, indexBytes)
                self._index_buffers[meshType] = ib
                self._index_counts[meshType] = len(indices)

            materialBytes = b"".join(
                struct.pack("<3fI3fff", *m["baseColor"], m["materialType"], *m["param1"], m["param2"], m["param3"])
                for m in self.materials
            )
            matDesc = pyd.BufferDesc()
            matDesc.byteSize = len(materialBytes)
            matDesc.canHaveTypedViews = True
            matDesc.structStride = MATERIAL_STRIDE
            matDesc.initialState = pyd.ResourceStates.ShaderResource
            matDesc.keepInitialState = True
            matDesc.debugName = "MaterialsData"
            self._materials_buffer = device.createBuffer(matDesc)
            commandList.writeBuffer(self._materials_buffer, materialBytes)

            instanceBytes = b"".join(
                struct.pack("<3ff3fIII", *i["position"], i["rotationY"], *i["size"], i["meshType"], i["material"], i["animType"])
                for i in self.instances
            )
            instDesc = pyd.BufferDesc()
            instDesc.byteSize = len(instanceBytes)
            instDesc.canHaveTypedViews = True
            instDesc.structStride = INSTANCE_STRIDE
            instDesc.initialState = pyd.ResourceStates.ShaderResource
            instDesc.keepInitialState = True
            instDesc.debugName = "InstancesData"
            self._instances_buffer = device.createBuffer(instDesc)
            commandList.writeBuffer(self._instances_buffer, instanceBytes)

            lightBytes = b"".join(
                struct.pack("<3f3f3f3fff", *l["position"], *l["target"], *l["targetOffset"], *l["color"], l["innerAngle"], l["outerAngle"])
                for l in self.lights
            )
            lightDesc = pyd.BufferDesc()
            lightDesc.byteSize = len(lightBytes)
            lightDesc.canHaveUAVs = True
            lightDesc.canHaveTypedViews = True
            lightDesc.structStride = LIGHT_STRIDE
            lightDesc.initialState = pyd.ResourceStates.UnorderedAccess
            lightDesc.keepInitialState = True
            lightDesc.debugName = "LightsData"
            self._lights_buffer = device.createBuffer(lightDesc)
            commandList.writeBuffer(self._lights_buffer, lightBytes)

            animStateDesc = pyd.BufferDesc()
            animStateDesc.byteSize = ANIM_STATE_STRIDE * len(self.instances)
            animStateDesc.canHaveUAVs = True
            animStateDesc.canHaveTypedViews = True
            animStateDesc.structStride = ANIM_STATE_STRIDE
            animStateDesc.initialState = pyd.ResourceStates.UnorderedAccess
            animStateDesc.keepInitialState = True
            animStateDesc.debugName = "AnimState"
            self._anim_state_buffer = device.createBuffer(animStateDesc)  # No upload: matches Scene::CreateAssets, which never
            # writes initial contents -- the first animation dispatch (g_ResetState=1) initializes it on the GPU.
```

- [ ] **Step 4: Add the bootstrap and a scene-only smoke test path**

Append at the end of the `if __name__ == "__main__":` block:

```python
    def _scene_smoke_test() -> bool:
        api = pyd.GraphicsAPI.D3D12
        deviceManager = pyd.DeviceManager.Create(api)
        if not deviceManager:
            pyd.log.fatal("Failed to create DeviceManager.")
            return False
        deviceParams = pyd.DeviceCreationParameters()
        if not deviceManager.CreateHeadlessDevice(deviceParams):
            pyd.log.error("Cannot initialize a graphics device with the requested parameters")
            return False
        device = deviceManager.GetDevice()

        commandList = device.createCommandList()
        commandList.open()
        scene = Scene()
        scene.CreateAssets(device, commandList)
        commandList.close()
        device.executeCommandList(commandList)
        device.waitForIdle()

        expectedMaterialCount = 2 + 7 * SceneParam_MaterialCountOfEachType
        ok = (
            len(scene.materials) == expectedMaterialCount
            and scene.GetMaterialsBuffer() is not None
            and scene.GetWorldObjectsBuffer() is not None
            and scene.GetLightsBuffer() is not None
            and scene.GetAnimStateBuffer() is not None
            and all(scene.GetMeshVertexBuffer(mt) is not None for mt in (MESH_PLANE, MESH_BOX, MESH_SPHERE))
            and all(scene.GetMeshIndexBuffer(mt) is not None for mt in (MESH_PLANE, MESH_BOX, MESH_SPHERE))
            and scene.GetIndexCount(MESH_BOX) > 0
            and len(scene.instances) > 0
            and len(scene.lights) > 0
        )
        print(f"materials={len(scene.materials)} (expected {expectedMaterialCount}), "
              f"instances={len(scene.instances)}, lights={len(scene.lights)}, "
              f"box_indices={scene.GetIndexCount(MESH_BOX)}")
        print("Test PASSED" if ok else "Test FAILED!")
        deviceManager.Shutdown()
        return ok

    if "--scene-smoke-test" in sys.argv:
        sys.exit(0 if _scene_smoke_test() else 1)
```

- [ ] **Step 5: Rebuild (no new native code in this task, but confirms nothing regressed)**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds (this task adds no C++; this step is a quick sanity check the module still imports).

- [ ] **Step 6: Run the scene-only smoke test**

Run: `uv run python work_graphs.py --scene-smoke-test`
Expected: prints `materials=72 (expected 72), instances=<N>, lights=<M>, box_indices=<K>` with
`N`/`M`/`K` all positive (exact values depend on the room-grid math — e.g. `roomCount1D`
computed from `int(500/120)=4` ball rooms per floor and `int(500/50)=10` object rooms per floor,
times 3 floors — but the important check is that generation completes without exception and
produces the expected material count and non-zero instance/light/index counts), then `Test PASSED`.

- [ ] **Step 7: Commit**

```bash
git add work_graphs.py
git commit -m "Add Scene class: procedural mesh/material/instance/light generation for work_graphs.py"
```

---

## Task 4: `RenderTargets` + pipeline/binding-layout setup

**Files:**
- Modify: `work_graphs.py` (extend, adding `RenderTargets` and the pipeline-loading half of
  the main render pass class)

**Interfaces:**
- Consumes: `Scene` (Task 3) — `GetMaterialsBuffer()`, `GetWorldObjectsBuffer()`,
  `GetLightsBuffer()`, `GetAnimStateBuffer()`. The 4 HLSL files (Task 2) and their entry point
  names.
- Produces: `RenderTargets` class (`__init__(device, width, height)`: `.depth`, `.gbuffer`,
  `.ldr_buffer`, `.framebuffer_gb` (a `FramebufferFactory`), `.size`). A `WorkGraphs` class
  with `load_scene_pipelines(fbinfo_view) -> None` building: one binding layout per pass
  (`self.animate_objects_layout`, `self.animate_lights_layout`, `self.gbuffer_fill_layout`,
  `self.light_culling_layout`, `self.deferred_shading_layout` — each derived via
  `pyd.CreateBindingSetAndLayout` from that pass's own tailored `BindingSetDesc`, not one
  shared over-provisioned layout), `self.input_layout`, `self.animate_objects_pso`,
  `self.animate_lights_pso`, `self.gbuffer_fill_pso`, `self.cull_lights_pso`, `self.shade_pso`,
  `self.constant_buffer`, `self.culled_lights_buffer`, `self.binding_sets` (dict keyed by pass
  name: `"animate_objects"`, `"animate_lights"`, `"gbuffer_fill"`, `"light_culling"`,
  `"deferred_shading"`). Task 5 consumes all of the above plus `Scene`'s buffers to record
  and dispatch the actual frame.

- [ ] **Step 1: Write `RenderTargets`**

Append to `work_graphs.py`, after the `Scene` class:

```python
    DeferredShadingParam_MaxLightsPerTile = 64  # Must match c_MaxLightsPerTile in lighting.hlsli.
    DeferredShadingParam_TileWidth = 8
    DeferredShadingParam_TileHeight = 4

    def GetLightTileCountX(viewportWidth: int) -> int:
        return (viewportWidth + DeferredShadingParam_TileWidth - 1) // DeferredShadingParam_TileWidth

    def GetLightTileCountY(viewportHeight: int) -> int:
        return (viewportHeight + DeferredShadingParam_TileHeight - 1) // DeferredShadingParam_TileHeight

    class RenderTargets:
        def __init__(self, device, width: int, height: int) -> None:
            self.size = (width, height)

            depthDesc = pyd.TextureDesc()
            depthDesc.width = width
            depthDesc.height = height
            depthDesc.keepInitialState = True
            depthDesc.useClearValue = True
            depthDesc.clearValue = pyd.Color(1.0)
            depthDesc.isRenderTarget = True
            depthDesc.isTypeless = True
            depthDesc.format = pyd.Format.D32
            depthDesc.initialState = pyd.ResourceStates.ShaderResource
            depthDesc.debugName = "DepthBuffer"
            self.depth = device.createTexture(depthDesc)

            gbufferDesc = pyd.TextureDesc()
            gbufferDesc.width = width
            gbufferDesc.height = height
            gbufferDesc.keepInitialState = True
            gbufferDesc.isRenderTarget = True
            gbufferDesc.format = pyd.Format.RGBA16_UINT
            gbufferDesc.useClearValue = True
            gbufferDesc.clearValue = pyd.Color(0.0)
            gbufferDesc.initialState = pyd.ResourceStates.ShaderResource
            gbufferDesc.debugName = "GBuffer"
            self.gbuffer = device.createTexture(gbufferDesc)

            ldrDesc = pyd.TextureDesc()
            ldrDesc.width = width
            ldrDesc.height = height
            ldrDesc.keepInitialState = True
            ldrDesc.format = pyd.Format.RGBA8_UNORM
            ldrDesc.isUAV = True
            ldrDesc.initialState = pyd.ResourceStates.UnorderedAccess
            ldrDesc.debugName = "LDRBuffer"
            self.ldr_buffer = device.createTexture(ldrDesc)

            self.framebuffer_gb = pyd.FramebufferFactory(device)
            self.framebuffer_gb.SetRenderTargets([self.gbuffer])
            self.framebuffer_gb.depthTarget = self.depth

        def is_update_required(self, width: int, height: int) -> bool:
            return self.size != (width, height)
```

- [ ] **Step 2: Write `LoadScenePipelines` (binding layout, input layout, PSOs, buffers)**

Append the main render-pass class:

```python
    class WorkGraphs:
        def __init__(self, device) -> None:
            self.device = device
            self.scene = Scene()
            self.render_targets = None
            self.time_in_seconds = 0.0
            self.time_diff_this_frame = 0.0
            self.force_reset_animation = True

        def init(self, commandList) -> None:
            self.scene.CreateAssets(self.device, commandList)

            # Matches variable_shading.py's exact mount pattern for donut's precompiled
            # framework shaders (needed here only for CommonRenderPasses.BlitTexture).
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(self.device.getGraphicsAPI())
            rootFs = pyd.RootFileSystem()
            rootFs.mount(Path("/shaders/donut"), frameworkShaderPath)
            shaderFactory = pyd.ShaderFactory(self.device, rootFs, Path("/shaders"))
            self.common_passes = pyd.CommonRenderPasses(self.device, shaderFactory)

        def load_scene_pipelines(self, fbinfo_view) -> None:
            # Design note: unlike the C++ sample (which builds ONE shared, over-provisioned
            # BindingLayoutDesc across all 5 passes, padded with null SRV/UAV placeholder
            # resources for slots a given pass doesn't use, so every pass can share one root
            # signature), each pass here gets its OWN binding layout, tailored to exactly the
            # registers that specific compiled shader stage actually declares. This is possible
            # because pydonut's BindingLayoutItem has no PushConstants factory (only
            # BindingSetItem does) -- a layout can only be hand-built from BindingLayoutItem, so
            # a manually-constructed shared layout can't declare a push-constant range at all.
            # `pyd.CreateBindingSetAndLayout(device, visibility, registerSpace, bindingSetDesc)`
            # derives the matching layout FROM a binding set (which DOES support
            # BindingSetItem.PushConstants), so it's used once per pass instead. This also drops
            # the null-placeholder buffers/textures entirely -- each pass only ever binds what
            # its own shader stage actually uses.
            api = self.device.getGraphicsAPI()
            shader_dir = folder / "shaders" / "work_graphs"
            source_paths = {
                "animation": shader_dir / "animation.hlsl",
                "gbuffer_fill": shader_dir / "gbuffer_fill.hlsl",
                "light_culling": shader_dir / "light_culling.hlsl",
                "deferred_shading": shader_dir / "deferred_shading.hlsl",
            }
            sources = {k: v.read_text(encoding="utf-8") for k, v in source_paths.items()}
            include_paths = [str(shader_dir)]

            animate_objects_bc = pyd.CompileShader(sources["animation"], "CSMainObjects", pyd.ShaderType.Compute, api, sourceName="animation.hlsl", includePaths=include_paths)
            animate_lights_bc = pyd.CompileShader(sources["animation"], "CSMainLights", pyd.ShaderType.Compute, api, sourceName="animation.hlsl", includePaths=include_paths)
            gbuffer_vs_bc = pyd.CompileShader(sources["gbuffer_fill"], "VSMain", pyd.ShaderType.Vertex, api, sourceName="gbuffer_fill.hlsl", includePaths=include_paths)
            gbuffer_ps_bc = pyd.CompileShader(sources["gbuffer_fill"], "PSMain", pyd.ShaderType.Pixel, api, sourceName="gbuffer_fill.hlsl", includePaths=include_paths)
            light_culling_bc = pyd.CompileShader(sources["light_culling"], "CSMain", pyd.ShaderType.Compute, api, sourceName="light_culling.hlsl", includePaths=include_paths)
            deferred_shading_bc = pyd.CompileShader(sources["deferred_shading"], "CSMain", pyd.ShaderType.Compute, api, sourceName="deferred_shading.hlsl", includePaths=include_paths)

            animate_objects_shader = self.device.createShader(animate_objects_bc, "CSMainObjects", pyd.ShaderType.Compute)
            animate_lights_shader = self.device.createShader(animate_lights_bc, "CSMainLights", pyd.ShaderType.Compute)
            gbuffer_vs = self.device.createShader(gbuffer_vs_bc, "VSMain", pyd.ShaderType.Vertex)
            gbuffer_ps = self.device.createShader(gbuffer_ps_bc, "PSMain", pyd.ShaderType.Pixel)
            light_culling_shader = self.device.createShader(light_culling_bc, "CSMain", pyd.ShaderType.Compute)
            deferred_shading_shader = self.device.createShader(deferred_shading_bc, "CSMain", pyd.ShaderType.Compute)

            attributes = [pyd.VertexAttributeDesc(), pyd.VertexAttributeDesc()]
            attributes[0].name = "POSITION"
            attributes[0].format = pyd.Format.RGB32_FLOAT
            attributes[0].offset = 0
            attributes[0].elementStride = 24
            attributes[1].name = "NORMAL"
            attributes[1].format = pyd.Format.RGB32_FLOAT
            attributes[1].offset = 12
            attributes[1].elementStride = 24
            self.input_layout = self.device.createInputLayout(attributes, gbuffer_vs)

            cbDesc = pyd.BufferDesc()
            cbDesc.byteSize = 256
            cbDesc.maxVersions = 16
            cbDesc.isConstantBuffer = True
            cbDesc.isVolatile = True
            cbDesc.debugName = "SceneConstants"
            cbDesc.initialState = pyd.ResourceStates.ShaderResource
            cbDesc.keepInitialState = True
            self.constant_buffer = self.device.createBuffer(cbDesc)

            width, height = self.render_targets.size
            tileCount = GetLightTileCountX(width) * GetLightTileCountY(height)
            culledLightsDesc = pyd.BufferDesc()
            culledLightsDesc.byteSize = tileCount * DeferredShadingParam_MaxLightsPerTile * 4
            culledLightsDesc.structStride = 4
            culledLightsDesc.canHaveUAVs = True
            culledLightsDesc.debugName = "CulledLights"
            culledLightsDesc.initialState = pyd.ResourceStates.ShaderResource
            culledLightsDesc.keepInitialState = True
            self.culled_lights_buffer = self.device.createBuffer(culledLightsDesc)

            # Per-pass binding sets/layouts, each matching exactly that shader's own registers
            # (register numbers taken directly from the copied HLSL files in shaders/work_graphs/).

            objectsSetDesc = pyd.BindingSetDesc()
            objectsSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # cbuffer InlineConstants: g_Time, g_TimeDiff, g_ResetState (animation.hlsl)
                pyd.BindingSetItem.StructuredBuffer_SRV(0, self.scene.GetWorldObjectsBuffer()),  # t_InstanceData : t0
                pyd.BindingSetItem.StructuredBuffer_UAV(0, self.scene.GetAnimStateBuffer()),      # u_AnimStateData : u0
            ]
            self.animate_objects_layout, self.binding_sets_animate_objects = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, objectsSetDesc)

            lightsSetDesc = pyd.BindingSetDesc()
            lightsSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # same InlineConstants layout, CSMainLights only reads g_Time/g_ResetState
                pyd.BindingSetItem.StructuredBuffer_UAV(0, self.scene.GetLightsBuffer()),  # u_LightData : u0
            ]
            self.animate_lights_layout, self.binding_sets_animate_lights = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, lightsSetDesc)

            gbufferSetDesc = pyd.BindingSetDesc()
            gbufferSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 4),  # cbuffer InstanceConstantBuffer: g_InstanceID (gbuffer_fill.hlsl)
                pyd.BindingSetItem.ConstantBuffer(1, self.constant_buffer),  # SceneConstantBuffer : b1 (scene_data.hlsli, viewProj)
                pyd.BindingSetItem.StructuredBuffer_SRV(0, self.scene.GetWorldObjectsBuffer()),  # t_InstanceData : t0
                pyd.BindingSetItem.StructuredBuffer_SRV(3, self.scene.GetMaterialsBuffer()),     # t_MaterialData : t3
                pyd.BindingSetItem.StructuredBuffer_SRV(4, self.scene.GetAnimStateBuffer()),     # t_AnimStateData : t4
            ]
            self.gbuffer_fill_layout, self.binding_sets_gbuffer_fill = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.All, 0, gbufferSetDesc)

            cullingSetDesc = pyd.BindingSetDesc()
            cullingSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # g_LightTilesX, g_LightTilesY, g_LightCount (light_culling.hlsl)
                pyd.BindingSetItem.ConstantBuffer(1, self.constant_buffer),
                pyd.BindingSetItem.Texture_SRV(1, self.render_targets.depth),                    # t_DepthBuffer : t1
                pyd.BindingSetItem.StructuredBuffer_SRV(4, self.scene.GetLightsBuffer()),        # t_LightData : t4
                pyd.BindingSetItem.StructuredBuffer_UAV(0, self.culled_lights_buffer),           # u_CulledLightsDataRW : u0
            ]
            self.light_culling_layout, self.binding_sets_light_culling = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, cullingSetDesc)

            shadingSetDesc = pyd.BindingSetDesc()
            shadingSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # g_LightTilesX, g_LightTilesY, g_LightCount (deferred_shading.hlsl)
                pyd.BindingSetItem.ConstantBuffer(1, self.constant_buffer),
                pyd.BindingSetItem.StructuredBuffer_SRV(0, self.scene.GetMaterialsBuffer()),     # t_MaterialData : t0
                pyd.BindingSetItem.Texture_SRV(1, self.render_targets.gbuffer),                  # t_GBuffer : t1
                pyd.BindingSetItem.Texture_SRV(2, self.render_targets.depth),                    # t_DepthBuffer : t2
                pyd.BindingSetItem.StructuredBuffer_SRV(3, self.culled_lights_buffer),           # t_CulledLightsData : t3
                pyd.BindingSetItem.StructuredBuffer_SRV(4, self.scene.GetLightsBuffer()),        # t_LightData : t4
                pyd.BindingSetItem.Texture_UAV(1, self.render_targets.ldr_buffer),               # u_LDRBuffer : u1
            ]
            self.deferred_shading_layout, self.binding_sets_deferred_shading = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, shadingSetDesc)

            gfxDesc = pyd.GraphicsPipelineDesc()
            gfxDesc.inputLayout = self.input_layout
            gfxDesc.addBindingLayout(self.gbuffer_fill_layout)
            gfxDesc.VS = gbuffer_vs
            gfxDesc.PS = gbuffer_ps
            self.gbuffer_fill_pso = self.device.createGraphicsPipeline(gfxDesc, fbinfo_view)

            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.animate_objects_layout)
            csDesc.CS = animate_objects_shader
            self.animate_objects_pso = self.device.createComputePipeline(csDesc)
            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.animate_lights_layout)
            csDesc.CS = animate_lights_shader
            self.animate_lights_pso = self.device.createComputePipeline(csDesc)
            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.light_culling_layout)
            csDesc.CS = light_culling_shader
            self.cull_lights_pso = self.device.createComputePipeline(csDesc)
            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.deferred_shading_layout)
            csDesc.CS = deferred_shading_shader
            self.shade_pso = self.device.createComputePipeline(csDesc)

            self.binding_sets = {
                "animate_objects": self.binding_sets_animate_objects,
                "animate_lights": self.binding_sets_animate_lights,
                "gbuffer_fill": self.binding_sets_gbuffer_fill,
                "light_culling": self.binding_sets_light_culling,
                "deferred_shading": self.binding_sets_deferred_shading,
            }

            self.force_reset_animation = True
```

- [ ] **Step 3: Rebuild**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds (no new native code in this task; confirms the file still imports
cleanly as Python).

- [ ] **Step 4: Verify pipeline/binding-set construction against a headless device**

```bash
uv run python -c "
import sys
sys.argv = ['work_graphs.py']
exec(open('work_graphs.py').read().split('if \"--scene-smoke-test\"')[0])
deviceManager = pyd.DeviceManager.Create(pyd.GraphicsAPI.D3D12)
deviceParams = pyd.DeviceCreationParameters()
assert deviceManager.CreateHeadlessDevice(deviceParams)
device = deviceManager.GetDevice()
commandList = device.createCommandList()
commandList.open()
wg = WorkGraphs(device)
wg.init(commandList)
commandList.close()
device.executeCommandList(commandList)
device.waitForIdle()
wg.render_targets = RenderTargets(device, 1920, 1080)
view = pyd.PlanarView()
view.SetViewport(pyd.Viewport(0, 1920, 0, 1080, 0, 1))
fb = wg.render_targets.framebuffer_gb.GetFramebuffer(view)
wg.load_scene_pipelines(fb.getFramebufferInfo())
print('OK: pipelines and binding sets constructed with no exception')
deviceManager.Shutdown()
"
```
Expected: prints `OK: pipelines and binding sets constructed with no exception`
(`Device.createGraphicsPipeline(desc, framebufferInfo: FramebufferInfo)` and
`Framebuffer.getFramebufferInfo() -> FramebufferInfo` are both confirmed in `_pydonut.pyi`, so
`fb.getFramebufferInfo()` is the correct and only argument needed — no fallback logic required).

- [ ] **Step 5: Commit**

```bash
git add work_graphs.py
git commit -m "Add RenderTargets and pipeline/binding-set setup for work_graphs.py"
```

---

## Task 5: Render loop, camera, and bootstrap — full visual verification

**Files:**
- Modify: `work_graphs.py` (final extension: `update_scene_constants`, the 4 per-frame
  populate-pass methods, `Render`, `Animate`, and the `main()`/CLI bootstrap)

**Interfaces:**
- Consumes: everything from Tasks 1-4 (`Scene`, `RenderTargets`, `WorkGraphs.binding_sets`/
  pipelines/buffers, `PlanarView.SetMatricesLookAt`).
- Produces: a runnable `work_graphs.py` — the final deliverable of this plan.

- [ ] **Step 1: Write `update_scene_constants` (camera + constant buffer)**

Append to the `WorkGraphs` class:

```python
        def update_scene_constants(self, commandList, view) -> None:
            sceneSize = self.scene.GetSceneSize()
            sceneHeight = self.scene.GetSceneHeight()

            camPosOrbitSpeed = 0.1
            camTargetOrbitSpeed = 0.03
            camPosRadiusRatio = 0.75
            camTargetRadiusRatio = 0.1
            camClimbSpeed = 0.1
            camClimbRatio = 0.6
            camVerticalFov = (math.pi / 4.0) * 1.15
            camNearClip = 0.5

            t = self.time_in_seconds
            camX = math.cos(t * camPosOrbitSpeed) * sceneSize * camPosRadiusRatio
            camY = math.sin(t * camClimbSpeed - 1.75) * sceneHeight * camClimbRatio + sceneHeight * camClimbRatio + 10.0
            camZ = math.sin(t * camPosOrbitSpeed) * sceneSize * camPosRadiusRatio

            tgtX = math.cos(t * camTargetOrbitSpeed) * sceneSize * camTargetRadiusRatio
            tgtY = 0.0
            tgtZ = math.sin(t * camTargetOrbitSpeed) * sceneSize * camTargetRadiusRatio

            width, height = self.render_targets.size
            aspectRatio = width / height
            view.SetMatricesLookAt(camX, camY, camZ, tgtX, tgtY, tgtZ, 0.0, 1.0, 0.0,
                                    aspectRatio, camVerticalFov, camNearClip, sceneSize * 1.2)
            view.UpdateCache()

            dirX, dirY, dirZ = tgtX - camX, tgtY - camY, tgtZ - camZ
            dirLen = math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ) or 1.0
            dirX, dirY, dirZ = dirX / dirLen, dirY / dirLen, dirZ / dirLen

            # SceneConstantBuffer layout (256 bytes total): viewProj(64) + viewProjInverse(64)
            # + camPosAndSceneTime(16) + camDir(16) + viewportSizeXY(16) + padding(80), matching
            # scene_data.hlsli's cbuffer exactly. GetViewProjMatrixBytes() (Task 1) returns the
            # first 128 bytes (viewProj + viewProjInverse) directly from PlanarView's own
            # GetViewProjectionMatrix()/GetInverseViewProjectionMatrix() -- no matrix math here.
            viewProjBytes = view.GetViewProjMatrixBytes()  # 128 bytes: viewProj + viewProjInverse
            constants = viewProjBytes + struct.pack(
                "<4f4f4f80x",
                camX, camY, camZ, self.time_in_seconds,
                dirX, dirY, dirZ, 0.0,
                float(width), float(height), 0.0, 0.0,
            )
            assert len(constants) == 256
            commandList.writeBuffer(self.constant_buffer, constants)
```

- [ ] **Step 2: Write the 4 populate-pass methods**

Append to the `WorkGraphs` class:

```python
        def populate_animation_pass(self, commandList) -> None:
            resetAnim = self.force_reset_animation

            state = pyd.ComputeState()
            state.pipeline = self.animate_objects_pso
            state.addBindingSet(self.binding_sets["animate_objects"])
            commandList.setComputeState(state)
            rootConstants = struct.pack("<ffI", self.time_in_seconds, self.time_diff_this_frame, 1 if resetAnim else 0)
            commandList.setPushConstants(rootConstants)
            threadsX = 32
            totalDispatch = (len(self.scene.instances) + threadsX - 1) // threadsX
            commandList.dispatch(max(totalDispatch, 1), 1, 1)

            state = pyd.ComputeState()
            state.pipeline = self.animate_lights_pso
            state.addBindingSet(self.binding_sets["animate_lights"])
            commandList.setComputeState(state)
            commandList.setPushConstants(rootConstants)
            totalDispatch = (len(self.scene.lights) + threadsX - 1) // threadsX
            commandList.dispatch(max(totalDispatch, 1), 1, 1)

            self.force_reset_animation = False

        def populate_gbuffer_pass(self, commandList, framebuffer) -> None:
            commandList.clearDepthStencilTexture(self.render_targets.depth, True, 1.0, False, 0)

            fbinfo = framebuffer.getFramebufferInfo()

            lastMeshType = None
            indexCount = 0
            for objectIndex, instance in enumerate(self.scene.instances):
                meshType = instance["meshType"]
                if meshType != lastMeshType:
                    lastMeshType = meshType
                    indexCount = self.scene.GetIndexCount(meshType)

                    state = pyd.GraphicsState()
                    state.pipeline = self.gbuffer_fill_pso
                    state.addBindingSet(self.binding_sets["gbuffer_fill"])
                    state.framebuffer = framebuffer
                    state.viewport.addViewportAndScissorRect(fbinfo.getViewport())
                    state.addVertexBuffer(self.scene.GetMeshVertexBuffer(meshType), 0)
                    state.setIndexBuffer(self.scene.GetMeshIndexBuffer(meshType), pyd.Format.R16_UINT)
                    commandList.setGraphicsState(state)

                # cbuffer InstanceConstantBuffer (gbuffer_fill.hlsl): one uint32, g_InstanceID.
                rootConstant = struct.pack("<I", objectIndex)
                commandList.setPushConstants(rootConstant)
                drawArgs = pyd.DrawArguments()
                drawArgs.vertexCount = indexCount
                commandList.drawIndexed(drawArgs)

        def populate_light_culling_pass(self, commandList) -> None:
            state = pyd.ComputeState()
            state.pipeline = self.cull_lights_pso
            state.addBindingSet(self.binding_sets["light_culling"])
            commandList.setComputeState(state)
            width, height = self.render_targets.size
            tilesX, tilesY = GetLightTileCountX(width), GetLightTileCountY(height)
            rootConstants = struct.pack("<III", tilesX, tilesY, len(self.scene.lights))
            commandList.setPushConstants(rootConstants)
            commandList.dispatch(tilesX, tilesY, 1)

        def populate_deferred_shading_pass(self, commandList) -> None:
            state = pyd.ComputeState()
            state.pipeline = self.shade_pso
            state.addBindingSet(self.binding_sets["deferred_shading"])
            commandList.setComputeState(state)
            width, height = self.render_targets.size
            tilesX, tilesY = GetLightTileCountX(width), GetLightTileCountY(height)
            rootConstants = struct.pack("<III", tilesX, tilesY, len(self.scene.lights))
            commandList.setPushConstants(rootConstants)
            threadsX, threadsY = 8, 4
            commandList.dispatch((width + threadsX - 1) // threadsX, (height + threadsY - 1) // threadsY, 1)

        def render(self, commandList, view, backbuffer) -> None:
            fbinfo = backbuffer.getFramebufferInfo()
            width, height = fbinfo.width, fbinfo.height

            if self.render_targets is None or self.render_targets.is_update_required(width, height):
                self.render_targets = RenderTargets(self.device, width, height)
                self.load_scene_pipelines(self.render_targets.framebuffer_gb.GetFramebuffer(view))

            self.update_scene_constants(commandList, view)
            self.populate_animation_pass(commandList)
            self.populate_gbuffer_pass(commandList, self.render_targets.framebuffer_gb.GetFramebuffer(view))
            self.populate_light_culling_pass(commandList)
            self.populate_deferred_shading_pass(commandList)
            self.common_passes.BlitTexture(commandList, backbuffer, self.render_targets.ldr_buffer)
```

Note: this port omits the C++ sample's D3D12-specific `D3D12_CS_DISPATCH_MAX_THREAD_GROUPS_PER_DIMENSION`
2D-dispatch-splitting logic for the animation passes (used there to handle scene object/light
counts that could exceed a 1D dispatch's group-count limit on some drivers). This scene's actual
instance/light counts (low thousands at most, per the density constants above) are far below
that limit even as a 1D dispatch, so the simpler `dispatch(n, 1, 1)` form used here is
sufficient — flag this simplification in the task report as a deliberate, scoped-out deviation,
not an oversight.

- [ ] **Step 3: Write `Animate` and the CLI/bootstrap**

Append:

```python
        def animate(self, elapsed: float) -> None:
            self.time_diff_this_frame = elapsed
            self.time_in_seconds += elapsed

    is_debug = "-debug" in sys.argv
    pyd.log.ConsoleApplicationMode()
    if not is_debug:
        pyd.log.SetMinSeverity(pyd.LogSeverity.Warning)

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True
    deviceParams.backBufferWidth = 1920
    deviceParams.backBufferHeight = 1080

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Work Graphs (Dispatch)"):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    device = deviceManager.GetDevice()
    wg = WorkGraphs(device)
    commandList = device.createCommandList()
    commandList.open()
    wg.init(commandList)
    commandList.close()
    device.executeCommandList(commandList)
    device.waitForIdle()

    view = pyd.PlanarView()

    class RenderPass(pyd.IRenderPass):
        def __init__(self, deviceManager) -> None:
            super().__init__(deviceManager)

        def Render(self, framebuffer) -> None:
            cl = device.createCommandList()
            cl.open()
            wg.render(cl, view, framebuffer)
            cl.close()
            device.executeCommandList(cl)
            deviceManager.SetInformativeWindowTitle("PyDonut Work Graphs (Dispatch)")

        def Animate(self, elapsedTimeSeconds: float) -> None:
            wg.animate(elapsedTimeSeconds)

    renderPass = RenderPass(deviceManager)
    deviceManager.AddRenderPassToBack(renderPass)
    deviceManager.RunMessageLoop()
    deviceManager.RemoveRenderPass(renderPass)
    deviceManager.Shutdown()
```

- [ ] **Step 4: Rebuild**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds.

- [ ] **Step 5: Run and visually verify**

Run: `uv run python work_graphs.py` (with a bounded timeout, e.g. 15-20 seconds, since this
opens a real window and runs its message loop — capture stdout/stderr and then terminate the
process; there is no automatic exit).
Expected:
- Reaches window creation with no exception/traceback in the captured output.
- A window titled "PyDonut Work Graphs (Dispatch)" opens showing: multiple stacked floors, a
  ground plane per floor, scattered animated boxes ("dancers") on each floor, spheres
  ("glitter balls") hanging with moving spot lights, and a procedural sky visible where no
  geometry occludes it — visually similar in composition to `work_graphs_d3d12.jpg`
  (`E:\Gits\Donut-Samples\examples\work_graphs\work_graphs_d3d12.jpg`), though this port has no
  ImGui overlay and only the dispatch technique (no side-by-side comparison yet).
- No black screen, no fully-white/garbage G-buffer, no obviously wrong (inside-out or
  flipped) geometry — if any of these happen, treat it as a real bug in the camera matrices
  (Step 2) or binding-set wiring (Task 4), not a cosmetic issue to wave off.

- [ ] **Step 6: Regression check**

Run: `uv run python headless.py`
Expected: still passes, confirming the new native binding(s) added in this plan didn't break
anything else.

- [ ] **Step 7: Commit**

```bash
git add work_graphs.py src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi
git commit -m "Add render loop, camera, and bootstrap: work_graphs.py dispatch path complete"
```

---

## Plan Self-Review Notes

- **Spec coverage:** every "Decisions made during brainstorming" bullet and every "New native
  bindings"/file-structure item in the design doc maps to a task: camera binding (Task 1),
  HLSL port (Task 2), scene generation (Task 3), render targets/pipelines (Task 4), render
  loop/bootstrap (Task 5).
- **View/projection matrix accessor resolved during planning, not deferred:** verified against
  `donut/engine/View.h:77-78` that `PlanarView::GetViewProjectionMatrix()`/
  `GetInverseViewProjectionMatrix()` already exist, so Task 1's `GetViewProjMatrixBytes` binding
  and Task 5's `update_scene_constants` use them directly — no placeholder matrix bytes, no
  mid-implementation research checkpoint.
- **Placeholder scan:** no bare "TBD"/"handle appropriately." The one deliberately-flagged
  self-correction in Task 3 Step 3 (the duplicated Checkers `specPower` line) is intentional —
  it's teaching the implementer to write the corrected version, not asking them to guess.
- **Type/name consistency:** `Scene`/`RenderTargets`/`WorkGraphs` class and method names, and
  the `MATERIAL_STRIDE`/`INSTANCE_STRIDE`/`LIGHT_STRIDE`/`ANIM_STATE_STRIDE` constants, are
  used identically from Task 3 through Task 5.
- **Scope check:** this plan produces exactly one deliverable (`work_graphs.py`, dispatch path
  only) — appropriately scoped as sub-project 1; the work-graph broadcasting-launch path and
  ImGui toggle are explicitly out of scope, to be planned separately once this is merged and
  verified.
- **API surface verified against the actual `_pydonut.pyi`/`_pydonut.cpp`, not assumed from the
  original C++ sample's nvrhi API.** A first draft of this plan (before this review pass)
  contained several real mismatches, all now corrected in the tasks above:
  - `nvrhi::BindingLayoutItem`/`BindingSetItem` have no `StructuredBuffer_UAV` — only
    `TypedBuffer_UAV` (single-format resources) was bound. Since `u_AnimStateData`/
    `u_LightData`/`u_CulledLightsDataRW` are `RWStructuredBuffer<T>` of a multi-field struct or a
    struct-strided scalar (not expressible as a single typed format), Task 1 now adds this
    missing binding — confirmed to already exist natively in nvrhi
    (`extern/donut/nvrhi/include/nvrhi/nvrhi.h:1947,2275`).
  - `BindingLayoutItem` has no `PushConstants` factory at all (only `BindingSetItem` does), so a
    manually-built shared `BindingLayoutDesc` (as originally drafted, copying the C++ sample's
    one-shared-layout approach) cannot declare a push-constant range. Task 4 was redesigned to
    use `pyd.CreateBindingSetAndLayout` once per pass instead, deriving each pass's own tailored
    layout from its `BindingSetDesc` — which also eliminates the C++ sample's null-placeholder
    resource pattern entirely (each pass now only binds what its own shader stage declares).
  - `GraphicsState` has no `vertexBuffers`/`indexBuffer` fields or an `addViewportAndScissorRect`
    method of its own — `addViewportAndScissorRect` lives on `viewport: ViewportState`, and
    vertex/index buffers are set via `addVertexBuffer(buffer, slot)`/`setIndexBuffer(buffer,
    format)`. `DrawArguments`/`VertexAttributeDesc` are plain read-write-field objects, not
    fluent `.setX()` builders (unlike nvrhi's own C++ API). Task 4/5 now use the confirmed shapes.
  - `CommandList` has no `copyTexture` method; blitting the LDR buffer to the backbuffer uses
    `CommonRenderPasses.BlitTexture` (confirmed signature), which needs a `ShaderFactory`/
    `RootFileSystem` mounted at donut's precompiled framework shaders — Task 4/5 add this,
    matching `variable_shading.py`'s exact mount pattern (`folder/"bin"/"shaders"/"framework"/
    GetShaderTypeName(api)`).
