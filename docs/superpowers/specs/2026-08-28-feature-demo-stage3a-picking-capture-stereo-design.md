# FeatureDemo port, Stage 3a: picking, capture and stereo — design

## Goal

Port the four remaining FeatureDemo features that do not involve light probes:
right-click **MaterialID picking**, **screenshots**, the **MipMapGen** test pass, and
**stereo rendering**. Picking retires the material dropdown that stage 2c introduced as
an explicit stand-in for it.

Reference sample: `E:\Gits\Donut-Samples\feature_demo\FeatureDemo.cpp`.

## Re-staging

Stage 3 was originally scoped as one "complete port" stage covering all five remaining
features. Light probes alone are roughly the size of all of stage 2c — a new `LightProbe`
struct, a seven-method `LightProbeProcessingPass`, the first bound Donut math type
(`dm::frustum`), `PrepareLights` gaining its currently-hardcoded `lightProbes` argument,
`CascadedShadowMap.SetupForCubemapView`, and a ~130-line `RenderLightProbe` that stands up
its own framebuffer, cubemap view, sky pass and forward pass. Splitting keeps each spec to
a normal size and each SDD run independently reviewable.

| Stage | Scope |
|---|---|
| 3a (this spec) | MaterialID picking, screenshots, MipMapGen, stereo |
| 3b | Light probes |

The five clusters are mutually independent — no ordering constraint between 3a and 3b.

Permanently out of scope regardless of stage: DLSS (no NGX SDK vendored), taskflow parallel
scene load, the ImGui console subsystem.

## MaterialID picking

The sample arms a pick on right mouse press (`FeatureDemo.cpp:516-526`), remembering the
cursor position recorded by `MousePosUpdate` (`:511`). An armed pick clears the MaterialIDs
target to `0xffff`, re-renders the scene through a `MaterialIDPass` into a dedicated
framebuffer — opaque draw strategy, plus the transparent one when translucency is enabled —
and captures one pixel (`:1039-1067`). After the command list executes, it reads the pixel
back and resolves it (`:1197-1228`): `.x` matches a material by `materialID`, `.y` matches a
mesh instance by `GetInstanceIndex()`, and the third-person camera is pointed at the picked
node (or at the scene root when nothing was hit).

### `MaterialIDPass` is nearly free

`MaterialIDPass` (`GBufferFillPass.h:148-159`) derives from `GBufferFillPass` and overrides
only `Init` and the protected `CreatePixelShader`. Since `GBufferFillPass`,
`GBufferFillPassCreateParameters` and `GBufferFillPassContext` are already bound, the new
class is a three-line `py::class_` declaring `GBufferFillPass` as its pybind11 base, plus a
constructor and `Init`. Its context type is `GBufferFillPassContext` — no new context class.

### The readback format is deliberately wider than the target

The sample constructs `PixelReadbackPass` with `nvrhi::Format::RGBA32_UINT`
(`FeatureDemo.cpp:803`) while `MaterialIDs` is `RG16_UINT` (`:124-127`). That is not a
mistake to "fix": the format argument selects the readback *buffer* layout and the compute
shader variant that writes it, not the source texture's format. Port it verbatim.

### `PointThirdPersonCameraAt` and the no-math-types rule

The sample's helper (`:659-667`) reads `node->GetGlobalBoundingBox()`, takes the box's
centre and half-diagonal, and derives an orbit distance from the vertical FOV. PyDonut binds
**no** Donut math types — vectors go in as flat scalars and come back as Python tuples
(`SceneGraphNode.GetWorldPosition` is the precedent). So `GetGlobalBoundingBox()` returns a
6-tuple `(minX, minY, minZ, maxX, maxY, maxZ)` and the arithmetic lives in Python:

