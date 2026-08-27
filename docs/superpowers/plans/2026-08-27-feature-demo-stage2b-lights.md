# FeatureDemo Stage 2b (spot and point lights) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind Donut's `SpotLight`, `PointLight` and `app::LightEditor` to Python, and give `feature_demo.py` two added lights in Sponza plus a Lights UI section that edits any light in the scene.

**Architecture:** Three binding tasks extend the single pybind11 translation unit `src/cpp/_pydonut.cpp`, then two tasks grow `feature_demo.py`. Lights reach both shading paths by being attached to the scene graph and nothing else — `Render()` is not touched by this stage at all, because both paths already submit `GetSceneGraph().GetLights()` wholesale.

**Tech Stack:** C++20, pybind11 3.x, NVRHI, Donut (vendored at `extern/donut`), scikit-build-core + uv, Python 3.14, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-feature-demo-stage2b-lights-design.md`

## Global Constraints

- **Donut math types are never exposed to Python.** `dm::float3`, `dm::double3` etc. are decomposed into flat scalars. Precedent: `Light.SetDirection` (`src/cpp/_pydonut.cpp:2264-2266`), `SkyParameters.SetSkyColor` (`src/cpp/_pydonut.cpp:2584-2586`).
- **Bind only what the example calls.** Every skipped constructor/method carries a comment saying it was skipped and why, so a later stage can tell a decision from an oversight.
- **Three files stay in sync for every new name:** `src/cpp/_pydonut.cpp` (the binding), `src/pydonut/_pydonut.pyi` (the type stub), `src/pydonut/__init__.py` (the `from pydonut._pydonut import X` line **and** the `__all__` entry). Adding a *method* to an existing class touches only the first two.
- **Rebuild command is `uv sync`.** It rebuilds the native module in place; `src/cpp/**` is a cache key (`pyproject.toml:26`). Tests run with `uv run pytest`. A binding change is not testable until `uv sync` has run.
- **Tests are GPU-free.** No device is created and nothing is rendered, matching `test/test_shadow_bindings.py`. Anything needing a device is verified by running the example instead.
- **Every new Python file starts with the repo's license header** — copy it verbatim from the top of `test/test_shadow_bindings.py` (lines 1-22).
- **Baseline test count is 43** (`uv run pytest -q` on the commit this plan starts from). Each task states the new expected total.
- **Attach before you place.** `Light::SetPosition` and `Light::SetDirection` both assert when the light has no scene-graph node (`SceneTypes.cpp:82` and `:100`), because both work by writing the owning node's transform.
- **No new light casts a shadow.** `DeferredLightingPass` logs an error and returns *without rendering the frame* when two lights present different shadow textures (`DeferredLightingPass.cpp:172-175`). Only the sun gets a `shadowMap`.

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `src/cpp/_pydonut.cpp` | modify | All bindings. Four insertion points: the include block (after line 41), `SceneGraphLeaf` (line 2231-2232), `Light` (line 2263-2283), after `DirectionalLight` (line 2285-2288), and after the `ImGui` class block (ends line 3196). |
| `src/pydonut/_pydonut.pyi` | modify | Type stubs, mirroring each binding. |
| `src/pydonut/__init__.py` | modify | Re-export line + `__all__` entry for `SpotLight`, `PointLight`, `LightEditor`. |
| `test/test_light_bindings.py` | create | GPU-free surface tests for this stage. A new file, not an extension of `test_shadow_bindings.py`, which is named for stage 2a's subject. |
| `feature_demo.py` | modify | The example. Grows by three module constants, `CreateSceneLights`, and a UI section. |

---

### Task 1: `SceneGraphLeaf.GetName` + `Light.SetPosition`/`SetColor`

**Files:**
- Modify: `src/cpp/_pydonut.cpp:2231-2232` (`SceneGraphLeaf`), `src/cpp/_pydonut.cpp:2263-2283` (`Light`)
- Modify: `src/pydonut/_pydonut.pyi` (the `SceneGraphLeaf` and `Light` stub classes)
- Test: `test/test_light_bindings.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SceneGraphLeaf.GetName() -> str`; `Light.SetPosition(x: float, y: float, z: float) -> None`; `Light.SetColor(r: float, g: float, b: float) -> None`. Tasks 2, 4 and 5 all call `GetName`; task 4 calls `SetPosition`.

- [ ] **Step 1: Write the failing test**

Create `test/test_light_bindings.py`. Copy lines 1-22 of `test/test_shadow_bindings.py` verbatim as the license header, then:

```python
"""Surface tests for the FeatureDemo stage 2b light bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a field that silently did not round-trip.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def _attached(light: pyd.Light) -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Puts `light` under a fresh graph's root and returns the graph and the light's node.

    SetPosition/SetDirection assert when a light has no node (SceneTypes.cpp:82, :100), so
    every positional test needs this much scaffolding. No device is involved.
    """
    graph = pyd.SceneGraph()
    root = graph.SetRootNode(pyd.SceneGraphNode())
    node = graph.AttachLeafNode(root, light)
    return graph, node


def test_scene_graph_leaf_name_round_trips() -> None:
    light = pyd.DirectionalLight()
    light.SetName("Sun")
    assert light.GetName() == "Sun"


def test_light_set_position_writes_the_nodes_world_transform() -> None:
    # SetPosition converts world space to parent-local and calls SceneGraphNode::SetTranslation
    # itself (SceneTypes.cpp:77-93). SetTranslation only marks the node dirty, so the world
    # transform GetWorldPosition reads back is the one Refresh recomputes.
    light = pyd.DirectionalLight()
    graph, node = _attached(light)
    light.SetPosition(1.0, 2.0, 3.0)
    graph.Refresh(0)
    assert node.GetWorldPosition() == pytest.approx((1.0, 2.0, 3.0))


def test_light_set_direction_leaves_the_position_alone() -> None:
    # SetDirection writes rotation and scaling through SetTransform(nullptr, &rotation,
    # &scaling) (SceneGraph.cpp:282-291), so the two setters are order-free.
    light = pyd.DirectionalLight()
    graph, node = _attached(light)
    light.SetPosition(1.0, 2.0, 3.0)
    light.SetDirection(0.0, -1.0, 0.0)
    graph.Refresh(0)
    assert node.GetWorldPosition() == pytest.approx((1.0, 2.0, 3.0))


def test_light_set_color_accepts_three_floats() -> None:
    # Setter only, matching SkyParameters' float3 fields -- there is no GetColor, because
    # nothing in the example reads a colour back and LightEditor writes the field from C++.
    light = pyd.DirectionalLight()
    light.SetColor(1.0, 0.5, 0.25)
    assert not hasattr(light, "GetColor")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_light_bindings.py -v`
Expected: FAIL — `AttributeError: 'pydonut._pydonut.DirectionalLight' object has no attribute 'GetName'`.

- [ ] **Step 3: Add `GetName` to the `SceneGraphLeaf` binding**

In `src/cpp/_pydonut.cpp`, replace the two-line `SceneGraphLeaf` binding at line 2231-2232 with:

```cpp
    py::class_<donut::engine::SceneGraphLeaf, std::shared_ptr<donut::engine::SceneGraphLeaf>>(m, "SceneGraphLeaf")
        .def("SetName", [](const donut::engine::SceneGraphLeaf &self, const std::string &name) { self.SetName(name); }, py::arg("name"))
        // Read back by feature_demo.py's light dropdown, which labels each entry with it
        // (FeatureDemo.cpp:1637-1643). SetName alone was enough while nothing read a name back.
        .def("GetName", &donut::engine::SceneGraphLeaf::GetName);
```

- [ ] **Step 4: Add `SetPosition` and `SetColor` to the `Light` binding**

In `src/cpp/_pydonut.cpp`, immediately after the `SetDirection` `.def` (which ends `}, py::arg("x"), py::arg("y"), py::arg("z"))` at line 2266), insert:

```cpp
        // Same shape as SetDirection: flat scalars in, nothing coming back. Light::SetPosition
        // converts world space to parent-local and writes the node's translation itself
        // (SceneTypes.cpp:77-93), which is why SceneGraphNode.SetTranslation stays unbound.
        //
        // Like SetDirection, this asserts when the light has no node (SceneTypes.cpp:82), so a
        // light must be attached to the scene graph before it is placed. The two do not clobber
        // each other: SetDirection writes only rotation and scaling (SceneGraph.cpp:282-291).
        //
        // The matching getters -- Light::GetPosition and GetDirection -- stay unbound: nothing
        // in the examples reads either back, and the node's world position is already reachable
        // through SceneGraphNode.GetWorldPosition.
        .def("SetPosition", [](const donut::engine::Light &self, double x, double y, double z) {
            self.SetPosition(donut::math::double3(x, y, z));
        }, py::arg("x"), py::arg("y"), py::arg("z"))
        // color is a dm::float3, so it takes flat scalars like SkyParameters' four float3
        // fields below. Setter only, as those are: nothing in the examples reads a colour back,
        // and LightEditor writes the field directly from C++.
        .def("SetColor", [](donut::engine::Light &self, float r, float g, float b) {
            self.color = donut::math::float3(r, g, b);
        }, py::arg("r"), py::arg("g"), py::arg("b"))
```

Note `SetColor` takes a non-const `Light &` — it assigns a field, unlike `SetPosition`/`SetDirection`, which are const members.

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, replace the `SceneGraphLeaf` stub class with:

```python
class SceneGraphLeaf():
    def SetName(self: SceneGraphLeaf, name: str) -> None: ...
    # Read back by feature_demo.py's light dropdown to label each entry.
    def GetName(self: SceneGraphLeaf) -> str: ...
```

And in the `Light` stub class, immediately after the `SetDirection` line, add:

```python
    # Flat scalars, like SetDirection -- donut math types never cross into Python. Both require
    # the light to be attached to a scene graph first: Light::SetPosition and SetDirection
    # assert when the light has no node (SceneTypes.cpp:82, :100). They do not clobber each
    # other; SetDirection writes only rotation and scaling.
    def SetPosition(self: Light, x: float, y: float, z: float) -> None: ...
    # Setter only, matching SkyParameters' float3 fields -- nothing reads a colour back, and
    # LightEditor writes the field from C++.
    def SetColor(self: Light, r: float, g: float, b: float) -> None: ...
```

No `__init__.py` change: this task adds no new top-level names.

- [ ] **Step 6: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`
Expected: 47 passed (43 baseline + 4 new).

- [ ] **Step 7: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi test/test_light_bindings.py
git commit -m "Bind SceneGraphLeaf.GetName and Light.SetPosition/SetColor"
```

---

### Task 2: `SpotLight` and `PointLight`

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (after the `DirectionalLight` binding, line 2285-2288)
- Modify: `src/pydonut/_pydonut.pyi` (after the `DirectionalLight` stub)
- Modify: `src/pydonut/__init__.py` (two import lines, two `__all__` entries)
- Test: `test/test_light_bindings.py` (append)

**Interfaces:**
- Consumes: `SceneGraphLeaf.GetName` from task 1.
- Produces: `pyd.SpotLight()` with `intensity`, `radius`, `range`, `innerAngle`, `outerAngle`; `pyd.PointLight()` with `intensity`, `radius`, `range`. Both derive from `pyd.Light`. Task 4 constructs both; task 5 edits them through `LightEditor`.

- [ ] **Step 1: Write the failing test**

Append to `test/test_light_bindings.py`:

```python
def test_spot_light_is_a_light() -> None:
    assert issubclass(pyd.SpotLight, pyd.Light)


def test_point_light_is_a_light() -> None:
    assert issubclass(pyd.PointLight, pyd.Light)


def test_spot_light_fields_round_trip() -> None:
    light = pyd.SpotLight()
    light.intensity = 60.0
    light.radius = 0.05
    light.range = 0.0
    light.innerAngle = 20.0
    light.outerAngle = 35.0
    # approx throughout: these are C++ floats, so 0.05 does not survive a round trip exactly.
    assert light.intensity == pytest.approx(60.0)
    assert light.radius == pytest.approx(0.05)
    assert light.range == pytest.approx(0.0)
    assert light.innerAngle == pytest.approx(20.0)
    assert light.outerAngle == pytest.approx(35.0)


def test_point_light_fields_round_trip() -> None:
    light = pyd.PointLight()
    light.intensity = 20.0
    light.radius = 0.05
    light.range = 0.0
    assert light.intensity == pytest.approx(20.0)
    assert light.radius == pytest.approx(0.05)
    assert light.range == pytest.approx(0.0)


def test_local_lights_cast_no_shadow_by_default() -> None:
    # Neither added light may get its own shadow map: DeferredLightingPass logs an error and
    # returns without rendering the frame when two lights present different shadow textures
    # (DeferredLightingPass.cpp:172-175).
    assert pyd.SpotLight().shadowMap is None
    assert pyd.PointLight().shadowMap is None


def test_get_lights_returns_the_concrete_light_types() -> None:
    # The Lights UI and LightEditor both depend on this: GetLights() is typed as a list of
    # Light in C++, and pybind must hand back the most-derived registered type so the editor
    # dispatches correctly and so `is` comparisons against the stored selection hold.
    graph = pyd.SceneGraph()
    root = graph.SetRootNode(pyd.SceneGraphNode())

    spot = pyd.SpotLight()
    spot.SetName("Spot")
    point = pyd.PointLight()
    point.SetName("Point")
    graph.AttachLeafNode(root, spot)
    graph.AttachLeafNode(root, point)

    lights = graph.GetLights()
    assert [light.GetName() for light in lights] == ["Spot", "Point"]
    assert isinstance(lights[0], pyd.SpotLight)
    assert isinstance(lights[1], pyd.PointLight)
    assert lights[0] is spot
    assert lights[1] is point
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_light_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'SpotLight'`.

- [ ] **Step 3: Add the bindings**

In `src/cpp/_pydonut.cpp`, immediately after the `DirectionalLight` binding (which ends `.def_readwrite("angularSize", &donut::engine::DirectionalLight::angularSize);` at line 2288), insert:

```cpp
    // SpotLight and PointLight (SceneGraph.h:218-233 and :235-248). Constructible, with every
    // public field bound: editing them is the point of the stage they were added for.
    //
    // range = 0 means infinite range -- both FillLightConstants overrides encode it as an
    // inverse range of zero (SceneTypes.cpp:193, :273), so it is not a degenerate value to
    // guard against. Angles are in degrees; Donut converts them to radians when it fills the
    // constants (SceneTypes.cpp:196-197).
    //
    // Store, SetProperty and Clone stay unbound on both: the JSON-serialisation and animation
    // paths, which no example drives.
    py::class_<donut::engine::SpotLight, donut::engine::Light, std::shared_ptr<donut::engine::SpotLight>>(m, "SpotLight")
        .def(py::init<>())
        .def_readwrite("intensity", &donut::engine::SpotLight::intensity)
        .def_readwrite("radius", &donut::engine::SpotLight::radius)
        .def_readwrite("range", &donut::engine::SpotLight::range)
        .def_readwrite("innerAngle", &donut::engine::SpotLight::innerAngle)
        .def_readwrite("outerAngle", &donut::engine::SpotLight::outerAngle);

    py::class_<donut::engine::PointLight, donut::engine::Light, std::shared_ptr<donut::engine::PointLight>>(m, "PointLight")
        .def(py::init<>())
        .def_readwrite("intensity", &donut::engine::PointLight::intensity)
        .def_readwrite("radius", &donut::engine::PointLight::radius)
        .def_readwrite("range", &donut::engine::PointLight::range);
```

- [ ] **Step 4: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, immediately after the `DirectionalLight` stub class, insert:

```python
# A cone light. Angles are in degrees (Donut converts to radians when filling the light
# constants); range = 0 means infinite range. Position and direction come from the owning
# scene-graph node -- set them with Light.SetPosition/SetDirection *after* attaching.
class SpotLight(Light):
    def __init__(self: SpotLight) -> None: ...
    intensity: float
    radius: float
    range: float
    innerAngle: float
    outerAngle: float

# An omnidirectional light. range = 0 means infinite range. Position comes from the owning
# scene-graph node -- set it with Light.SetPosition *after* attaching.
class PointLight(Light):
    def __init__(self: PointLight) -> None: ...
    intensity: float
    radius: float
    range: float
```

- [ ] **Step 5: Re-export from `__init__.py`**

In `src/pydonut/__init__.py`, after the line `from pydonut._pydonut import DirectionalLight` (line 124), add:

```python
from pydonut._pydonut import SpotLight
from pydonut._pydonut import PointLight
```

And in `__all__`, after the `'DirectionalLight',` entry (line 308), add:

```python
    'SpotLight',
    'PointLight',
```

- [ ] **Step 6: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`
Expected: 53 passed (47 + 6 new).

- [ ] **Step 7: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_light_bindings.py
git commit -m "Bind SpotLight and PointLight"
```

---

### Task 3: `LightEditor`

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (include block after line 41; new free function after the `ImGui` class block, which ends at line 3196)
- Modify: `src/pydonut/_pydonut.pyi` (after the `ImGui` stub class)
- Modify: `src/pydonut/__init__.py` (one import line, one `__all__` entry)
- Test: `test/test_light_bindings.py` (append)

**Interfaces:**
- Consumes: `pyd.Light` and its subclasses from tasks 1-2.
- Produces: `pyd.LightEditor(light: Light) -> bool`. Task 5 calls it from inside `UIRenderer.buildUI`.

- [ ] **Step 1: Write the failing test**

Append to `test/test_light_bindings.py`:

```python
def test_light_editor_is_exported() -> None:
    # Never called from a test: it emits ImGui widgets, so it needs a live frame between
    # Begin and End. Presence only, the same treatment the ImGui surface gets in
    # test_postprocess_bindings.py:227.
    assert callable(pyd.LightEditor)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_light_bindings.py::test_light_editor_is_exported -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'LightEditor'`.

- [ ] **Step 3: Add the include**

In `src/cpp/_pydonut.cpp`, immediately after `#include <donut/app/imgui_renderer.h>` (line 41), add:

```cpp
#include <donut/app/UserInterfaceUtils.h>
```

- [ ] **Step 4: Add the binding**

In `src/cpp/_pydonut.cpp`, immediately after the `ImGui` class binding — the line `.def_static("SetItemDefaultFocus", &ImGui::SetItemDefaultFocus);` at line 3196 — insert:

```cpp
    // Donut's own light editor, drawn entirely from C++: it dispatches on GetLightType() and
    // emits the right controls for a directional, point or spot light
    // (UserInterfaceUtils.cpp:364-377). Bound rather than ported for the same reason every
    // render pass is bound rather than reimplemented, and because porting it would need three
    // ImGui entry points nothing else here wants -- ColorEdit3, a logarithmic SliderFloat flag,
    // and a double-typed SliderScalar.
    //
    // It draws into whatever ImGui window is current, so it is called from inside buildUI
    // between Begin and End. Returns whether the user changed anything.
    //
    // MaterialEditor, FileDialog, FolderDialog and AzimuthElevationSliders from the same header
    // stay unbound: the first three belong to later stages, and the last is an implementation
    // detail of the editors above it.
    m.def("LightEditor", [](donut::engine::Light &light) {
        return donut::app::LightEditor(light);
    }, py::arg("light"));
```

- [ ] **Step 5: Add the type stub**

In `src/pydonut/_pydonut.pyi`, immediately after the `ImGui` stub class, insert:

```python
# Donut's built-in light editor: emits the controls appropriate to the light's concrete type
# and returns whether anything changed. It draws into the current ImGui window, so call it from
# inside a buildUI() override, between ImGui.Begin and ImGui.End.
def LightEditor(light: Light) -> bool: ...
```

- [ ] **Step 6: Re-export from `__init__.py`**

Add `from pydonut._pydonut import LightEditor` alongside the other imports, and `'LightEditor',` to `__all__`. Place both next to the `SpotLight`/`PointLight` entries added in task 2, so the stage's names stay together.

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`
Expected: 54 passed (53 + 1 new).

**If the build fails at the link step** with unresolved `GetOpenFileNameA`, `GetSaveFileNameA`, `SHBrowseForFolderW` or `SHGetPathFromIDListW`: referencing `LightEditor` pulls `UserInterfaceUtils.obj` into the link, and that object also contains `FileDialog`/`FolderDialog`, which need `comdlg32` and `shell32`. MSVC's default standard-library list normally covers both, so this is not expected — but if it happens, the fix is to add them explicitly in `CMakeLists.txt:170-175`:

```cmake
target_link_libraries(_pydonut PRIVATE
    donut_core
    donut_render
    donut_app
    donut_engine
)

if (WIN32)
    # donut::app::LightEditor lives in UserInterfaceUtils.obj alongside FileDialog and
    # FolderDialog, so referencing the editor drags in their Win32 dialog dependencies.
    target_link_libraries(_pydonut PRIVATE comdlg32 shell32)
endif()
```

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_light_bindings.py CMakeLists.txt
git commit -m "Bind donut::app::LightEditor"
```

---

### Task 4: `feature_demo.py` — add the spot and point lights

**Files:**
- Modify: `feature_demo.py` (module constants after `SHADOW_LIGHT_SPACE_Z_DOWN`, line 84; new method after `CreateSunLight`, which ends line 628; one call in `Init`, line 279 area)

**Interfaces:**
- Consumes: `pyd.SpotLight`, `pyd.PointLight` (task 2), `Light.SetPosition` (task 1).
- Produces: three lights in the scene graph named `"Sun"`, `"Point"` and `"Spot"`. Task 5's dropdown lists them.

- [ ] **Step 1: Add the module constants**

In `feature_demo.py`, immediately after `SHADOW_LIGHT_SPACE_Z_DOWN = 20.0` (line 84), add:

```python
    # The two demonstration lights this example adds to Sponza. Intensity is luminous intensity
    # in lm/sr, multiplied by the light's colour; radius is the light sphere's radius in world
    # units. Starting points tuned by eye against Sponza's metre scale -- the Lights UI section
    # is how they are explored further, so they are constants rather than UI state.
    POINT_LIGHT_INTENSITY = 20.0
    SPOT_LIGHT_INTENSITY = 60.0
    LOCAL_LIGHT_RADIUS = 0.05
```

- [ ] **Step 2: Add `CreateSceneLights`**

In `feature_demo.py`, immediately after `CreateSunLight` (its last line is `graph.Refresh(0)` at line 628), add:

```python
        def CreateSceneLights(self: FeatureDemo) -> None:
            """Adds the spot and point light this stage demonstrates.

            Unlike CreateSunLight there is no "reuse what the scene declared" branch. The sun is
            the light the renderer needs and another scene might supply one; these two are the
            example's own demonstration objects and are always synthesised.

            Attach first, then place. Light.SetPosition and Light.SetDirection both assert when
            the light has no node (SceneTypes.cpp:82, :100), because both work by writing the
            owning node's transform. They do not clobber each other: SetDirection writes only
            rotation and scaling (SceneGraph.cpp:282-291).

            Neither light gets a shadow map, and that is load-bearing rather than unfinished.
            DeferredLightingPass logs an error and returns *without rendering the frame* if two
            lights present different shadow textures (DeferredLightingPass.cpp:172-175), and a
            CascadedShadowMap cannot be shared with a local light -- that needs
            SetupPerObjectShadow, which is unbound. Only the sun casts.

            Nothing else changes to light the scene with these: both shading paths already
            submit the whole GetLights() list, and both build their constants through the
            virtual FillLightConstants, which SpotLight and PointLight override.
            """
            assert self.scene is not None
            graph = self.scene.GetSceneGraph()
            root = graph.GetRootNode()

            point = pyd.PointLight()
            point.SetName("Point")
            point.intensity = POINT_LIGHT_INTENSITY
            point.radius = LOCAL_LIGHT_RADIUS
            graph.AttachLeafNode(root, point)
            point.SetPosition(-4.0, 2.0, 0.0)

            spot = pyd.SpotLight()
            spot.SetName("Spot")
            spot.intensity = SPOT_LIGHT_INTENSITY
            spot.radius = LOCAL_LIGHT_RADIUS
            spot.innerAngle = 20.0
            spot.outerAngle = 35.0
            graph.AttachLeafNode(root, spot)
            spot.SetPosition(4.0, 5.0, 0.0)
            spot.SetDirection(-0.2, -1.0, 0.0)

            graph.Refresh(0)
```

- [ ] **Step 3: Call it from `Init`**

In `FeatureDemo.Init`, the two lines

```python
            self.CreateSunLight()
            self.scene.FinishedLoading(self.GetFrameIndex())
```

become

```python
            self.CreateSunLight()
            self.CreateSceneLights()
            self.scene.FinishedLoading(self.GetFrameIndex())
```

Before `FinishedLoading`, so the whole graph is complete when the scene uploads its resources.

- [ ] **Step 4: Run it on the deferred path**

Run: `uv run feature_demo.py`
Expected: Sponza as before, plus a bright pool of light on the floor around x = -4 (the point light) and a cone of light around x = +4 (the spot). Fly to each and confirm both are visible and distinct from the sun's lighting — toggle "Enabled" under Shadows off and on: the two new pools must not change, because only the sun casts.

If either light is invisible or blows out the frame, adjust `POINT_LIGHT_INTENSITY` / `SPOT_LIGHT_INTENSITY` and re-run. These are the values the spec flagged for tuning by eye.

- [ ] **Step 5: Verify the forward path**

With the example running, uncheck "Deferred Shading".
Expected: both lights still visible, roughly matching the deferred result. This is the check that `FillLightConstants` reaches `ForwardShadingPass::PrepareLights` as well.

- [ ] **Step 6: Run under the debug layers**

Run: `uv run feature_demo.py -debug`
Expected: no validation errors, and in particular no `All lights submitted to DeferredLightingPass::Render(...) must use the same shadow map textures` in the console — that message means a new light acquired a shadow map it must not have.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Add a spot and a point light to feature_demo.py"
```

---

### Task 5: `feature_demo.py` — the Lights UI section

**Files:**
- Modify: `feature_demo.py` (`UIRenderer.__init__`, line 1070-1076; `buildUI`, after the Shadows `CollapsingHeader` block which ends line 1181)

**Interfaces:**
- Consumes: `pyd.LightEditor` (task 3), `SceneGraphLeaf.GetName` (task 1), the three lights (task 4).
- Produces: nothing later tasks rely on — this is the last task.

- [ ] **Step 1: Add the selection field**

In `UIRenderer.__init__`, after `self.ui = ui`, add:

```python
            # The selected light lives here rather than on UIData because nothing outside the
            # UI reads it -- the same place the original keeps m_SelectedLight
            # (FeatureDemo.cpp:1445).
            self.selectedLight: pyd.Light | None = None
```

- [ ] **Step 2: Add the UI section**

In `UIRenderer.buildUI`, immediately after the Shadows `CollapsingHeader` block (it ends with the `self.app.shadowMap.SetLitOutOfBounds(...)` line) and before `if pyd.ImGui.CollapsingHeader("Sky"):`, add:

```python
            # Fetched before the header so an empty scene hides the section entirely, matching
            # FeatureDemo.cpp:1635. This example always has three, but a different scene need
            # not.
            assert self.app.scene is not None
            lights = self.app.scene.GetSceneGraph().GetLights()

            if lights and pyd.ImGui.CollapsingHeader("Lights"):
                preview = (
                    self.selectedLight.GetName()
                    if self.selectedLight is not None
                    else "(None)"
                )
                if pyd.ImGui.BeginCombo("Select Light", preview):
                    for light in lights:
                        # The original passes &selected and then tests it
                        # (FeatureDemo.cpp:1641-1648), which re-selects whatever the mouse
                        # passes over. The bound Selectable returns the click instead, which is
                        # the correct ImGui idiom, so the argument only drives highlighting.
                        #
                        # `is` is sound here: pybind hands back the same Python wrapper for a
                        # C++ object that is still alive on the Python side, and holding the
                        # selection is what keeps it alive.
                        if pyd.ImGui.Selectable(light.GetName(), light is self.selectedLight):
                            self.selectedLight = light
                            pyd.ImGui.SetItemDefaultFocus()
                    pyd.ImGui.EndCombo()

                # Donut draws the whole editor, picking the controls from the light's concrete
                # type. Its return value says whether anything changed; nothing here needs to
                # act on that, because every field it writes is read fresh each frame -- the
                # sun's cascades included, since RenderShadowMap re-fits them every frame.
                if self.selectedLight is not None:
                    pyd.LightEditor(self.selectedLight)
```

- [ ] **Step 3: Run and exercise every control**

Run: `uv run feature_demo.py`
Expected, each verified by hand:
- The Lights header lists exactly `Sun`, `Point` and `Spot`.
- Selecting each one swaps the editor's controls: Azimuth/Elevation + Color + Irradiance + Angular Size for `Sun`; Radius + Color + Intensity for `Point`; those three plus Azimuth/Elevation and Inner/Outer Angle for `Spot`.
- The combo's preview text tracks the selection, and re-opening it highlights the selected entry.
- Dragging `Point`'s Intensity brightens and dims its pool of light.
- Dragging `Spot`'s Outer Angle widens and narrows its cone.
- Editing a Color visibly tints the affected light.

- [ ] **Step 4: Verify the sun's shadows follow its editor**

With `Sun` selected and Shadows enabled, drag Azimuth and Elevation.
Expected: the shadows swing with the light every frame, with no hitch and no shadow-map rebuild — `RenderShadowMap` re-fits the cascades from `self.sunLight` each frame, so nothing extra is needed for this to work.

- [ ] **Step 5: Verify both shading paths and every AA mode**

Run: `uv run feature_demo.py -debug`, then with the Lights section open, toggle "Deferred Shading" and cycle all five AA modes.
Expected: no validation errors, the editor keeps working, and the two added lights stay visible throughout. MSAA is the interesting case, since it forces the forward path.

- [ ] **Step 6: Confirm the binding tests still pass**

Run: `uv run pytest -q`
Expected: 54 passed.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Add the Lights UI section to feature_demo.py"
```

---

## Stage 2b Done

At this point `feature_demo.py` renders Sponza lit by a sun, a point light and a spot light on both shading paths, with Donut's light editor driving any of the three live, and `uv run pytest` covers the new binding surface. Stage 2c (scene cameras and the material editor) gets its own spec and plan.
