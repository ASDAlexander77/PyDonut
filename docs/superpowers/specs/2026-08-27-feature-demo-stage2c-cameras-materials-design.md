# FeatureDemo port, Stage 2c: scene cameras and the material editor — design

## Goal

Give `feature_demo.py` a camera dropdown that switches between a first-person camera, a
third-person camera and the scene's own cameras, and a material editor window that edits any
material in the scene through Donut's own editor.

This is stage 2c. Stage 2b (spot and point lights) is complete and landed; see
[`2026-08-27-feature-demo-stage2b-lights-design.md`](2026-08-27-feature-demo-stage2b-lights-design.md),
whose [Re-staging](2026-08-27-feature-demo-stage2b-lights-design.md#re-staging-again) table this
spec closes out.

## Re-staging

Stage 2b's table already put scene cameras and the material editor in 2c. That split holds, and
this spec is the whole of it.

| Stage | Adds | Example state at end of stage |
| --- | --- | --- |
| **2c (this spec)** | `SwitchableCamera`, `SceneCamera`/`PerspectiveCamera`, `SceneGraph.GetCameras`/`GetMaterials`, `app::MaterialEditor`, `Material.materialID`, `SceneGraphNode.InvalidateContent` | + a camera dropdown over two synthesised scene cameras, the T-key toggle, and live material editing |
| **3** | unchanged from stage 1's table: `LightProbeProcessingPass` + `LightProbe`, `PixelReadbackPass`, `MipMapGenPass`, `MaterialIDPass`, `StereoPlanarView`, screenshots | The complete port |

## Camera switching: bind `SwitchableCamera`

`extern/donut` has grown a `SwitchableCamera` (`Camera.h:249`) that the reference
`FeatureDemo.cpp` predates. It bundles a `FirstPersonCamera`, a `ThirdPersonCamera` and an
optional scene camera, and owns the switching, the copy-the-view-across-a-switch behaviour, and
the routing of input events to whichever user camera is active.

The example binds it rather than porting the original's hand-rolled equivalent. This is the same
call stage 2b made for `LightEditor`: this repo calls Donut's helpers, it does not reimplement
their internals. It also avoids a binding this codebase does not want. The original's
`CopyActiveCameraToFirstPerson` (`FeatureDemo.cpp:452-464`) reads a scene camera's
`viewToWorld.m_translation` and `m_linear.row2`/`row1` — matrix component access, which the
flat-scalar convention rules out. `SwitchableCamera::SwitchToFirstPerson` does exactly that work
in C++ (`Camera.cpp:534-554`), so binding it removes the need for a matrix accessor rather than
forcing one.

The cost is structural divergence from the sample being ported: `m_ui.ActiveSceneCamera` plus
`m_ui.UseThirdPersonCamera` collapse into one object, and the original's `if
(!m_ui.ActiveSceneCamera)` input gating (`FeatureDemo.cpp:501-537`) becomes
`SwitchableCamera`'s own return value — its `KeyboardUpdate`/`MousePosUpdate`/
`MouseButtonUpdate`/`MouseScrollUpdate` all return `False` when a scene camera is active
(`Camera.cpp:585-650`), which is the same gate expressed as a result instead of a condition.

### Two defaults that will bite if the port is written literally

**`SwitchableCamera` starts in third person.** `m_UseFirstPerson` defaults to `false` and
`m_SceneCamera` starts null, so on a fresh object `IsThirdPersonActive()` is true
(`Camera.h:259-261`). The example starts first-person today, so `Init` must call
`SwitchToFirstPerson(copyView=False)` before positioning the camera. Passing `copyView=True`
here would copy from the default-constructed third-person camera (30 units back, aimed at the
origin) and quietly overwrite the `LookAt` that follows.

**`SwitchToSceneCamera` guards a null camera with an assert** (`Camera.cpp:578-582`), and this
project builds Release, so that assert compiles out and a null argument becomes a null
dereference at the next frame's `GetWorldToViewMatrix`. This is the same shape as the silent
`SetName` no-op stage 2b spent two fix rounds on. The binding therefore raises `ValueError` on
`None` instead of relying on the assert.

### The view shim

`SceneCamera` is a `SceneGraphLeaf`, not a `BaseCamera`, so the existing
`PlanarView.SetMatricesFromCamera` (`_pydonut.cpp:3009-3012`) cannot accept one, and
`SwitchableCamera::GetWorldToViewMatrix` returns a `dm::affine3` that must not cross into
Python.

A new `PlanarView.SetMatricesFromSwitchableCamera(camera, aspectRatio, verticalFovRadians,
zNear)` mirrors the existing shim's shape. Internally it takes the caller's fov and near plane,
lets `GetSceneCameraProjectionParams` (`Camera.h:278`) override both when a *perspective* scene
camera is active, and builds the same reverse-Z projection:

```cpp
// verticalFovRadians and zNear arrive by value, so the override writes into the local copies
camera.GetSceneCameraProjectionParams(verticalFovRadians, zNear);  // leaves both unchanged
                                                                   // unless a perspective
                                                                   // scene camera is active
self.SetMatrices(camera.GetWorldToViewMatrix(),
                 donut::math::perspProjD3DStyleReverse(verticalFovRadians, aspectRatio, zNear));
```

That is exactly what `FeatureDemo.cpp:700-715` does inline, kept on the C++ side of the
boundary. `SetMatricesFromCamera`, `SetMatricesOrbit` and the look-at variant are already
PyDonut-authored shims of this kind, so this follows the established pattern rather than
introducing one.

`ThirdPersonCamera.SetView` is already bound and must be called each frame after
`UpdateCache()`, as in the original (`FeatureDemo.cpp:773`) — the third-person camera needs the
view's projection to convert mouse movement into orbit and pan amounts.

## Synthesised scene cameras

`media/sponza-plus.scene.json` declares no cameras at all, so a faithful dropdown would list
only First-Person and Third-Person and nothing would exercise the new bindings. As in stage 2b,
where the same was true of lights, the example synthesises its own in `Init`.

`CreateSceneCameras()` builds two `PerspectiveCamera`s and attaches them to the root, following
`CreateSceneLights`' shape: construct, attach, *then* name and place. `SceneGraph::RegisterLeaf`
routes any `SceneCamera` into `m_Cameras` (`SceneGraph.cpp:577-582`), so an attached camera
reaches `GetCameras()` with no extra registration, exactly as an attached light reaches
`GetLights()`.

Two cameras rather than one, with different fields, so switching between them visibly changes
the projection and not merely the position:

| | Nave | Gallery |
| --- | --- | --- |
| name | `"Nave"` | `"Gallery"` |
| position | `(-8.0, 2.0, 0.0)` | `(0.0, 8.0, -4.0)` |
| direction | `(1.0, 0.0, 0.0)` | `(0.0, -0.4, 1.0)` |
| `verticalFov` | `radians(60)` | `radians(40)` |
| `zNear` | `0.1` | `0.1` |

`verticalFov` is in **radians** (`SceneGraph.h:158`), unlike `SpotLight`'s degrees — the values
above are written as `math.radians(...)` in the example so the unit is visible at the call site.

These positions are starting points chosen against Sponza's metre scale, to be tuned by eye at
the plan's run step — the same treatment stage 2b gave its light intensities.

## Material editing without picking

The original selects a material by right-clicking a mesh, reading `m_ui.SelectedMaterial` back
from a `MaterialIDPass` readback (`FeatureDemo.cpp:1684-1698`). That picking is stage 3.

Until it exists, the editor window gets a material **dropdown** built from
`SceneGraph.GetMaterials()`, listing every material by name. This is a deliberate, temporary
departure from the original: stage 3 replaces the combo with the viewport picking that drives it
in the real sample. The code says so at the combo, so a later reader can tell a placeholder from
a design decision.

Everything else follows the original. A separate top-right `"Material Editor"` window, gated on
a selection; a `Material %d: %s` header over `materialID` and `name`; the editor's return value
assigned to `material.dirty`; and a scene-content invalidation when the domain changes, because
a material moving between the opaque and alpha-blended domains changes which draw list its
geometry belongs to:

```python
previousDomain = material.domain
material.dirty = pyd.MaterialEditor(material, True)

if material.domain != previousDomain:
    self.app.scene.GetSceneGraph().GetRootNode().InvalidateContent()
```

Materials register through mesh geometry rather than as scene-graph leaves
(`SceneGraph.cpp:542`), so `GetMaterials()` returns what Sponza's meshes actually reference and
needs no synthesised entries of its own.

## New native bindings (`src/cpp/_pydonut.cpp`)

As in every prior stage: bound to exactly the surface the example calls, with every skipped
member listed so a later stage can tell a decision from an oversight.

### `SwitchableCamera`

Constructible. `SwitchToFirstPerson(copyView=True)`, `SwitchToThirdPerson(copyView=True)`,
`SwitchToSceneCamera(camera)`; `IsFirstPersonActive()`, `IsThirdPersonActive()`,
`IsSceneCameraActive()`; `GetSceneCamera()`, `GetFirstPersonCamera()`, `GetThirdPersonCamera()`;
`KeyboardUpdate`, `MousePosUpdate`, `MouseButtonUpdate`, `MouseScrollUpdate`, `Animate`.

`GetFirstPersonCamera`/`GetThirdPersonCamera` return C++ references into the
`SwitchableCamera`, so they bind with `py::return_value_policy::reference_internal` — the
returned wrapper must keep its owner alive, and must not be handed a copy.

### `SceneCamera(SceneGraphLeaf)` and `PerspectiveCamera(SceneCamera)`

`SceneCamera` (`SceneGraph.h:145-152`) binds base-only, with no constructor: it inherits
`SceneGraphLeaf::Clone()` pure (`SceneGraph.h:67`) and so is abstract, the same shape as `Light`.
`PerspectiveCamera` (`SceneGraph.h:154-165`) is constructible with `zNear` and `verticalFov`.

### `SceneGraphNode.SetPositionAndDirection(px, py, pz, dx, dy, dz)`

Placing a synthesised camera needs one binding this spec did not originally anticipate.
`SetPosition` and `SetDirection` are declared on `Light` (`SceneGraph.h:199-200`), **not** on
`SceneGraphLeaf`, so a `PerspectiveCamera` does not inherit the setters `CreateSceneLights` uses.
Their bodies (`SceneTypes.cpp:77-116`) are generic node-transform work — invert the parent
transform, `lookatZ` the direction, `decomposeAffine`, `SetTransform` — so the equivalent binds
once on `SceneGraphNode`, where the transform actually lives, and `CreateSceneCameras` calls it
on the node `AttachLeafNode` returns.

Composing `dm` math inside a shim like this is an established pattern in this file
(`SetMatricesOrbit`, `setTransformScaleTranslation`) and keeps the math types in C++; it is not
the same thing as reimplementing a Donut *pass*, which this project does not do.

### `SceneGraph.GetCameras()` and `SceneGraph.GetMaterials()`

`GetCameras` (`SceneGraph.h:556`) returns a plain vector and binds directly. `GetMaterials`
(`SceneGraph.h:548`) returns a `ResourceTracker<Material>`, which `pybind11/stl.h` cannot convert
automatically, so it is copied into a plain vector — the same treatment `GetMeshes` already gets
(`_pydonut.cpp:2382-2387`).

### `Material.materialID`, `SceneGraphNode.InvalidateContent()`, `MaterialEditor`

`materialID` (`SceneTypes.h:255`) is assigned by the scene graph and only read by the editor's
header, so it binds read-only. `InvalidateContent` (`SceneGraph.h:321`) is what the domain-change
path needs. `MaterialEditor(material, allowMaterialDomainChanges) -> bool`
(`UserInterfaceUtils.h:42`) is a free function over `donut::app::MaterialEditor`, the same shape
as stage 2b's `LightEditor` — and, like it, drawn into whatever ImGui window is current.

### `ImGui.SetNextWindowPos` gains a pivot

The original right-aligns the editor window with a pivot of `(1, 0)` (`FeatureDemo.cpp:1687`).
The bound `SetNextWindowPos(x, y, cond)` has no pivot parameter, and the window's width is not
knowable in Python before it is drawn. The existing binding therefore gains two optional
arguments, `pivotX=0.0`, `pivotY=0.0`, which is backward-compatible with its current callers.

### Skipped

- `SwitchableCamera.GetActiveUserCamera`, `GetWorldToViewMatrix` — the first is an internal
  detail of the input routing that is already bound; the second returns a matrix, which the view
  shim consumes in C++.
- `SwitchToThirdPerson`'s `targetDistance` — the original's suggested value is the distance to
  the object in the centre of the view, which needs the depth readback that stage 3 adds.
- `SwitchableCamera.JoystickUpdate`, `JoystickButtonUpdate` — no example handles joystick input.
- `OrthographicCamera` (`SceneGraph.h:167-178`) — nothing constructs one, and the projection
  shim only handles the perspective case.
- `PerspectiveCamera.zFar`, `aspectRatio` — `std::optional<float>` fields; the example leaves
  both unset, taking the reverse-infinite projection and the viewport's aspect ratio.
- `SceneCamera.GetViewToWorldMatrix`, `GetWorldToViewMatrix` — matrices; `SwitchableCamera`
  consumes them internally.
- `PerspectiveCamera.Clone`, `Load`, `SetProperty` — the JSON and animation paths, which the
  example does not drive.
- `MaterialEditor_*` helpers, `FileDialog`, `FolderDialog` — the dialogs belong to stage 3's
  screenshot path.

## `feature_demo.py` changes

### Camera

`self.camera` becomes a `SwitchableCamera`. `Init` switches to first person explicitly, then
positions it through the owned camera:

```python
self.camera.SwitchToFirstPerson(copyView=False)
firstPerson = self.camera.GetFirstPersonCamera()
firstPerson.LookAt(0.0, 1.8, 0.0, 1.0, 1.8, 0.0)
firstPerson.SetMoveSpeed(3.0)
```

The four existing input paths (`feature_demo.py:705`, `:709`, `:713`, `:721`) keep calling
`self.camera`, now dispatching through the switchable camera. Two additions: a
`MouseScrollUpdate` override, which the example does not currently have at all and which
third-person zoom needs, and the T-key toggle from `FeatureDemo.cpp:486-499` — with a scene
camera active T returns to a user camera, otherwise it swaps first and third person.

`SetupView` replaces `SetMatricesFromCamera` (`feature_demo.py:770`) with
`SetMatricesFromSwitchableCamera`, and adds
`self.camera.GetThirdPersonCamera().SetView(self.view)` after `UpdateCache()`.

### The camera dropdown

A `BeginCombo("Camera (T)", ...)` in the existing settings window, mirroring
`FeatureDemo.cpp:1548-1570`: a `"First-Person"` entry, a `"Third-Person"` entry, then one
`Selectable` per `GetCameras()` entry. Each selection calls the matching `SwitchTo*`, and the
preview text is the active scene camera's name or `"First-Person"`/`"Third-Person"`.

As in stage 2b's light dropdown, selection is driven by `Selectable`'s return value rather than
the original's mutate-and-test pattern, because the bound `Selectable(label, selected) -> bool`
returns the click.

### The material editor window

A second ImGui window, outside the settings window's `Begin`/`End`, holding the material combo
and the editor. `self.selectedMaterial` lives on `UIRenderer` beside `self.selectedLight`, for
the same reason: nothing outside the UI reads it.

The window's contents are wrapped in `PushID`/`PopID`, as the Lights section already is —
`MaterialEditor` emits generically-labelled controls, and the final review of stage 2b found a
real ID collision between `LightEditor`'s `"Radius"` slider and the SSAO section's.

## Testing

`test/test_camera_bindings.py` and `test/test_material_bindings.py`, following
`test_light_bindings.py`: GPU-free, no device, nothing rendered.

`SwitchableCamera`'s state machine is genuinely testable without a device — construct, switch,
assert which `Is*Active` predicate holds. That includes a test pinning the third-person default
described above, so the trap cannot regress silently, and a test that `SwitchToSceneCamera(None)`
raises `ValueError` rather than crashing.

`GetCameras` gets the same most-derived-type test the lights got: attaching a `PerspectiveCamera`
and reading it back must yield a `PerspectiveCamera`, since the dropdown's `is` comparison and
the projection shim's `dynamic_pointer_cast` both depend on it.

`MaterialEditor` needs a live ImGui frame and cannot be called from a test; it gets a presence
check, as `LightEditor` did. `GetMaterials` needs a loaded scene, so it is verified by running
the example rather than by a test.

Scene-camera *rendering* — that switching actually changes the view — needs a GPU and a window,
so it is a manual verification step in the plan, as stage 2b's lighting was.

## Out of scope

MaterialID picking and everything else deferred to stage 3; `OrthographicCamera`; joystick
input; stereo (`StereoPlanarView` is stage 3, and the camera work here touches only the planar
path); and camera animation, which the scene's animation path would drive rather than the UI.