```python
def PointThirdPersonCameraAt(self, node):
    minX, minY, minZ, maxX, maxY, maxZ = node.GetGlobalBoundingBox()
    cx, cy, cz = (minX + maxX) * 0.5, (minY + maxY) * 0.5, (minZ + maxZ) * 0.5
    dx, dy, dz = maxX - minX, maxY - minY, maxZ - minZ
    radius = math.sqrt(dx * dx + dy * dy + dz * dz) * 0.5
    distance = radius / math.sin(math.radians(CAMERA_VERTICAL_FOV_DEGREES * 0.5))
    thirdPerson = self.camera.GetThirdPersonCamera()
    thirdPerson.SetTargetPosition(cx, cy, cz)
    thirdPerson.SetDistance(distance)
    thirdPerson.Animate(0.0)
```

`Animate(0.0)` is load-bearing: `SetTargetPosition`/`SetDistance` only stage the values, and
the camera does not recompute its position until it animates. Dropping it leaves the camera
where it was, with no error.

## Screenshots

`SaveTextureToFile` (`TextureCache.h:243-249`) is a free function in `donut::engine`. Its
header requires that no immediate command list be open when it is called, which is why the
sample invokes it after `executeCommandList` (`FeatureDemo.cpp:1191-1195`). The Python port
must keep that ordering.

### `FileDialog` binds with a Python-shaped signature

`donut::app::FileDialog(bool bOpen, const char* pFilters, std::string& fileName)` takes a
double-NUL-terminated filter buffer (description, NUL, pattern, NUL, ..., trailing NUL) and
returns its result through an out-parameter. Both are hostile from Python — embedded NULs do
not survive a normal `str` conversion. It binds as:

```python
FileDialog(bOpen: bool, filters: list[tuple[str, str]]) -> str | None
```

with the packed buffer built C++-side from the `(description, pattern)` pairs, and `None`
for "cancelled". This is a deliberate signature change, not a literal port.

### Fallback when no dialog is available

On Windows `FileDialog` calls `GetSaveFileNameA`. On Linux it shells out to `zenity`
(`UserInterfaceUtils.cpp:74-88`), which may not be installed — this repo is also built and
run under WSL. A `None` return is therefore ambiguous between "user cancelled" and "no
dialog available", and the sample's behaviour (do nothing) would look like a broken button.

Instead: on `None`, fall back to the first unused `screenshot_NNNN.bmp` beside the script,
counting up from `0001`, and log the chosen path at info level. A cancelled dialog thus also
writes a file — accepted deliberately, because the alternative is a button that silently
does nothing on a machine without `zenity`, and the file is trivially deleted.

## MipMapGen

`MipMapGenPass` (`MipMapGenPass.h:43-79`) takes a texture that must already have been
allocated with mip levels. The sample gives `ResolvedColor` a full mip chain purely to
exercise the pass (`FeatureDemo.cpp:135`):

```python
mipLevels = int(math.floor(math.log2(max(width, height)))) + 1
```

`Dispatch` reduces LOD 0 into LOD 1 and up; `Display` blits the levels in a spiral to a
target framebuffer for debugging. Both run at the Render tail behind a `TestMipMapGen`
checkbox, as in `:1162-1166`.

## Stereo

`StereoPlanarView` is `StereoView<PlanarView>` (`View.h:337`) — two `PlanarView` members,
`LeftView` and `RightView`, with the composite-view interface fanning out over both. The
sample splits the framebuffer side by side: the left eye gets viewport
`(width * 0.5, height)`, the right gets `(width * 0.5 .. width, 0 .. height)`, both share one
projection built at **half** the full aspect ratio, and the right eye's view matrix is the
left's translated by 0.2 world units in X (`FeatureDemo.cpp:720-755`).

### The real cost: ten narrowed binding signatures

Ten bound call sites currently take a concrete `donut::engine::PlanarView&` where the C++
they wrap takes `const ICompositeView&` or `const IView&`. A stereo view cannot pass through
any of them. The bindings narrowed what Donut declares wide; widening them is a correctness
fix on its own merits, independent of stereo, and stage 3b's light probes need the same.

