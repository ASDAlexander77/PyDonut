# FeatureDemo Stage 2c (scene cameras and the material editor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind Donut's `SwitchableCamera`, `SceneCamera`/`PerspectiveCamera` and `app::MaterialEditor`, and give `feature_demo.py` a camera dropdown over two synthesised scene cameras plus a material editor window.

**Architecture:** Three binding tasks extend the single pybind11 translation unit `src/cpp/_pydonut.cpp`, then three tasks grow `feature_demo.py`. Camera switching is delegated wholesale to Donut's `SwitchableCamera` rather than hand-rolled in Python, which keeps view matrices on the C++ side of the boundary; a new `PlanarView.SetMatricesFromSwitchableCamera` shim is the only place they are touched.

**Tech Stack:** C++20, pybind11 3.x, NVRHI, Donut (vendored at `extern/donut`), scikit-build-core + uv, Python 3.14, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-feature-demo-stage2c-cameras-materials-design.md`

## Global Constraints

- **Donut math types are never exposed to Python.** `dm::float3`, `dm::affine3`, `dm::float4x4` etc. are decomposed into flat scalars, or consumed entirely inside a C++ shim. Precedent: `PlanarView.SetMatricesFromCamera` (`src/cpp/_pydonut.cpp:3009-3012`), `Light.SetDirection`.
- **Bind only what the example calls.** Every skipped constructor/method carries a comment saying it was skipped and why, so a later stage can tell a decision from an oversight.
- **Three files stay in sync for every new top-level name:** `src/cpp/_pydonut.cpp` (the binding), `src/pydonut/_pydonut.pyi` (the type stub), `src/pydonut/__init__.py` (the `from pydonut._pydonut import X` line **and** the `__all__` entry). Adding a *method* to an existing class touches only the first two.
- **Rebuild command is `uv sync`.** It rebuilds the native module in place; `src/cpp/**` is a cache key (`pyproject.toml:26`). Tests run with `uv run pytest`. A binding change is not testable until `uv sync` has run.
- **Tests are GPU-free.** No device is created and nothing is rendered, matching `test/test_light_bindings.py`. Anything needing a device or a live ImGui frame is verified by running the example instead.
- **Every new Python file starts with the repo's license header** — copy it verbatim from the top of `test/test_light_bindings.py` (lines 1-22).
- **Baseline test count is 55** (`uv run pytest -q` on the commit this plan starts from). Each task states the new expected total.
- **Attach before you place, and attach before you name.** `Light`/`SceneGraphLeaf` setters that write through the owning node — `SetPosition`, `SetDirection`, `SetName` — assert or silently no-op when the leaf has no node (`SceneTypes.cpp:82`, `:100`; `SceneGraph.cpp:40-47`). This project builds Release, so those asserts compile out and the failure is silent.
- **Never use `SceneGraph.SetRootNode`'s return value as a node.** It returns the *previous* root (`SceneGraph.cpp:670-679`), which is `None` on a fresh graph. Call `SetRootNode(...)` then `GetRootNode()`. Two separate tasks in the stage 2b plan hit this.
- **`verticalFov` on `PerspectiveCamera` is in radians**, unlike `SpotLight`'s degrees (`SceneGraph.h:158`).

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `src/cpp/_pydonut.cpp` | modify | All bindings. Insertion points: `Material` (line 2148), after `PointLight` (ends line 2344), `SceneGraphNode` (line 2354), `SceneGraph` (line 2365), after `ThirdPersonCamera` (ends line 2982), `planarView` shims (after line 3012), `ImGui.SetNextWindowPos` (line 3201-3203), after the `LightEditor` free function (ends line 3285). |
| `src/pydonut/_pydonut.pyi` | modify | Type stubs, mirroring each binding. |
| `src/pydonut/__init__.py` | modify | Re-export line + `__all__` entry for `SceneCamera`, `PerspectiveCamera`, `SwitchableCamera`, `MaterialEditor`. |
| `test/test_camera_bindings.py` | create | GPU-free surface tests for the camera half of this stage. A new file, not an extension of `test_light_bindings.py`, which is named for stage 2b's subject. |
| `test/test_material_bindings.py` | create | GPU-free surface tests for the material half. Separate from the camera file because the two halves share no fixtures and a reviewer should be able to reject one without the other. |
| `feature_demo.py` | modify | The example. Grows by `CreateSceneCameras`, a camera dropdown, a material editor window, and the `SwitchableCamera` swap. |

**Line numbers throughout this plan are from the commit the plan starts from.** Each task's insertions shift the ones below it, so locate every insertion point by the quoted anchor text, not by the number.

---

### Task 1: `SceneCamera`, `PerspectiveCamera`, `SceneGraph.GetCameras`

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (after the `PointLight` binding, which ends line 2344; and the `SceneGraph` class binding, line 2365)
- Modify: `src/pydonut/_pydonut.pyi` (after the `PointLight` stub; and the `SceneGraph` stub)
- Modify: `src/pydonut/__init__.py` (two import lines, two `__all__` entries)
- Test: `test/test_camera_bindings.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `pyd.SceneCamera` (abstract, not constructible); `pyd.PerspectiveCamera()` with `zNear: float` and `verticalFov: float`, deriving from `pyd.SceneCamera` → `pyd.SceneGraphLeaf`; `SceneGraph.GetCameras() -> list[SceneCamera]`; `SceneGraphNode.SetPositionAndDirection(px, py, pz, dx, dy, dz) -> None`. Task 2's `SwitchToSceneCamera` takes a `SceneCamera`; tasks 4 and 5 construct `PerspectiveCamera`, call `GetCameras`, and place cameras with `SetPositionAndDirection`.

**Why `SetPositionAndDirection` is needed:** `SetPosition` and `SetDirection` are declared on `Light` (`SceneGraph.h:199-200`), **not** on `SceneGraphLeaf`, so a `PerspectiveCamera` does not inherit them and cannot be placed the way `CreateSceneLights` places a light. Their bodies (`SceneTypes.cpp:77-116`) are generic node-transform work — invert the parent transform, `lookatZ` the direction, `decomposeAffine`, `SetTransform` — so this task binds one equivalent on `SceneGraphNode`, where the transform actually lives. Composing `dm` math inside a shim is an established pattern in this file (`SetMatricesOrbit`, `setTransformScaleTranslation`), unlike reimplementing a Donut *pass*.

- [ ] **Step 1: Write the failing test**

Create `test/test_camera_bindings.py`. Copy lines 1-22 of `test/test_light_bindings.py` verbatim as the license header, then:

```python
"""Surface tests for the FeatureDemo stage 2c camera bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a field that silently did not round-trip, a reference-returning getter that hands
back a copy.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def _graph_with_root() -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Returns a fresh graph and its real root node.

    SetRootNode returns the *previous* root (SceneGraph.cpp:670-679) -- None on a fresh
    graph -- so the root has to be read back with GetRootNode(). Passing SetRootNode's
    result as AttachLeafNode's parent silently re-roots the graph on every attach instead
    of adding siblings.
    """
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    return graph, graph.GetRootNode()


def test_scene_camera_is_not_constructible() -> None:
    # SceneCamera inherits SceneGraphLeaf::Clone() pure (SceneGraph.h:67) and does not
    # override it, so it is abstract and binds base-only -- the same shape as Light.
    with pytest.raises(TypeError):
        pyd.SceneCamera()


def test_perspective_camera_is_a_scene_camera() -> None:
    assert issubclass(pyd.PerspectiveCamera, pyd.SceneCamera)


def test_perspective_camera_is_a_scene_graph_leaf() -> None:
    # The dropdown labels cameras with SceneGraphLeaf.GetName, and CreateSceneCameras
    # attaches them with AttachLeafNode -- both need this inheritance edge to be registered.
    assert issubclass(pyd.PerspectiveCamera, pyd.SceneGraphLeaf)


def test_perspective_camera_fields_round_trip() -> None:
    camera = pyd.PerspectiveCamera()
    camera.zNear = 0.1
    camera.verticalFov = 1.047  # radians, NOT degrees (SceneGraph.h:158)
    # approx: these are C++ floats, so neither value survives a round trip exactly.
    assert camera.zNear == pytest.approx(0.1)
    assert camera.verticalFov == pytest.approx(1.047)


def test_get_cameras_returns_the_concrete_camera_types() -> None:
    # SwitchableCamera.GetSceneCameraProjectionParams dynamic_pointer_casts to
    # PerspectiveCamera (Camera.cpp:522-532), and the dropdown's `is` check compares against
    # the stored selection -- both need pybind to hand back the most-derived registered type.
    graph, root = _graph_with_root()

    nave = pyd.PerspectiveCamera()
    gallery = pyd.PerspectiveCamera()
    graph.AttachLeafNode(root, nave)
    graph.AttachLeafNode(root, gallery)
    nave.SetName("Nave")
    gallery.SetName("Gallery")

    cameras = graph.GetCameras()
    assert [camera.GetName() for camera in cameras] == ["Nave", "Gallery"]
    assert isinstance(cameras[0], pyd.PerspectiveCamera)
    assert cameras[0] is nave
    assert cameras[1] is gallery


def test_set_position_and_direction_writes_the_nodes_world_transform() -> None:
    # Light.SetPosition/SetDirection are declared on Light (SceneGraph.h:199-200), not on
    # SceneGraphLeaf, so a camera cannot be placed the way a light is. This node-level
    # equivalent is how CreateSceneCameras positions its cameras.
    #
    # SetTranslation only marks the node dirty, so the world transform GetWorldPosition reads
    # back is the one Refresh recomputes.
    graph, root = _graph_with_root()
    camera = pyd.PerspectiveCamera()
    node = graph.AttachLeafNode(root, camera)

    node.SetPositionAndDirection(-8.0, 2.0, 0.0, 1.0, 0.0, 0.0)
    graph.Refresh(0)

    assert node.GetWorldPosition() == pytest.approx((-8.0, 2.0, 0.0))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_camera_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'SceneCamera'`.

- [ ] **Step 3: Add the camera class bindings**

In `src/cpp/_pydonut.cpp`, immediately after the `PointLight` binding (it ends with the line `.def_readwrite("range", &donut::engine::PointLight::range);`), insert:

```cpp
    // SceneCamera (SceneGraph.h:145-152) is abstract: it inherits SceneGraphLeaf::Clone()
    // pure (SceneGraph.h:67) and does not override it. Bound base-only with no constructor,
    // the same shape as Light above, so GetCameras() can hand back concrete subtypes and so
    // SwitchableCamera.SwitchToSceneCamera can accept them.
    //
    // GetViewToWorldMatrix and GetWorldToViewMatrix stay unbound: both return dm::affine3,
    // which SwitchableCamera consumes internally (see SetMatricesFromSwitchableCamera).
    py::class_<donut::engine::SceneCamera, donut::engine::SceneGraphLeaf,
               std::shared_ptr<donut::engine::SceneCamera>>(m, "SceneCamera");

    // PerspectiveCamera (SceneGraph.h:154-165). NOTE verticalFov is in RADIANS, unlike
    // SpotLight's innerAngle/outerAngle, which are degrees.
    //
    // zFar and aspectRatio stay unbound: both are std::optional<float>, and the example
    // leaves them unset to get the reverse-infinite projection and the viewport's own aspect
    // ratio. Clone, Load and SetProperty stay unbound too -- the JSON and animation paths,
    // which no example drives. OrthographicCamera (SceneGraph.h:167-178) is unbound entirely:
    // nothing constructs one, and the projection shim only handles the perspective case.
    py::class_<donut::engine::PerspectiveCamera, donut::engine::SceneCamera,
               std::shared_ptr<donut::engine::PerspectiveCamera>>(m, "PerspectiveCamera")
        .def(py::init<>())
        .def_readwrite("zNear", &donut::engine::PerspectiveCamera::zNear)
        .def_readwrite("verticalFov", &donut::engine::PerspectiveCamera::verticalFov);
```

- [ ] **Step 4: Add `GetCameras` to the `SceneGraph` binding**

In `src/cpp/_pydonut.cpp`, in the `SceneGraph` class binding, immediately after the `.def("GetLights", &donut::engine::SceneGraph::GetLights)` line, insert:

```cpp
        // Scene cameras attached anywhere in the graph. SceneGraph::RegisterLeaf routes any
        // SceneCamera into m_Cameras (SceneGraph.cpp:577-582), so a camera attached with
        // AttachLeafNode shows up here with no extra registration -- exactly as a light does.
        .def("GetCameras", &donut::engine::SceneGraph::GetCameras)
```

- [ ] **Step 4b: Add `SetPositionAndDirection` to the `SceneGraphNode` binding**

`Light::SetPosition`/`SetDirection` are declared on `Light` (`SceneGraph.h:199-200`), not on `SceneGraphLeaf`, so a `PerspectiveCamera` does not inherit them. Their bodies are generic node-transform work, so bind one equivalent on the node itself.

In `src/cpp/_pydonut.cpp`, in the `SceneGraphNode` class binding, immediately after the `.def("SetName", &donut::engine::SceneGraphNode::SetName, py::arg("name"))` line, insert:

```cpp
        // Places the node at a world position, oriented along a world direction. This is what
        // Light::SetPosition and Light::SetDirection do (SceneTypes.cpp:77-116), lifted to the
        // node because those two are declared on Light (SceneGraph.h:199-200) and so are not
        // available on a SceneCamera -- CreateSceneCameras needs exactly this for the cameras
        // it synthesises.
        //
        // Both halves are done together because they share the parent-transform inversion, and
        // because Light does them as one pair in practice: attach, then position, then aim.
        // Composing dm math inside a shim follows SetMatricesOrbit and
        // setTransformScaleTranslation elsewhere in this file -- the math types stay in C++.
        .def("SetPositionAndDirection", [](donut::engine::SceneGraphNode &self,
                double px, double py, double pz, double dx, double dy, double dz) {
            donut::engine::SceneGraphNode *parent = self.GetParent();
            donut::math::daffine3 parentToWorld = donut::math::daffine3::identity();
            if (parent)
                parentToWorld = donut::math::daffine3(parent->GetLocalToWorldTransform());

            const donut::math::double3 translation =
                inverse(parentToWorld).transformPoint(donut::math::double3(px, py, pz));

            const donut::math::daffine3 worldToLocal =
                donut::math::lookatZ(donut::math::double3(dx, dy, dz));
            const donut::math::daffine3 localToParent = inverse(worldToLocal * parentToWorld);

            donut::math::dquat rotation;
            donut::math::double3 scaling;
            donut::math::decomposeAffine<double>(localToParent, nullptr, &rotation, &scaling);

            self.SetTransform(&translation, &rotation, &scaling);
        }, py::arg("px"), py::arg("py"), py::arg("pz"), py::arg("dx"), py::arg("dy"), py::arg("dz"))
```

**Note the missing semicolon** — this `.def(...)` goes into the *middle* of the `SceneGraphNode` chain, which still ends at the existing `GetWorldPosition` entry's `});`. Inserting a `;` here would orphan every `.def` below it and fail to compile.

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, immediately after the `PointLight` stub class, insert:

```python
# A camera stored in the scene graph. Abstract (SceneGraphLeaf.Clone is pure and SceneCamera
# does not override it), so it cannot be constructed -- it exists so GetCameras() can return
# concrete subtypes and SwitchableCamera.SwitchToSceneCamera can accept them. Its position and
# orientation come from the owning scene-graph node.
class SceneCamera(SceneGraphLeaf): ...

# A perspective scene camera. verticalFov is in RADIANS, unlike SpotLight's degrees. zFar and
# aspectRatio are left unbound, so the projection is reverse-infinite and takes the viewport's
# aspect ratio. Position and direction come from the owning scene-graph node: place it with
# SceneGraphNode.SetPositionAndDirection on the node AttachLeafNode returns. Light's own
# SetPosition/SetDirection are declared on Light, so a camera does not inherit them.
class PerspectiveCamera(SceneCamera):
    def __init__(self: PerspectiveCamera) -> None: ...
    zNear: float
    verticalFov: float
```

And in the `SceneGraph` stub class, immediately after the `GetLights` line, add:

```python
    # Scene cameras attached anywhere in the graph -- populated by AttachLeafNode, the same
    # way GetLights is.
    def GetCameras(self: SceneGraph) -> list[SceneCamera]: ...
```

And in the `SceneGraphNode` stub class, after `SetName`, add:

```python
    # Places the node at a world position, oriented along a world direction -- what
    # Light.SetPosition/SetDirection do, lifted to the node because those two are declared on
    # Light and so are unavailable on a SceneCamera. Call it *after* attaching the node: it
    # reads the parent's transform to convert world space to parent-local.
    def SetPositionAndDirection(self: SceneGraphNode, px: float, py: float, pz: float, dx: float, dy: float, dz: float) -> None: ...
```

- [ ] **Step 6: Re-export from `__init__.py`**

In `src/pydonut/__init__.py`, after the line `from pydonut._pydonut import PointLight`, add:

```python
from pydonut._pydonut import SceneCamera
from pydonut._pydonut import PerspectiveCamera
```

And in `__all__`, after the `'PointLight',` entry, add:

```python
    'SceneCamera',
    'PerspectiveCamera',
```

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`
Expected: 61 passed (55 baseline + 6 new).

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_camera_bindings.py
git commit -m "Bind SceneCamera, PerspectiveCamera and SceneGraph.GetCameras"
```

---

### Task 2: `SwitchableCamera` and the view shim

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (after the `ThirdPersonCamera` binding, which ends line 2982; and after the `SetMatricesFromCamera` shim, line 3012)
- Modify: `src/pydonut/_pydonut.pyi` (after the `ThirdPersonCamera` stub; and in the `PlanarView` stub)
- Modify: `src/pydonut/__init__.py` (one import line, one `__all__` entry)
- Test: `test/test_camera_bindings.py` (append)

**Interfaces:**
- Consumes: `pyd.SceneCamera`, `pyd.PerspectiveCamera` from task 1.
- Produces: `pyd.SwitchableCamera()` with `SwitchToFirstPerson(copyView=True)`, `SwitchToThirdPerson(copyView=True)`, `SwitchToSceneCamera(sceneCamera)`, `IsFirstPersonActive()`, `IsThirdPersonActive()`, `IsSceneCameraActive()`, `GetSceneCamera()`, `GetFirstPersonCamera()`, `GetThirdPersonCamera()`, `KeyboardUpdate(key, scancode, action, mods)`, `MousePosUpdate(xpos, ypos)`, `MouseButtonUpdate(button, action, mods)`, `MouseScrollUpdate(xoffset, yoffset)`, `Animate(deltaT)`; and `PlanarView.SetMatricesFromSwitchableCamera(camera, aspectRatio, verticalFovRadians=PI/4, zNear=0.1)`. Tasks 4 and 5 use all of these.

- [ ] **Step 1: Write the failing test**

Append to `test/test_camera_bindings.py`:

```python
def test_switchable_camera_starts_in_third_person() -> None:
    # m_UseFirstPerson defaults to false and m_SceneCamera starts null (Camera.h:259-261), so
    # a fresh SwitchableCamera is in THIRD person. The example starts first-person, so Init
    # must switch explicitly. Pinned here because getting it wrong changes the example's
    # starting camera silently, with nothing else to catch it.
    camera = pyd.SwitchableCamera()
    assert camera.IsThirdPersonActive()
    assert not camera.IsFirstPersonActive()
    assert not camera.IsSceneCameraActive()


def test_switch_to_first_person_makes_it_active() -> None:
    camera = pyd.SwitchableCamera()
    camera.SwitchToFirstPerson(copyView=False)
    assert camera.IsFirstPersonActive()
    assert not camera.IsThirdPersonActive()


def test_get_first_person_camera_returns_the_owned_camera_not_a_copy() -> None:
    # Bound with return_value_policy::reference_internal. If it handed back a copy instead,
    # Init's LookAt/SetMoveSpeed would be written to a temporary and thrown away -- the
    # example would silently start at the origin. Two separate calls must see one object.
    camera = pyd.SwitchableCamera()
    camera.GetFirstPersonCamera().LookAt(0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    assert camera.GetFirstPersonCamera().GetDir() == pytest.approx((1.0, 0.0, 0.0))


def test_switch_to_scene_camera_activates_the_scene_camera() -> None:
    graph, root = _graph_with_root()
    sceneCamera = pyd.PerspectiveCamera()
    graph.AttachLeafNode(root, sceneCamera)

    camera = pyd.SwitchableCamera()
    camera.SwitchToSceneCamera(sceneCamera)

    assert camera.IsSceneCameraActive()
    assert not camera.IsFirstPersonActive()
    assert not camera.IsThirdPersonActive()
    assert camera.GetSceneCamera() is sceneCamera


def test_switch_to_scene_camera_rejects_none() -> None:
    # C++ guards this with assert(!!sceneCamera) (Camera.cpp:578-582), which compiles out in
    # this project's Release build -- a None would become a null dereference on the next
    # frame's GetWorldToViewMatrix rather than an error here.
    camera = pyd.SwitchableCamera()
    with pytest.raises(ValueError):
        camera.SwitchToSceneCamera(None)


def test_set_matrices_from_switchable_camera_accepts_every_camera_state() -> None:
    # No device needed: PlanarView and SwitchableCamera are both constructible standalone and
    # this only computes matrices. PlanarView exposes no matrix getters, so this asserts the
    # shim runs rather than checking the values -- including the scene-camera branch, where
    # GetSceneCameraProjectionParams overrides fov and zNear. The rendered result is a manual
    # check in tasks 4-5.
    graph, root = _graph_with_root()
    sceneCamera = pyd.PerspectiveCamera()
    graph.AttachLeafNode(root, sceneCamera)
    sceneCamera.verticalFov = 0.7
    sceneCamera.zNear = 0.2

    view = pyd.PlanarView()
    camera = pyd.SwitchableCamera()

    camera.SwitchToFirstPerson(copyView=False)
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0)

    camera.SwitchToThirdPerson(copyView=False)
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0)

    camera.SwitchToSceneCamera(sceneCamera)
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_camera_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'SwitchableCamera'`.

- [ ] **Step 3: Add the `SwitchableCamera` binding**

In `src/cpp/_pydonut.cpp`, immediately after the last `thirdPersonCamera.def(...)` line (`thirdPersonCamera.def("MouseScrollUpdate", &donut::app::ThirdPersonCamera::MouseScrollUpdate, py::arg("xoffset"), py::arg("yoffset"));`), insert:

```cpp
    // SwitchableCamera (Camera.h:249) bundles a FirstPersonCamera, a ThirdPersonCamera and an
    // optional scene camera, and owns the switching, the copy-the-view-across-a-switch
    // behaviour, and the routing of input to whichever user camera is active. Bound rather
    // than reimplemented in Python for the same reason LightEditor was -- this repo calls
    // Donut's helpers rather than porting their internals -- and because doing it in Python
    // would need a matrix accessor this codebase deliberately does not have: the reference
    // sample's CopyActiveCameraToFirstPerson (FeatureDemo.cpp:452-464) reads viewToWorld
    // matrix components, which is exactly the work SwitchToFirstPerson does in C++
    // (Camera.cpp:534-554).
    //
    // The input methods return False when a scene camera is active (Camera.cpp:585-650),
    // which is the same gate the reference sample writes as `if (!m_ui.ActiveSceneCamera)`.
    //
    // NOTE: a default-constructed SwitchableCamera is in THIRD person -- m_UseFirstPerson
    // defaults to false and m_SceneCamera starts null (Camera.h:259-261). A caller that wants
    // to start in first person must say so explicitly.
    py::class_<donut::app::SwitchableCamera>(m, "SwitchableCamera")
        .def(py::init<>())
        .def("SwitchToFirstPerson", &donut::app::SwitchableCamera::SwitchToFirstPerson,
            py::arg("copyView") = true)
        // targetDistance stays unbound: the value the C++ suggests is the distance to the
        // object in the centre of the view, which needs the depth readback stage 3 adds.
        .def("SwitchToThirdPerson", [](donut::app::SwitchableCamera &self, bool copyView) {
            self.SwitchToThirdPerson(copyView);
        }, py::arg("copyView") = true)
        // The C++ guards a null camera with assert(!!sceneCamera) (Camera.cpp:578-582), which
        // compiles out in this project's Release build -- a null would survive to become a
        // dereference in the next frame's GetWorldToViewMatrix. Raise instead of relying on it.
        .def("SwitchToSceneCamera", [](donut::app::SwitchableCamera &self,
                const std::shared_ptr<donut::engine::SceneCamera> &sceneCamera) {
            if (!sceneCamera)
                throw std::invalid_argument("SwitchToSceneCamera requires a SceneCamera, not None");
            self.SwitchToSceneCamera(sceneCamera);
        }, py::arg("sceneCamera"))
        .def("IsFirstPersonActive", &donut::app::SwitchableCamera::IsFirstPersonActive)
        .def("IsThirdPersonActive", &donut::app::SwitchableCamera::IsThirdPersonActive)
        .def("IsSceneCameraActive", &donut::app::SwitchableCamera::IsSceneCameraActive)
        .def("GetSceneCamera", [](donut::app::SwitchableCamera &self) {
            return self.GetSceneCamera();
        })
        // Both return references INTO the SwitchableCamera, so the returned wrapper has to keep
        // its owner alive and must not be a copy -- reference_internal does both. A copy here
        // would silently discard whatever the caller writes through the returned camera.
        .def("GetFirstPersonCamera", &donut::app::SwitchableCamera::GetFirstPersonCamera,
            py::return_value_policy::reference_internal)
        .def("GetThirdPersonCamera", &donut::app::SwitchableCamera::GetThirdPersonCamera,
            py::return_value_policy::reference_internal)
        .def("KeyboardUpdate", &donut::app::SwitchableCamera::KeyboardUpdate,
            py::arg("key"), py::arg("scancode"), py::arg("action"), py::arg("mods"))
        .def("MousePosUpdate", &donut::app::SwitchableCamera::MousePosUpdate,
            py::arg("xpos"), py::arg("ypos"))
        .def("MouseButtonUpdate", &donut::app::SwitchableCamera::MouseButtonUpdate,
            py::arg("button"), py::arg("action"), py::arg("mods"))
        .def("MouseScrollUpdate", &donut::app::SwitchableCamera::MouseScrollUpdate,
            py::arg("xoffset"), py::arg("yoffset"))
        .def("Animate", &donut::app::SwitchableCamera::Animate, py::arg("deltaT"));
    // GetActiveUserCamera and GetWorldToViewMatrix stay unbound: the first is an internal
    // detail of the input routing that is already bound above, and the second returns a
    // matrix, which SetMatricesFromSwitchableCamera consumes in C++. JoystickUpdate and
    // JoystickButtonUpdate stay unbound -- no example handles joystick input.
```

- [ ] **Step 4: Add the view shim**

In `src/cpp/_pydonut.cpp`, immediately after the `SetMatricesFromCamera` shim (it ends with the line `}, py::arg("camera"), py::arg("aspectRatio"), py::arg("verticalFovRadians") = donut::math::PI_f * 0.25f, py::arg("zNear") = 0.1f);`), insert:

```cpp
    // SceneCamera is a SceneGraphLeaf, not a BaseCamera, so SetMatricesFromCamera above cannot
    // accept one, and SwitchableCamera::GetWorldToViewMatrix returns a dm::affine3 that must
    // not cross into Python. Same shape as SetMatricesFromCamera, and reproduces what
    // FeatureDemo.cpp:700-715 does inline: the caller's fov and near plane are used as-is
    // unless a *perspective* scene camera is active, in which case that camera's own values
    // win. GetSceneCameraProjectionParams (Camera.h:278) leaves both untouched otherwise, so
    // the unconditional call is correct for the first-person and third-person cases too.
    planarView.def("SetMatricesFromSwitchableCamera", [](donut::engine::PlanarView &self,
            const donut::app::SwitchableCamera &camera,
            float aspectRatio, float verticalFovRadians, float zNear) {
        // Both are by-value parameters, so this overwrites the local copies, not the caller's.
        camera.GetSceneCameraProjectionParams(verticalFovRadians, zNear);
        self.SetMatrices(camera.GetWorldToViewMatrix(),
            donut::math::perspProjD3DStyleReverse(verticalFovRadians, aspectRatio, zNear));
    }, py::arg("camera"), py::arg("aspectRatio"),
       py::arg("verticalFovRadians") = donut::math::PI_f * 0.25f, py::arg("zNear") = 0.1f);
```

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, immediately after the `ThirdPersonCamera` stub class, insert:

```python
# Bundles a first-person camera, a third-person camera and an optional scene camera, owning the
# switching between them, the copy-the-view-across-a-switch behaviour, and the routing of input
# to whichever user camera is active. The *Update methods return False when a scene camera is
# active, which is how the example gates input without tracking the active camera itself.
#
# NOTE: a fresh SwitchableCamera is in THIRD person. Call SwitchToFirstPerson(copyView=False)
# to start first-person -- with copyView=True it would copy from the default-constructed
# third-person camera and overwrite whatever LookAt follows.
class SwitchableCamera:
    def __init__(self: SwitchableCamera) -> None: ...
    def SwitchToFirstPerson(self: SwitchableCamera, copyView: bool = True) -> None: ...
    def SwitchToThirdPerson(self: SwitchableCamera, copyView: bool = True) -> None: ...
    # Raises ValueError on None: the C++ guards it with an assert that compiles out in this
    # project's Release build.
    def SwitchToSceneCamera(self: SwitchableCamera, sceneCamera: SceneCamera) -> None: ...
    def IsFirstPersonActive(self: SwitchableCamera) -> bool: ...
    def IsThirdPersonActive(self: SwitchableCamera) -> bool: ...
    def IsSceneCameraActive(self: SwitchableCamera) -> bool: ...
    def GetSceneCamera(self: SwitchableCamera) -> Optional[SceneCamera]: ...
    # Both return the camera owned by this SwitchableCamera, not a copy -- writes through the
    # returned object stick.
    def GetFirstPersonCamera(self: SwitchableCamera) -> FirstPersonCamera: ...
    def GetThirdPersonCamera(self: SwitchableCamera) -> ThirdPersonCamera: ...
    def KeyboardUpdate(self: SwitchableCamera, key: int, scancode: int, action: int, mods: int) -> bool: ...
    def MousePosUpdate(self: SwitchableCamera, xpos: float, ypos: float) -> bool: ...
    def MouseButtonUpdate(self: SwitchableCamera, button: int, action: int, mods: int) -> bool: ...
    def MouseScrollUpdate(self: SwitchableCamera, xoffset: float, yoffset: float) -> bool: ...
    def Animate(self: SwitchableCamera, deltaT: float) -> None: ...
```

And in the `PlanarView` stub class, immediately after the `SetMatricesFromCamera` line, add:

```python
    # Like SetMatricesFromCamera, but for a SwitchableCamera, which may be driving a scene
    # camera rather than a BaseCamera. When a perspective scene camera is active its own
    # verticalFov and zNear override the arguments passed here.
    def SetMatricesFromSwitchableCamera(self: PlanarView, camera: SwitchableCamera, aspectRatio: float, verticalFovRadians: float = ..., zNear: float = 0.1) -> None: ...
```

- [ ] **Step 6: Re-export from `__init__.py`**

In `src/pydonut/__init__.py`, add `from pydonut._pydonut import SwitchableCamera` alongside the other camera imports (next to `ThirdPersonCamera`), and `'SwitchableCamera',` to `__all__` next to `'ThirdPersonCamera',`.

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`
Expected: 67 passed (61 + 6 new).

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_camera_bindings.py
git commit -m "Bind SwitchableCamera and PlanarView.SetMatricesFromSwitchableCamera"
```

---

### Task 3: Material bindings

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (the `Material` binding line 2148; the `SceneGraphNode` binding line 2354; the `SceneGraph` binding line 2365; `ImGui.SetNextWindowPos` lines 3201-3203; after the `LightEditor` free function, which ends line 3285)
- Modify: `src/pydonut/_pydonut.pyi` (the `Material`, `SceneGraphNode`, `SceneGraph` and `ImGui` stub classes; and a new free function stub)
- Modify: `src/pydonut/__init__.py` (one import line, one `__all__` entry)
- Test: `test/test_material_bindings.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Material.materialID -> int` (read-only); `SceneGraph.GetMaterials() -> list[Material]`; `SceneGraphNode.InvalidateContent() -> None`; `pyd.MaterialEditor(material, allowMaterialDomainChanges) -> bool`; `ImGui.SetNextWindowPos(x, y, cond=0, pivotX=0.0, pivotY=0.0)`. Task 6 calls all of these.

- [ ] **Step 1: Write the failing test**

Create `test/test_material_bindings.py`. Copy lines 1-22 of `test/test_light_bindings.py` verbatim as the license header, then:

```python
"""Surface tests for the FeatureDemo stage 2c material bindings.

These need no GPU: they construct no device and render nothing. Anything that needs a loaded
scene (GetMaterials returning real entries) or a live ImGui frame (MaterialEditor) is verified
by running the example instead, and gets a presence check here.
"""

from __future__ import annotations

import pydonut as pyd


def test_material_id_is_readable() -> None:
    # Displayed in the editor window's "Material %d: %s" header. Assigned by the scene graph
    # when the material is registered, so a freshly constructed Material reads back the C++
    # default rather than anything meaningful -- this pins that it is exposed and is an int.
    material = pyd.Material()
    assert isinstance(material.materialID, int)


def test_material_id_is_read_only() -> None:
    # Bound read-only because the scene graph owns it -- writing it from Python would
    # desynchronise the material from the ID the MaterialID pass will resolve in stage 3.
    material = pyd.Material()
    with pytest.raises(AttributeError):
        material.materialID = 5


def test_scene_graph_exposes_get_materials() -> None:
    # A real call needs a loaded scene, since materials register through mesh geometry rather
    # than as scene-graph leaves (SceneGraph.cpp:542) -- an empty graph has none. Presence
    # here; the populated dropdown is a manual check in task 6.
    graph = pyd.SceneGraph()
    assert graph.GetMaterials() == []


def test_invalidate_content_is_callable_on_a_root_node() -> None:
    # Called when the editor changes a material's domain, so the scene re-sorts its draw
    # lists. Returns nothing and exposes no Python-readable state, so this asserts only that
    # the binding exists and does not raise -- the visible effect is a manual check.
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    graph.GetRootNode().InvalidateContent()


def test_material_editor_is_exported() -> None:
    # Never called from a test: it emits ImGui widgets, so it needs a live frame between
    # Begin and End. Presence only, the same treatment LightEditor gets in
    # test_light_bindings.py.
    assert callable(pyd.MaterialEditor)
```

Note this file imports `pytest` for `test_material_id_is_read_only`, so its import block is:

```python
from __future__ import annotations

import pytest

import pydonut as pyd
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_material_bindings.py -v`
Expected: FAIL — `AttributeError: 'pydonut._pydonut.Material' object has no attribute 'materialID'`.

- [ ] **Step 3: Add `materialID` to the `Material` binding**

In `src/cpp/_pydonut.cpp`, in the `Material` class binding, immediately after the `.def_readwrite("domain", &donut::engine::Material::domain)` line, insert:

```cpp
        // Read-only: assigned by the scene graph when the material is registered, and only
        // read back by the material editor window's "Material %d: %s" header
        // (FeatureDemo.cpp:1689). Writing it from Python would desynchronise the material
        // from the ID stage 3's MaterialID pass resolves.
        .def_readonly("materialID", &donut::engine::Material::materialID)
```

- [ ] **Step 4: Add `InvalidateContent` and `GetMaterials`**

In `src/cpp/_pydonut.cpp`, in the `SceneGraphNode` class binding, immediately after the `.def("SetName", &donut::engine::SceneGraphNode::SetName, py::arg("name"))` line — above the `SetPositionAndDirection` entry task 1 added — insert (note the missing semicolon: this goes into the middle of the chain, which still ends at `GetWorldPosition`):

```cpp
        // Marks this node's subtree as needing its content re-evaluated. The material editor
        // calls it on the root when a material changes domain (FeatureDemo.cpp:1694-1695),
        // because moving between the opaque and alpha-blended domains changes which draw list
        // the material's geometry belongs to.
        .def("InvalidateContent", &donut::engine::SceneGraphNode::InvalidateContent)
```

In the `SceneGraph` class binding, immediately after the `GetMeshes` lambda's closing `})`, insert:

```cpp
        // ResourceTracker<Material> isn't a plain container pybind11/stl.h can convert
        // automatically, so it's copied into a plain vector here -- the same treatment
        // GetMeshes gets just above. Materials register through mesh geometry rather than as
        // scene-graph leaves (SceneGraph.cpp:542), so this returns what the loaded meshes
        // reference and is empty on a graph with no meshes.
        .def("GetMaterials", [](const donut::engine::SceneGraph &self) {
            std::vector<std::shared_ptr<donut::engine::Material>> materials;
            for (const auto &material : self.GetMaterials())
                materials.push_back(material);
            return materials;
        })
```

- [ ] **Step 5: Give `SetNextWindowPos` a pivot**

In `src/cpp/_pydonut.cpp`, replace the existing `SetNextWindowPos` binding (lines 3201-3203) with:

```cpp
        // pivot places the given point within the window itself: (0, 0) is its top-left
        // corner (the default, and what every existing caller gets), (1, 0) its top-right.
        // The material editor window is right-aligned with (1, 0) as in FeatureDemo.cpp:1687,
        // which Python cannot do by computing x itself -- the window's width is not known
        // until after it is drawn.
        .def_static("SetNextWindowPos", [](float x, float y, int cond, float pivotX, float pivotY) {
            ImGui::SetNextWindowPos(ImVec2(x, y), cond, ImVec2(pivotX, pivotY));
        }, py::arg("x"), py::arg("y"), py::arg("cond") = 0,
           py::arg("pivotX") = 0.0f, py::arg("pivotY") = 0.0f)
```

- [ ] **Step 6: Add the `MaterialEditor` binding**

In `src/cpp/_pydonut.cpp`, immediately after the `LightEditor` free function (it ends with the line `}, py::arg("light"));`), insert:

```cpp
    // Donut's own material editor, drawn entirely from C++ (UserInterfaceUtils.h:42). Bound
    // rather than ported for the same reason LightEditor above is. Returns whether the user
    // changed anything, which the caller assigns to Material.dirty so the scene re-uploads the
    // material's constant buffer.
    //
    // allowMaterialDomainChanges lets the editor move a material between the opaque and
    // alpha-blended domains, which changes which draw list its geometry belongs to -- callers
    // passing True must invalidate scene content when the domain actually changes.
    //
    // Takes a reference rather than a pointer so pybind rejects None with a TypeError; the C++
    // signature takes Material* and would happily dereference a null.
    m.def("MaterialEditor", [](donut::engine::Material &material, bool allowMaterialDomainChanges) {
        return donut::app::MaterialEditor(&material, allowMaterialDomainChanges);
    }, py::arg("material"), py::arg("allowMaterialDomainChanges"));
```

- [ ] **Step 7: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, in the `Material` stub class, immediately after the `domain: MaterialDomain` line, add:

```python
    # Read-only: assigned by the scene graph, and only read back for the material editor
    # window's header. Stage 3's MaterialID pass resolves picking to this value.
    materialID: int
```

In the `SceneGraphNode` stub class, after `SetName`, add:

```python
    # Marks this node's subtree as needing its content re-evaluated -- called on the root when
    # a material changes domain, since that moves its geometry between draw lists.
    def InvalidateContent(self: SceneGraphNode) -> None: ...
```

In the `SceneGraph` stub class, after `GetMeshes`, add:

```python
    # Materials referenced by the graph's meshes. Empty on a graph with no meshes: materials
    # register through mesh geometry, not as scene-graph leaves.
    def GetMaterials(self: SceneGraph) -> list[Material]: ...
```

In the `ImGui` stub class, replace the `SetNextWindowPos` stub with:

```python
    @staticmethod
    # pivot places that point of the window at (x, y): (0, 0) is its top-left corner, (1, 0)
    # its top-right, which is how the material editor window right-aligns itself.
    def SetNextWindowPos(x: float, y: float, cond: int = 0, pivotX: float = 0.0, pivotY: float = 0.0) -> None: ...
```

And immediately after the `LightEditor` free-function stub, add:

```python
# Donut's built-in material editor: emits the controls for the material's texture slots and
# constants and returns whether anything changed. Draws into the current ImGui window, so call
# it from inside a buildUI() override between ImGui.Begin and ImGui.End. When
# allowMaterialDomainChanges is True the editor may change material.domain, and the caller must
# then call InvalidateContent() on the scene graph's root node.
def MaterialEditor(material: Material, allowMaterialDomainChanges: bool) -> bool: ...
```

- [ ] **Step 8: Re-export from `__init__.py`**

Add `from pydonut._pydonut import MaterialEditor` alongside the other imports, and `'MaterialEditor',` to `__all__`. Place both next to the existing `LightEditor` entries, so the editors stay together.

- [ ] **Step 9: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`
Expected: 72 passed (67 + 5 new).

- [ ] **Step 10: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_material_bindings.py
git commit -m "Bind MaterialEditor, GetMaterials, materialID and InvalidateContent"
```

---

### Task 4: `feature_demo.py` — switch to `SwitchableCamera` and add the scene cameras

**Files:**
- Modify: `feature_demo.py` (the `self.camera` field, line 260; the camera setup in `Init`, lines 337-338; a new method after `CreateSceneLights`, which ends line 695; `KeyboardUpdate`, lines 697-706; a new `MouseScrollUpdate` after `MouseButtonUpdate`, line 712-714; `SetupView`, line 770)

**Interfaces:**
- Consumes: `pyd.SwitchableCamera` and `PlanarView.SetMatricesFromSwitchableCamera` (task 2), `pyd.PerspectiveCamera` (task 1).
- Produces: `self.camera` is a `SwitchableCamera`; two `PerspectiveCamera`s named `"Nave"` and `"Gallery"` in the scene graph. Task 5's dropdown drives both.

- [ ] **Step 1: Add the scene-camera constants**

In `feature_demo.py`, immediately after the three light constants (`LOCAL_LIGHT_RADIUS = 0.05`), add:

```python
    # The two demonstration scene cameras this example adds to Sponza. Vertical FOV is in
    # RADIANS here, unlike the spot light's degrees -- PerspectiveCamera.verticalFov is what
    # Donut reads directly. Written with math.radians so the unit is visible at the call site.
    # Positions tuned by eye against Sponza's metre scale, like the light intensities above.
    NAVE_CAMERA_FOV = math.radians(60.0)
    GALLERY_CAMERA_FOV = math.radians(40.0)
    SCENE_CAMERA_Z_NEAR = 0.1
```

- [ ] **Step 2: Switch the camera field**

In `FeatureDemo.__init__`, replace

```python
            self.camera = pyd.FirstPersonCamera()
```

with

```python
            # SwitchableCamera owns a first-person camera, a third-person camera and the
            # optional active scene camera, and routes input to whichever is active. Init
            # picks the starting one -- a fresh SwitchableCamera is in *third* person.
            self.camera = pyd.SwitchableCamera()
```

- [ ] **Step 3: Fix the camera setup in `Init`**

In `FeatureDemo.Init`, replace

```python
            self.camera.LookAt(0.0, 1.8, 0.0, 1.0, 1.8, 0.0)
            self.camera.SetMoveSpeed(3.0)
```

with

```python
            # copyView=False matters: a fresh SwitchableCamera is in third person
            # (Camera.h:259-261), so copying the view would take it from the
            # default-constructed third-person camera -- 30 units back, aimed at the origin --
            # and overwrite the LookAt below.
            self.camera.SwitchToFirstPerson(copyView=False)
            firstPerson = self.camera.GetFirstPersonCamera()
            firstPerson.LookAt(0.0, 1.8, 0.0, 1.0, 1.8, 0.0)
            firstPerson.SetMoveSpeed(3.0)
```

- [ ] **Step 4: Add `CreateSceneCameras`**

In `feature_demo.py`, immediately after `CreateSceneLights` (its last line is `graph.Refresh(0)`), add:

```python
        def CreateSceneCameras(self: FeatureDemo) -> None:
            """Adds the two scene cameras the camera dropdown demonstrates.

            sponza-plus.scene.json declares no cameras at all, so without these the dropdown
            would offer only First-Person and Third-Person and nothing would exercise the
            SceneCamera bindings -- the same reason CreateSunLight synthesises the sun.

            Attach first, then name and place. SceneGraphLeaf.SetName writes through the
            owning node and silently does nothing when the leaf has no node yet
            (SceneGraph.cpp:40-47), and this project builds Release, so the assert meant to
            catch that is compiled out.

            SceneGraph::RegisterLeaf routes any SceneCamera into the graph's camera list
            (SceneGraph.cpp:577-582), so an attached camera reaches GetCameras() with no
            further registration -- exactly as an attached light reaches GetLights().

            The two differ in vertical FOV as well as position, so switching between them
            visibly changes the projection and not merely the viewpoint.
            """
            assert self.scene is not None
            graph = self.scene.GetSceneGraph()
            root = graph.GetRootNode()

            nave = pyd.PerspectiveCamera()
            nave.verticalFov = NAVE_CAMERA_FOV
            nave.zNear = SCENE_CAMERA_Z_NEAR
            naveNode = graph.AttachLeafNode(root, nave)
            nave.SetName("Nave")
            naveNode.SetPositionAndDirection(-8.0, 2.0, 0.0, 1.0, 0.0, 0.0)

            gallery = pyd.PerspectiveCamera()
            gallery.verticalFov = GALLERY_CAMERA_FOV
            gallery.zNear = SCENE_CAMERA_Z_NEAR
            galleryNode = graph.AttachLeafNode(root, gallery)
            gallery.SetName("Gallery")
            galleryNode.SetPositionAndDirection(0.0, 8.0, -4.0, 0.0, -0.4, 1.0)

            graph.Refresh(0)
```

**Why this places cameras through the node, unlike `CreateSceneLights`:** `SetPosition` and `SetDirection` are declared on `Light` (`SceneGraph.h:199-200`), not on `SceneGraphLeaf`, so a `PerspectiveCamera` does not have them. Task 1 bound the node-level equivalent for exactly this, and it is why the return value of `AttachLeafNode` is captured here where `CreateSceneLights` discards it.

- [ ] **Step 5: Call it from `Init`**

In `FeatureDemo.Init`, the three lines

```python
            self.CreateSunLight()
            self.CreateSceneLights()
            self.scene.FinishedLoading(self.GetFrameIndex())
```

become

```python
            self.CreateSunLight()
            self.CreateSceneLights()
            self.CreateSceneCameras()
            self.scene.FinishedLoading(self.GetFrameIndex())
```

- [ ] **Step 6: Add the T-key toggle**

In `FeatureDemo.KeyboardUpdate`, immediately after the existing TAB block and before `self.camera.KeyboardUpdate(...)`, insert:

```python
            # T cycles the camera, matching FeatureDemo.cpp:486-499: from a scene camera it
            # returns to a user camera, otherwise it swaps first and third person. copyView
            # defaults to True here (unlike Init), which is the point -- the new camera picks
            # up where the old one was looking.
            if key == 84 and action == 1:  # GLFW_KEY_T, GLFW_PRESS
                if self.camera.IsFirstPersonActive():
                    self.camera.SwitchToThirdPerson()
                else:
                    self.camera.SwitchToFirstPerson()
                return True
```

- [ ] **Step 7: Add `MouseScrollUpdate`**

In `feature_demo.py`, immediately after `MouseButtonUpdate`, add:

```python
        def MouseScrollUpdate(self: FeatureDemo, xoffset: float, yoffset: float) -> bool:
            # The example had no scroll handler while it only had a first-person camera, which
            # does not use the wheel. The third-person camera zooms with it.
            self.camera.MouseScrollUpdate(xoffset, yoffset)
            return True
```

- [ ] **Step 8: Update `SetupView`**

In `FeatureDemo.SetupView`, replace

```python
            self.view.SetMatricesFromCamera(self.camera, width / height)
            self.view.UpdateCache()
```

with

```python
            self.view.SetMatricesFromSwitchableCamera(self.camera, width / height)
            self.view.UpdateCache()

            # The third-person camera converts mouse drags into orbit and pan amounts using
            # the view's own projection and viewport, so it needs the view fed back in after
            # UpdateCache -- as in FeatureDemo.cpp:773.
            self.camera.GetThirdPersonCamera().SetView(self.view)
```

- [ ] **Step 9: Run the tests and the example**

Run: `uv run pytest -q`
Expected: 72 passed (unchanged — this task adds no tests).

Run: `uv run feature_demo.py`
Expected, each verified by hand:
- The example starts in first person, at the same viewpoint as before this task, and WASD/mouse-look still fly the camera.
- Pressing T switches to a third-person orbit camera looking at roughly where the first-person camera was; the mouse wheel zooms it, and dragging orbits it.
- Pressing T again returns to first person, looking where the third-person camera was.

If the example starts somewhere unexpected — 30 units out, aimed at the origin — the `copyView=False` in step 3 is missing or was passed as `True`.

- [ ] **Step 10: Commit**

```bash
git add feature_demo.py
git commit -m "Switch feature_demo.py to SwitchableCamera and add two scene cameras"
```

---

### Task 5: `feature_demo.py` — the camera dropdown

**Files:**
- Modify: `feature_demo.py` (`UIRenderer.buildUI`, after the `"Animations"` checkbox at lines 1190-1192)

**Interfaces:**
- Consumes: `pyd.SwitchableCamera`'s switch and query methods (task 2), `SceneGraph.GetCameras` (task 1), the two named cameras (task 4), `SceneGraphLeaf.GetName` (stage 2b).
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Add the dropdown**

In `UIRenderer.buildUI`, immediately after the `"Animations"` checkbox block and before the `"Material Events"` checkbox, add:

```python
            # Mirrors FeatureDemo.cpp:1548-1570, which places this right after the Animations
            # checkbox. The preview shows the active scene camera's name, or which user camera
            # is active. The scene is None until Init has loaded it.
            if self.app.scene is not None:
                sceneCameras = self.app.scene.GetSceneGraph().GetCameras()
                activeSceneCamera = self.app.camera.GetSceneCamera()

                if activeSceneCamera is not None:
                    cameraPreview = activeSceneCamera.GetName()
                elif self.app.camera.IsFirstPersonActive():
                    cameraPreview = "First-Person"
                else:
                    cameraPreview = "Third-Person"

                if pyd.ImGui.BeginCombo("Camera (T)", cameraPreview):
                    # As in the Lights section, selection is driven by Selectable's return
                    # value rather than the original's mutate-and-test pattern: the bound
                    # Selectable(label, selected) -> bool returns the click, and the argument
                    # only drives highlighting.
                    #
                    # copyView is left at its default True for every switch here, so the new
                    # camera picks up the outgoing one's viewpoint -- the behaviour the
                    # original gets from its CopyActiveCameraToFirstPerson call.
                    if pyd.ImGui.Selectable(
                        "First-Person", self.app.camera.IsFirstPersonActive()
                    ):
                        self.app.camera.SwitchToFirstPerson()
                    if pyd.ImGui.Selectable(
                        "Third-Person", self.app.camera.IsThirdPersonActive()
                    ):
                        self.app.camera.SwitchToThirdPerson()
                    for sceneCamera in sceneCameras:
                        if pyd.ImGui.Selectable(
                            sceneCamera.GetName(), sceneCamera is activeSceneCamera
                        ):
                            self.app.camera.SwitchToSceneCamera(sceneCamera)
                    pyd.ImGui.EndCombo()
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest -q`
Expected: 72 passed (unchanged — this task adds no tests).

- [ ] **Step 3: Run and exercise the dropdown**

Run: `uv run feature_demo.py`
Expected, each verified by hand:
- The "Camera (T)" combo lists exactly `First-Person`, `Third-Person`, `Nave` and `Gallery`.
- Selecting `Nave` jumps the view to a ground-level shot down the nave; selecting `Gallery` jumps to a narrower-FOV shot from the upper gallery. The two look visibly different in framing, not just position.
- While a scene camera is selected, WASD and mouse-look do nothing — `SwitchableCamera`'s input methods return `False` with a scene camera active, which is the gate the original writes as `if (!m_ui.ActiveSceneCamera)`.
- Selecting `First-Person` or pressing T returns control, looking from where the scene camera was.
- The preview text tracks the selection, and reopening the combo highlights the active entry.

If either scene camera is badly framed — inside a wall, or aimed at nothing — adjust its `SetPosition`/`SetDirection` values in `CreateSceneCameras` and re-run. These are the values the spec flagged for tuning by eye.

- [ ] **Step 4: Commit**

```bash
git add feature_demo.py
git commit -m "Add the camera dropdown to feature_demo.py"
```

---

### Task 6: `feature_demo.py` — the material editor window

**Files:**
- Modify: `feature_demo.py` (the module docstring, lines 24-36; `UIRenderer.__init__`, after `self.selectedLight`; `UIRenderer.buildUI`, after the settings window's `pyd.ImGui.End()` at line 1388)

**Interfaces:**
- Consumes: `pyd.MaterialEditor`, `SceneGraph.GetMaterials`, `Material.materialID`, `SceneGraphNode.InvalidateContent`, `ImGui.SetNextWindowPos`'s pivot (task 3).
- Produces: nothing — this is the last task.

- [ ] **Step 1: Add the selection field**

In `UIRenderer.__init__`, immediately after the `self.selectedLight` line, add:

```python
            # Same reasoning as selectedLight: nothing outside the UI reads it. The original
            # keeps the equivalent in m_ui.SelectedMaterial because its MaterialID readback
            # writes it from outside the UI -- that readback is stage 3.
            self.selectedMaterial: pyd.Material | None = None
```

- [ ] **Step 2: Add the material editor window**

In `UIRenderer.buildUI`, immediately after the settings window's `pyd.ImGui.End()` — the one closing the `"Settings"` window — add:

```python
            # A second, separate window, as in FeatureDemo.cpp:1684-1698. Outside the Settings
            # window's Begin/End: ImGui windows do not nest.
            if self.app.scene is not None:
                materials = self.app.scene.GetSceneGraph().GetMaterials()
                if materials:
                    self._buildMaterialEditorWindow(materials)

        def _buildMaterialEditorWindow(
            self: UIRenderer, materials: list[pyd.Material]
        ) -> None:
            """Draws the Material Editor window over the currently selected material.

            Split out of buildUI purely for size -- buildUI is already long, and this is a
            self-contained second window rather than another section of the settings panel.
            """
            # Right-aligned, matching FeatureDemo.cpp:1687: the pivot puts the window's
            # top-right corner at the given point, which is the only way to right-align
            # without knowing the window's width beforehand.
            windowWidth, _ = self.app.GetDeviceManager().GetWindowDimensions()
            pyd.ImGui.SetNextWindowPos(float(windowWidth) - 10.0, 10.0, 0, 1.0, 0.0)
            pyd.ImGui.Begin("Material Editor", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            # MaterialEditor emits generically-labelled controls, and CollapsingHeader does not
            # push an ID scope -- the same collision the Lights section is wrapped against.
            pyd.ImGui.PushID("MaterialEditor")

            if self.selectedMaterial is None:
                self.selectedMaterial = materials[0]

            # A dropdown stands in for the right-click viewport picking the original uses
            # (FeatureDemo.cpp:1684 reads m_ui.SelectedMaterial, written by a MaterialID
            # readback). That readback is stage 3; this combo is transitional and goes away
            # with it, rather than being a deliberate departure from the original.
            if pyd.ImGui.BeginCombo("Material", self.selectedMaterial.name):
                for material in materials:
                    if pyd.ImGui.Selectable(
                        material.name, material is self.selectedMaterial
                    ):
                        self.selectedMaterial = material
                pyd.ImGui.EndCombo()

            material = self.selectedMaterial
            pyd.ImGui.Text(f"Material {material.materialID}: {material.name}")

            previousDomain = material.domain
            material.dirty = pyd.MaterialEditor(material, True)

            # Moving between the opaque and alpha-blended domains changes which draw list the
            # material's geometry belongs to, so the scene has to re-evaluate its content.
            if material.domain != previousDomain:
                self.app.scene.GetSceneGraph().GetRootNode().InvalidateContent()

            pyd.ImGui.PopID()
            pyd.ImGui.End()
```

`GetWindowDimensions() -> tuple[int, int]` is already bound on `DeviceManager` and needs no new binding — `GetBackBufferWidth`, which the C++ original uses, is not bound and does not need to be.

- [ ] **Step 3: Update the stale module docstring**

The module docstring still describes the file as stage 1 and lists things that have since landed. Replace lines 24-36 (from `"""Port of Donut's FeatureDemo sample -- stage 1 of 3.` through the closing `"""`) with:

```python
"""Port of Donut's FeatureDemo sample -- stages 1, 2a, 2b and 2c.

Renders media/sponza-plus.scene.json through the full HDR pipeline: deferred or forward
shading, a procedural sky, SSAO, TAA or MSAA, bloom, and tone mapping with eye adaptation,
with cascaded sun shadows, a spot and a point light, a switchable first-person/third-person/
scene camera, and live light and material editors.

Still to come in stage 3: light probes, MaterialID readback (which replaces the material
editor's dropdown with right-click picking), MipMapGen, stereo and screenshots. DLSS,
taskflow and the ImGui console are out of scope permanently: see
docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md.

NOTE: sponza-plus.scene.json declares no lights and no cameras at all, so the "Sun",
"Point" and "Spot" lights and the "Nave" and "Gallery" cameras this example offers are all
created here and attached to the scene graph, not loaded.
"""
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: 72 passed (unchanged — this task adds no tests).

- [ ] **Step 5: Run and exercise the editor**

Run: `uv run feature_demo.py`
Expected, each verified by hand:
- A "Material Editor" window appears at the top right, listing Sponza's materials in its combo.
- Selecting a different material changes the header's `Material <id>: <name>` line and the controls below it.
- Changing a material's base colour or a scalar visibly changes the matching geometry in the scene.
- Dragging the SSAO "Radius" slider does *not* move any slider in the Material Editor, and vice versa — this is what the `PushID` wrapper is for.
- Switching a material's domain from Opaque to AlphaBlended makes its geometry render as translucent (enable "Translucency" and use the forward path — uncheck "Deferred Shading" — since only the forward path draws the transparent pass).

- [ ] **Step 6: Run under the debug layers**

Run: `uv run feature_demo.py -debug`
Expected: no validation errors while switching cameras, editing materials, and toggling Deferred Shading.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Add the material editor window to feature_demo.py"
```

---

## Stage 2c Done

At this point `feature_demo.py` renders Sponza with switchable first-person, third-person and scene cameras, edits any light and any material live through Donut's own editors, and `uv run pytest` covers the new binding surface at 72 tests. Stage 3 (light probes, MaterialID picking, MipMapGen, stereo and screenshots) gets its own spec and plan, and replaces this stage's material dropdown with real viewport picking.