| # | Binding | Current | Target |
|---|---|---|---|
| 1 | `CommandList.clearTextureFloat` (view overload) | `PlanarView&` | `IView&` |
| 2 | `CommandList.clearDepthStencilTexture` (view overload) | `PlanarView&` | `IView&` |
| 3 | `GBufferRenderTargets.GetFramebuffer` | `PlanarView&` | `IView&` |
| 4 | `DeferredLightingPass.Render` | `PlanarView&` | `ICompositeView&` |
| 5 | `TemporalAntiAliasingPass.__init__` (`compositeView`) | `PlanarView&` | `ICompositeView&` |
| 6 | `TemporalAntiAliasingPass.RenderMotionVectors` (both params) | `PlanarView&` | `ICompositeView&` |
| 7 | `TemporalAntiAliasingPass.TemporalResolve` (both params) | `PlanarView&` | `ICompositeView&` |
| 8 | `CascadedShadowMap.SetupForPlanarView` | `PlanarView&` | `IView&` |
| 9 | `CascadedShadowMap.SetupForPlanarViewStable` | `PlanarView&` | `IView&` |
| 10 | `FramebufferFactory.GetFramebuffer` | `PlanarView&` | `IView&` |

`SkyPass.Render`, `SsaoPass.Render`, `ToneMappingPass.SimpleRender`, `BloomPass.Render` and
`RenderCompositeView` already take the wide type and need no change.

Widening is source-compatible for every existing Python caller: `PlanarView` is registered
with `IView` as its pybind11 base, so a `PlanarView` argument still converts. No change is
required in `deferred_shading.py`, `rt_bindless.py`, `threaded_rendering.py` or any existing
test — but they must all still pass, since they are what proves the widening is compatible.

### One of the ten is not mechanical

`SetupForPlanarViewStable` currently calls `view.GetInverseViewMatrix()`. `StereoView`
overrides that method to `assert(false); return dm::affine3::identity()` (`View.h:263-267`).
Asserts are compiled out in this project's Release build, so under stereo it would silently
hand the shadow fit an identity matrix and place every cascade at the world origin — no
crash, no error, just wrong shadows. This is the same silent-failure shape as stage 2b's
`SetRootNode` return-value trap.

The fix is what the sample does (`FeatureDemo.cpp:944`): take the inverse view matrix from
the first *planar* child view.

```cpp
.def("SetupForPlanarViewStable", [](donut::render::CascadedShadowMap &self,
        const donut::engine::DirectionalLight &light, const donut::engine::IView &view,
        float maxShadowDistance, float lightSpaceZUp, float lightSpaceZDown, float exponent) {
    RequireCascadeExponent("SetupForPlanarViewStable", exponent);
    // StereoView::GetInverseViewMatrix is assert(false) + identity (View.h:263-267), and
    // asserts compile out in Release -- so this must come from a planar child view, as
    // FeatureDemo.cpp:944 does. IView::GetChildView returns `this` for a PlanarView.
    const donut::engine::IView* planar =
        view.GetChildView(donut::engine::ViewType::PLANAR, 0);
    return self.SetupForPlanarViewStable(light, view.GetProjectionFrustum(),
        planar->GetInverseViewMatrix(), maxShadowDistance, lightSpaceZUp, lightSpaceZDown,
        exponent);
}, ...);
```

`GetProjectionFrustum` stays on the composite view: `StereoView` overrides it meaningfully,
merging the two eyes' frusta by taking the right eye's right plane (`View.h:246-255`).
`SetupForPlanarView` (the tight fit) uses `GetViewFrustum`, which `StereoView` also overrides
meaningfully (`:235-244`), so that one is pure widening.

### The stereo view shim

Stage 2c added `PlanarView.SetMatricesFromSwitchableCamera(camera, aspectRatio, ...)` so that
`dm::affine3` never crosses into Python. Stereo needs the same treatment, with the eye offset
applied C++-side:

```cpp
stereoPlanarView.def("SetMatricesFromSwitchableCamera", [](donut::engine::StereoPlanarView &self,
        const donut::app::SwitchableCamera &camera, float aspectRatio, float eyeSeparation,
        float verticalFovRadians, float zNear) {
    camera.GetSceneCameraProjectionParams(verticalFovRadians, zNear);
    const donut::math::float4x4 projection =
        donut::math::perspProjD3DStyleReverse(verticalFovRadians, aspectRatio, zNear);
    const donut::math::affine3 leftView = camera.GetWorldToViewMatrix();
    self.LeftView.SetMatrices(leftView, projection);
    donut::math::affine3 rightView = leftView;
    rightView.m_translation -= donut::math::float3(eyeSeparation, 0.f, 0.f);
    self.RightView.SetMatrices(rightView, projection);
}, py::arg("camera"), py::arg("aspectRatio"), py::arg("eyeSeparation") = 0.2f,
   py::arg("verticalFovRadians") = donut::math::PI_f * 0.25f, py::arg("zNear") = 0.1f);
```

`aspectRatio` is the **per-eye** aspect ratio — the caller passes `width / height * 0.5`,
matching `FeatureDemo.cpp:736`. The shim does not halve it itself, so that its contract stays
identical to the planar shim's.

`LeftView` and `RightView` bind as `reference_internal` properties: they are members of the
stereo view, and a copy would silently discard viewport and pixel-offset writes — the same
trap `SwitchableCamera.GetFirstPersonCamera` documents.

A copy constructor `StereoPlanarView(other)` binds too, mirroring `PlanarView`'s. It is how
`self.viewPrevious` takes its snapshot at the Render tail, matching `:753`.

## New native bindings (`src/cpp/_pydonut.cpp`)

### `MaterialIDPass(GBufferFillPass)`

```text
MaterialIDPass(device, commonPasses)
    .Init(shaderFactory, params)   # params: GBufferFillPassCreateParameters
```

Registered with `donut::render::GBufferFillPass` as its pybind11 base, `shared_ptr` holder.
Uses `GBufferFillPassContext` — no new context type.

### `PixelReadbackPass`

```text
PixelReadbackPass(device, shaderFactory, inputTexture, format, arraySlice=0, mipLevel=0)
    .Capture(commandList, x, y) -> None      # dm::uint2 flattened to two ints
    .ReadUInts()  -> tuple[int, int, int, int]
    .ReadFloats() -> tuple[float, float, float, float]
    .ReadInts()   -> tuple[int, int, int, int]
```

All three readers bind: they are one line each and the class is meaningless without the one
that matches the caller's format.

### `MipMapGenPass` and `MipMapGenPassMode`

```text
MipMapGenPassMode: MODE_COLOR | MODE_MIN | MODE_MAX | MODE_MINMAX
MipMapGenPass(device, shaderFactory, texture, mode=MipMapGenPassMode.MODE_MAX)
    .Dispatch(commandList, maxLOD=-1)
    .Display(commonPasses, commandList, target)   # target: Framebuffer
```

The enum is nested as `MipMapGenPass::Mode` in C++; it binds at module scope as
`MipMapGenPassMode`, matching how `GBufferFillPass::CreateParameters` binds as
`GBufferFillPassCreateParameters`. All four values bind, not just the one the sample uses —
per the stage 2c `MaterialDomain` finding, an enum read off arbitrary data must be complete.

### `StereoPlanarView(IView)`

```text
StereoPlanarView()
StereoPlanarView(other)                       # copy ctor, mirrors PlanarView's
    .LeftView  -> PlanarView                  # reference_internal property
    .RightView -> PlanarView                  # reference_internal property
    .SetMatricesFromSwitchableCamera(camera, aspectRatio, eyeSeparation=0.2,
                                     verticalFovRadians=PI/4, zNear=0.1)
```

`UpdateCache` is called per eye through the child views, as the sample does (`:748-749`);
`StereoView` has no `UpdateCache` of its own.

### `CommandList.clearTextureUInt(texture, clearValue)`

Mirrors the existing `clearTextureFloat` pair: an `AllSubresources` overload and a
view-taking overload using `view.GetSubresources()`.

### `SceneGraphNode.GetGlobalBoundingBox()`

Returns `(minX, minY, minZ, maxX, maxY, maxZ)`. Per the no-math-types rule.

### `SceneGraphNode.GetPath()`

Returns `str` via `GetPath().generic_string()` — `std::filesystem::path` does not cross into
Python. Drives the "Picked node:" log line (`:1224`).

### `SceneGraphLeaf.GetNodeSharedPtr()`

Declared on `SceneGraphLeaf` (`SceneGraph.h:65`), so `MeshInstance` inherits it. Returns
`SceneGraphNode | None` — it is a `weak_ptr::lock()`, which can legitimately return null for
a detached leaf.

### `SaveTextureToFile` and `FileDialog`

```text
SaveTextureToFile(device, commonPasses, texture, textureState, fileName,
                  saveAlphaChannel=True) -> bool
FileDialog(bOpen: bool, filters: list[tuple[str, str]]) -> str | None
```

Both module-level functions. `FolderDialog` stays unbound — nothing needs it.

### Ten widened signatures

Per the stereo table above. Every one is a parameter-type change plus, for
`SetupForPlanarViewStable`, the `GetChildView` correction. `_pydonut.pyi` mirrors all ten.

### Skipped

`MipMapGenPass`'s internal binding-set plumbing; `FolderDialog`; `StereoView`'s `GetChildView`
and the rest of the `IView` surface (nothing in Python calls them directly — the passes do,
in C++).

## `feature_demo.py` changes

### `UIData`

New fields: `Stereo = False`, `TestMipMapGen = False`, `ScreenshotFileName = ""`,
`SelectedNode = None`. `SelectedMaterial` already exists from stage 2c.

### `RenderTargets`

`MaterialIDs = makeColor(pyd.Format.RG16_UINT, "MaterialIDs", False)` — MSAA-matched
alongside `HdrColor`, matching `:124-127`. `MaterialIDFramebuffer` pairs it with the gbuffer
depth target, matching `:208-210`. `ResolvedColor`'s desc gains
`mipLevels = floor(log2(max(width, height))) + 1`; `makeSingleSampled` takes a `mipLevels`
argument defaulting to 1 so the other four single-sampled targets are unaffected.

### Input

`MousePosUpdate` records `self.pickPosition = (int(xpos), int(ypos))` unconditionally, as the
sample does (`:511`), so picking works while a scene camera is active. The sample wraps its
camera call in an `if (!m_ui.ActiveSceneCamera)` guard; the Python port has no such guard
because `SwitchableCamera` already routes input away from the user cameras when a scene
camera is active — so only the new pick lines are added, and the existing
`self.camera.MousePosUpdate(...)` call stays as it is.

`MouseButtonUpdate` sets `self.pick = True` on right press. No GLFW constants are bound —
the codebase convention is a raw numeric code with a naming comment
(`feature_demo.py:762`, `rt_bindless.py:198`, `threaded_rendering.py:197`):

```python
if button == 1 and action == 1:  # GLFW_MOUSE_BUTTON_2, GLFW_PRESS
    self.pick = True
```

### `CreateRenderPasses`

Builds `self.materialIDPass` (`Init` with the same `GBufferFillPassCreateParameters` the
gbuffer pass uses), `self.pixelReadbackPass` over `MaterialIDs` with `Format.RGBA32_UINT`, and
`self.mipMapGenPass` over `ResolvedColor` with `MODE_COLOR`.

### `SetupView`

Branches on `self.ui.Stereo`. When stereo and `self.view` is not already a `StereoPlanarView`,
replace both `self.view` and `self.viewPrevious` with fresh ones and mark the topology
changed; symmetrically for the planar case. Set the two eye viewports, call
`SetMatricesFromSwitchableCamera(self.camera, width / height * 0.5)`, `UpdateCache()` each
eye, and feed `LeftView` to the third-person camera (`:751`). On a topology change, copy the
current view into `viewPrevious` so the first stereo frame does not resolve against a planar
one (`:753`).

The Render tail's `self.viewPrevious = pyd.PlanarView(self.view)` becomes type-aware:
`pyd.StereoPlanarView(self.view)` when stereo.

### `Render`

The pick block goes between the shading passes and the sky pass, matching `:1039-1067`: clear
`MaterialIDs` to `0xffff`, `RenderCompositeView` opaque into `MaterialIDFramebuffer` with
`materialIDPass`, repeat with the transparent strategy when `EnableTranslucency`, then
`Capture(commandList, *self.pickPosition)`.

MipMapGen goes after tone mapping and before the final blit, matching `:1162-1166`.

The screenshot and pick-resolution blocks go after `executeCommandList`, matching
`:1191-1228` — the screenshot because `SaveTextureToFile` requires no open command list, the
pick because the readback buffer is not populated until the GPU has run. Pick resolution
clears `SelectedMaterial`/`SelectedNode`, matches `.x` against
`sceneGraph.GetMaterials()` by `materialID` and `.y` against `sceneGraph.GetMeshInstances()`
by `GetInstanceIndex()`, logs the node path, and points the third-person camera at the hit
node — or at the root when nothing matched.

### `buildUI`

The stage 2c material dropdown is removed; picking replaces it, as that spec anticipated. The
material editor window stays and is now driven entirely by the pick. Added, matching
`:1545, 1669-1680`: a `Stereo` checkbox, a `Screenshot` button, a `Test MipMapGen Pass`
checkbox, and a line showing the picked node's path.

## Testing

Existing baseline is 74 tests. New tests, all headless (no window, no device work beyond what
the existing suite already does):

`test/test_picking_bindings.py` (new)

- `MaterialIDPass` is a subclass of `GBufferFillPass` and is constructible.
- `PixelReadbackPass.ReadUInts`/`ReadFloats`/`ReadInts` each return a 4-tuple of the right
  element type.
- `SceneGraphNode.GetGlobalBoundingBox()` on a node with known geometry returns a 6-tuple
  whose mins are componentwise `<=` its maxes.
- `SceneGraphNode.GetPath()` returns a `str` reflecting the node's name and parentage.
- `SceneGraphLeaf.GetNodeSharedPtr()` returns the attaching node for an attached leaf, and
  `None` for a detached one.
- `CommandList.clearTextureUInt` accepts both overloads.

`test/test_capture_bindings.py` (new)

- All four `MipMapGenPassMode` values round-trip (`for mode in pyd.MipMapGenPassMode`).
- `MipMapGenPass` is constructible over a texture created with a mip chain.
- `FileDialog` is exposed with the documented signature and rejects a bad `filters` shape
  with `TypeError`. The dialog itself is **not** invoked — it is modal and would hang a
  headless run.
- `SaveTextureToFile` is exposed and returns `False` for an unwritable path rather than
  raising.

`test/test_stereo_bindings.py` (new)

- `StereoPlanarView` is constructible, copy-constructible, and is an `IView`.
- `LeftView`/`RightView` are live references: writing a viewport through
  `view.LeftView.SetViewport(...)` is visible on a second read of `view.LeftView`, proving
  `reference_internal` rather than a copy.
- `SetMatricesFromSwitchableCamera` runs without error and leaves the two eyes with
  *different* view extents — the observable proxy for the eye offset, since matrices do not
  cross into Python.
- A `StereoPlanarView` is accepted by each of the ten widened signatures that can be
  exercised without a live swap chain.

Regression: the full existing suite must pass unchanged. `deferred_shading.py`,
`rt_bindless.py` and `threaded_rendering.py` are the practical proof that the ten widened
signatures stayed source-compatible; their existing tests already cover the passes involved.

## Out of scope

Light probes (stage 3b). DLSS, taskflow parallel scene load, the ImGui console. Per-object
shadows and `SetupPerObjectShadow`. `SsaoPass`'s `CreateParameters` constructor and
`bindingSetIndex`. Visual verification of stereo, picking accuracy, or screenshot contents —
none of that is reachable from a headless test, and it is called out here so no reviewer
mistakes a green suite for proof the features look right on screen.
