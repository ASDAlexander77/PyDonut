# FeatureDemo Stage 2a (sun shadows) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind Donut's `CascadedShadowMap`, `DepthPass` and the `IShadowMap` interface to Python, and give `feature_demo.py` sun shadows on both its shading paths, with a live toggle between the two cascade fits.

**Architecture:** Four binding tasks extend the single pybind11 translation unit `src/cpp/_pydonut.cpp`, then three tasks grow `feature_demo.py`. Shadows attach by assigning `sunLight.shadowMap` — both lighting passes read it themselves, so no pass input is plumbed. The shadow map is created and destroyed by its own `CreateShadowMap()`, deliberately outside the back-buffer-sized render-target rebuild path.

**Tech Stack:** C++20, pybind11 3.x, NVRHI, Donut (vendored at `extern/donut`), scikit-build-core + uv, Python 3.14, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-feature-demo-stage2a-shadows-design.md`

## Global Constraints

- **Donut math types are never exposed to Python.** `dm::frustum`, `dm::affine3`, `dm::float3` etc. are decomposed into flat scalars, or — as in this plan's shadow setup calls — extracted C++-side from an object Python already holds. Precedent: `DeferredLightingPassInputs.SetAmbientColors` (`src/cpp/_pydonut.cpp:2389`), `TemporalAntiAliasingPass.GetCurrentPixelOffset`.
- **Bind only what the example calls.** Every skipped constructor/method carries a comment saying it was skipped and why, so a later stage can tell a decision from an oversight.
- **Three files stay in sync for every binding:** `src/cpp/_pydonut.cpp` (the binding), `src/pydonut/_pydonut.pyi` (the type stub), `src/pydonut/__init__.py` (the `from pydonut._pydonut import X` line **and** the `__all__` entry).
- **Rebuild command is `uv sync`.** It rebuilds the native module in place; `src/cpp/**` is a cache key (`pyproject.toml:26`). Tests run with `uv run pytest`. A binding change is not testable until `uv sync` has run.
- **Tests are GPU-free.** No device is created and nothing is rendered, matching `test/test_postprocess_bindings.py`. Anything needing a device is verified by running the example instead.
- **Every new Python file starts with the repo's license header** — copy it verbatim from the top of `test/test_postprocess_bindings.py` (lines 1-22).
- **Two asserts in Donut constrain the UI ranges:** `numCascades` must be in `[1, 4]` (`CascadedShadowMap.cpp:40-41`) and `exponent` must be **strictly greater than 1** (`CascadedShadowMap.cpp:83`). A debug build aborts otherwise.

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `src/cpp/_pydonut.cpp` | modify | All bindings. Four separate insertion points: includes (~line 46-65), `Light` (line 2237), after `GBufferFillPass` (line 2370), after `BloomPass` (line 2665), and the two free functions (lines 2686-2704). |
| `src/pydonut/_pydonut.pyi` | modify | Type stubs, mirroring each binding. |
| `src/pydonut/__init__.py` | modify | Re-export line + `__all__` entry per new name. |
| `test/test_shadow_bindings.py` | create | GPU-free surface tests for this stage. A new file, not an extension of `test_postprocess_bindings.py`, which is named for stage 1's subject. |
| `feature_demo.py` | modify | The example. Grows by `CreateShadowMap`, a shadow render block, and a UI section. |

---

### Task 1: `IShadowMap` base + `Light.shadowMap`

The smallest shippable piece: a light can be given a shadow map, or `None`. Nothing renders yet.

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (include near line 54; new class + property near line 2237)
- Modify: `src/pydonut/_pydonut.pyi:1094-1098`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_shadow_bindings.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `pyd.IShadowMap` (a non-constructible polymorphic base) and `Light.shadowMap`, a read/write property accepting an `IShadowMap` or `None`. Tasks 2 and 6 both depend on these names.

- [ ] **Step 1: Write the failing test**

Create `test/test_shadow_bindings.py`. Copy lines 1-22 of `test/test_postprocess_bindings.py` (the license header) verbatim as the first 22 lines, then append:

```python
"""Surface tests for the FeatureDemo stage 2a shadow bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a parameter default drifting away from the C++ header it mirrors.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def test_ishadowmap_is_exported() -> None:
    assert hasattr(pyd, "IShadowMap")


def test_ishadowmap_is_not_constructible() -> None:
    # Registered purely as a polymorphic base, the same shape ICompositeView/IView take --
    # everything the interface declares is called by the lighting passes in C++.
    with pytest.raises(TypeError):
        pyd.IShadowMap()


def test_light_shadow_map_defaults_to_none() -> None:
    light = pyd.DirectionalLight()
    assert light.shadowMap is None


def test_light_shadow_map_accepts_none() -> None:
    # Assigning None is the shadow toggle: both lighting passes null-check light->shadowMap
    # (DeferredLightingPass.cpp:163), so clearing it needs no pass rebuild.
    light = pyd.DirectionalLight()
    light.shadowMap = None
    assert light.shadowMap is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_shadow_bindings.py -v`
Expected: FAIL — `test_ishadowmap_is_exported` with `AssertionError`, and the `shadowMap` tests with `AttributeError`.

- [ ] **Step 3: Add the include**

In `src/cpp/_pydonut.cpp`, immediately after `#include <donut/engine/FramebufferFactory.h>` (line 54):

```cpp
#include <donut/engine/ShadowMap.h>
```

- [ ] **Step 4: Register `IShadowMap`**

In `src/cpp/_pydonut.cpp`, immediately **before** `py::class_<donut::engine::Light, ...>` (line 2237):

```cpp
    // Registered as a polymorphic base with no methods bound, the same shape ICompositeView/
    // IView take at :2756-2762. Everything IShadowMap declares (GetWorldToUvzwMatrix,
    // FillShadowConstants, GetUVRange, GetFadeRangeInTexels, IsLitOutOfBounds, GetCascade,
    // GetPerObjectShadow) is called by the lighting passes in C++, never from Python. It
    // exists so Light.shadowMap has a type to accept and so CascadedShadowMap can derive from
    // it Python-side. Not constructible: there is no concrete IShadowMap.
    py::class_<donut::engine::IShadowMap, std::shared_ptr<donut::engine::IShadowMap>>(m, "IShadowMap");

```

- [ ] **Step 5: Add the `Light.shadowMap` property**

In the same file, extend the `Light` binding. Replace the closing of its `FillLightConstants` def (line 2244-2248) — that is, change the trailing `});` into `})` and append the new property:

```cpp
        .def("FillLightConstants", [](const donut::engine::Light &self) {
            LightConstants constants{};
            self.FillLightConstants(constants);
            return py::bytes(reinterpret_cast<const char*>(&constants), sizeof(constants));
        })
        // Assigning a shadow map to a light is the entire shadow wiring: both lighting passes
        // read light->shadowMap themselves (DeferredLightingPass.cpp:163-192) to pull the
        // texture, its size and the per-cascade constants, so there is no pass input to plumb.
        // Assigning None is how the example's shadow toggle turns shadows off, with no pass
        // rebuild and no binding cache to clear.
        //
        // shadowChannel is deliberately left unbound: it selects a channel in the
        // shadowChannels texture, a screen-space shadow-mask path nothing here renders.
        .def_readwrite("shadowMap", &donut::engine::Light::shadowMap);
```

- [ ] **Step 6: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, immediately before `class Light(SceneGraphLeaf):` (line 1094):

```python
# The interface a shadow map implements, registered as a polymorphic base only -- everything it
# declares is called by the lighting passes in C++. Not constructible; see CascadedShadowMap.
class IShadowMap():
    pass

```

And inside `class Light`, after the `FillLightConstants` line (1098):

```python
    # Assigning this is the entire shadow wiring -- both lighting passes read it themselves.
    # None means "this light casts no shadow", and is how a shadow toggle is implemented.
    shadowMap: Optional[IShadowMap]
```

- [ ] **Step 7: Re-export from `__init__.py`**

In `src/pydonut/__init__.py`, add the import next to the other scene-graph types (near `from pydonut._pydonut import DirectionalLight`):

```python
from pydonut._pydonut import IShadowMap
```

and the matching `__all__` entry in the same relative position:

```python
    'IShadowMap',
```

- [ ] **Step 8: Rebuild and run the tests**

Run: `uv sync && uv run pytest -v`
Expected: PASS — the four new tests plus the 25 existing ones, 29 total.

- [ ] **Step 9: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_shadow_bindings.py
git commit -m "Bind IShadowMap and Light.shadowMap"
```

---

### Task 2: `CascadedShadowMap`

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (include near line 63; new class after the `BloomPass` block, line 2665)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_shadow_bindings.py`

**Interfaces:**
- Consumes: `pyd.IShadowMap` from Task 1.
- Produces: `pyd.CascadedShadowMap(device, resolution, numCascades, numPerObjectShadows, format, isUAV=False)` with `SetupForPlanarView(light, view, maxShadowDistance, lightSpaceZUp, lightSpaceZDown, exponent=4.0)`, `SetupForPlanarViewStable(...)` (same signature), `Clear(commandList)`, `GetView()`, `GetCascadeView(cascade)`, `GetTexture()`, `GetNumberOfCascades()`, `SetLitOutOfBounds(litOutOfBounds)`, `SetFalloffDistance(distance)`. Tasks 5, 6 and 7 use these.

- [ ] **Step 1: Write the failing test**

Append to `test/test_shadow_bindings.py`:

```python
def test_cascaded_shadow_map_is_a_shadow_map() -> None:
    assert issubclass(pyd.CascadedShadowMap, pyd.IShadowMap)


def test_cascaded_shadow_map_surface() -> None:
    for name in (
        "SetupForPlanarView",
        "SetupForPlanarViewStable",
        "Clear",
        "GetView",
        "GetCascadeView",
        "GetTexture",
        "GetNumberOfCascades",
        "SetLitOutOfBounds",
        "SetFalloffDistance",
    ):
        assert hasattr(pyd.CascadedShadowMap, name), name


def test_cascaded_shadow_map_skips_the_unsafe_cascade_setter() -> None:
    # SetNumberOfCascadesUnsafe only moves the count the *shaders* read; the composite view is
    # built once in the constructor (CascadedShadowMap.cpp:67) and never rebuilt, so lowering
    # the count through it would leave GetView() still rendering every allocated slice. The
    # cascade count is a construction parameter here instead -- see the spec.
    assert not hasattr(pyd.CascadedShadowMap, "SetNumberOfCascadesUnsafe")


def test_cascaded_shadow_map_setup_takes_a_view_not_a_frustum() -> None:
    # The frustum is pulled off the view C++-side: donut math types never cross into Python.
    # Nothing here constructs a shadow map (that needs a device), so this checks the signature
    # rejects the shape a frustum would have had.
    with pytest.raises(TypeError):
        pyd.CascadedShadowMap.SetupForPlanarView(None, None, (0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_shadow_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'CascadedShadowMap'`.

- [ ] **Step 3: Add the include**

In `src/cpp/_pydonut.cpp`, immediately after `#include <donut/render/BloomPass.h>` (line 63):

```cpp
#include <donut/render/CascadedShadowMap.h>
```

- [ ] **Step 4: Add the binding**

In `src/cpp/_pydonut.cpp`, immediately after the `BloomPass` binding ends (line 2665, the line ending `py::arg("sigmaInPixels"), py::arg("blendFactor"));`) and before the `FramebufferFactory` binding:

```cpp
    // Both setup calls take the PlanarView where C++ takes a dm::frustum (and, for the stable
    // variant, a dm::affine3): donut math types never cross into Python, and the view already
    // holds everything both fits need. They want *different* frustums -- the tight fit takes
    // the view frustum, the stable fit the projection frustum plus the inverse view matrix,
    // which is exactly what makes the stable fit independent of camera orientation
    // (CascadedShadowMap.h:64-76). Both accessors are on IView (View.h:71-74).
    //
    // preViewTranslation is left at its 0 default and not exposed: it belongs to renderers that
    // translate the world to keep the camera near the origin, which no example here does.
    // numberOfCascades is left at its -1 default (meaning "all allocated cascades") because the
    // cascade count is a *construction* parameter -- see the skip note below.
    //
    // Skipped: SetupForCubemapView and SetupPerObjectShadow (they need the light types and
    // per-object shadow slices a later stage binds), SetupProxyViews, GetPerObjectView, and
    // SetNumberOfCascadesUnsafe -- that setter only moves m_NumberOfCascades, which is what the
    // shaders read, while m_CompositeView is built once in the constructor (CascadedShadowMap.
    // cpp:67) and never rebuilt. Lowering the count through it would leave GetView() rendering
    // every allocated slice, burning a scene depth pass per unused cascade and writing into
    // slices whose view matrices were never set up. Recreating the map is the correct way to
    // change the count.
    py::class_<donut::render::CascadedShadowMap, donut::engine::IShadowMap,
        std::shared_ptr<donut::render::CascadedShadowMap>>(m, "CascadedShadowMap")
        .def(py::init([](nvrhi::IDevice* device, int resolution, int numCascades,
                int numPerObjectShadows, nvrhi::Format format, bool isUAV) {
            return new donut::render::CascadedShadowMap(device, resolution, numCascades,
                numPerObjectShadows, format, isUAV);
        }), py::arg("device"), py::arg("resolution"), py::arg("numCascades"),
            py::arg("numPerObjectShadows"), py::arg("format"), py::arg("isUAV") = false)
        .def("SetupForPlanarView", [](donut::render::CascadedShadowMap &self,
                const donut::engine::DirectionalLight &light, const donut::engine::PlanarView &view,
                float maxShadowDistance, float lightSpaceZUp, float lightSpaceZDown, float exponent) {
            return self.SetupForPlanarView(light, view.GetViewFrustum(), maxShadowDistance,
                lightSpaceZUp, lightSpaceZDown, exponent);
        }, py::arg("light"), py::arg("view"), py::arg("maxShadowDistance"),
            py::arg("lightSpaceZUp"), py::arg("lightSpaceZDown"), py::arg("exponent") = 4.0f)
        .def("SetupForPlanarViewStable", [](donut::render::CascadedShadowMap &self,
                const donut::engine::DirectionalLight &light, const donut::engine::PlanarView &view,
                float maxShadowDistance, float lightSpaceZUp, float lightSpaceZDown, float exponent) {
            return self.SetupForPlanarViewStable(light, view.GetProjectionFrustum(),
                view.GetInverseViewMatrix(), maxShadowDistance, lightSpaceZUp, lightSpaceZDown,
                exponent);
        }, py::arg("light"), py::arg("view"), py::arg("maxShadowDistance"),
            py::arg("lightSpaceZUp"), py::arg("lightSpaceZDown"), py::arg("exponent") = 4.0f)
        .def("Clear", &donut::render::CascadedShadowMap::Clear, py::arg("commandList"))
        // Returns the CompositeView holding one PlanarView per allocated cascade -- pass it
        // straight to RenderCompositeView to fill every cascade in one call. Note this is an
        // ICompositeView and *not* an IView: CompositeView derives from ICompositeView directly
        // (View.h:150), which is why Task 4 widens RenderCompositeView to ICompositeView.
        .def("GetView", [](donut::render::CascadedShadowMap &self) -> const donut::engine::ICompositeView* {
            return &self.GetView();
        }, py::return_value_policy::reference_internal)
        // Raw pointer, not the shared_ptr C++ returns: PlanarView is registered with pybind11's
        // default (unique_ptr) holder, so returning a shared_ptr<PlanarView> would not compile.
        // reference_internal keeps the owning shadow map alive for as long as Python holds the
        // view. The example renders every cascade through GetView(); this is here because
        // inspecting one cascade's fit is the first thing wanted when cascades look wrong.
        .def("GetCascadeView", [](donut::render::CascadedShadowMap &self, uint32_t cascade) -> donut::engine::PlanarView* {
            return self.GetCascadeView(cascade).get();
        }, py::arg("cascade"), py::return_value_policy::reference_internal)
        .def("GetTexture", [](donut::render::CascadedShadowMap &self) -> nvrhi::ITexture* {
            return self.GetTexture();
        }, py::return_value_policy::reference_internal)
        .def("GetNumberOfCascades", &donut::render::CascadedShadowMap::GetNumberOfCascades)
        .def("SetLitOutOfBounds", &donut::render::CascadedShadowMap::SetLitOutOfBounds,
            py::arg("litOutOfBounds"))
        .def("SetFalloffDistance", &donut::render::CascadedShadowMap::SetFalloffDistance,
            py::arg("distance"));

```

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, after the `BloomPass` class (line 1458) and before `class FramebufferFactory`:

```python
# A directional light's shadow map, as an array of cascade slices. The cascade count is fixed at
# construction: the composite view GetView() returns is built once in the constructor and never
# rebuilt, so changing the count means constructing a new CascadedShadowMap.
#
# Both setup calls take the PlanarView rather than a frustum -- donut math types never cross into
# Python, and the two fits want different frustums off it (view frustum for the tight fit,
# projection frustum plus inverse view matrix for the stable one). Both return True if any
# cascade's view changed. numCascades must be in [1, 4] and exponent must be > 1, both asserted
# in C++.
class CascadedShadowMap(IShadowMap):
    def __init__(self: CascadedShadowMap, device: Device, resolution: int, numCascades: int, numPerObjectShadows: int, format: Format, isUAV: bool = False) -> None: ...
    def SetupForPlanarView(self: CascadedShadowMap, light: DirectionalLight, view: PlanarView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
    def SetupForPlanarViewStable(self: CascadedShadowMap, light: DirectionalLight, view: PlanarView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
    def Clear(self: CascadedShadowMap, commandList: CommandList) -> None: ...
    # An ICompositeView, not an IView: one PlanarView per allocated cascade. Pass it to
    # RenderCompositeView to fill every cascade in a single call.
    def GetView(self: CascadedShadowMap) -> ICompositeView: ...
    def GetCascadeView(self: CascadedShadowMap, cascade: int) -> PlanarView: ...
    def GetTexture(self: CascadedShadowMap) -> Texture: ...
    # 0 until one of the setup calls has run -- the constructor allocates cascades but does not
    # activate them.
    def GetNumberOfCascades(self: CascadedShadowMap) -> int: ...
    def SetLitOutOfBounds(self: CascadedShadowMap, litOutOfBounds: bool) -> None: ...
    def SetFalloffDistance(self: CascadedShadowMap, distance: float) -> None: ...

```

- [ ] **Step 6: Re-export from `__init__.py`**

Add next to the other render passes (near `from pydonut._pydonut import BloomPass`):

```python
from pydonut._pydonut import CascadedShadowMap
```

and in `__all__`, in the same relative position:

```python
    'CascadedShadowMap',
```

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync && uv run pytest -v`
Expected: PASS — 33 tests.

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_shadow_bindings.py
git commit -m "Bind CascadedShadowMap"
```

---

### Task 3: `DepthPass`

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (include near line 56; new classes after the `GBufferFillPass` block, line 2370)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_shadow_bindings.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `pyd.DepthPass(device, commonPasses)` with `Init(shaderFactory, params)` and `ResetBindingCache()`; `pyd.DepthPassContext()`; `pyd.DepthPassCreateParameters()` with fields `depthBias`, `depthBiasClamp`, `slopeScaledDepthBias`, `trackLiveness`, `useInputAssembler`, `numConstantBufferVersions`. Tasks 5 and 6 use these.

- [ ] **Step 1: Write the failing test**

Append to `test/test_shadow_bindings.py`:

```python
def test_depth_pass_trio_is_exported() -> None:
    for name in ("DepthPass", "DepthPassContext", "DepthPassCreateParameters"):
        assert hasattr(pyd, name), name


def test_depth_pass_context_is_a_geometry_pass_context() -> None:
    # RenderCompositeView threads this through, so it has to convert to the base.
    assert issubclass(pyd.DepthPassContext, pyd.GeometryPassContext)


def test_depth_pass_is_a_geometry_pass() -> None:
    assert issubclass(pyd.DepthPass, pyd.IGeometryPass)


def test_depth_pass_create_parameter_defaults_match_the_header() -> None:
    # Mirrors DepthPass.h:75-88. A default drifting from the header is exactly what this
    # GPU-free test layer exists to catch.
    params = pyd.DepthPassCreateParameters()
    assert params.depthBias == 0
    assert params.depthBiasClamp == 0.0
    assert params.slopeScaledDepthBias == 0.0
    assert params.trackLiveness is True
    assert params.useInputAssembler is False
    assert params.numConstantBufferVersions == 16


def test_depth_pass_create_parameters_skip_material_bindings() -> None:
    # The pass builds its own MaterialBindingCache when this is null, and nothing in this repo
    # constructs one -- so it is deliberately unbound rather than overlooked.
    assert not hasattr(pyd.DepthPassCreateParameters(), "materialBindings")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_shadow_bindings.py -v`
Expected: FAIL — `AssertionError` on `DepthPass` missing from `pydonut`.

- [ ] **Step 3: Add the include**

In `src/cpp/_pydonut.cpp`, immediately after `#include <donut/render/GBufferFillPass.h>` (line 56):

```cpp
#include <donut/render/DepthPass.h>
```

- [ ] **Step 4: Add the bindings**

In `src/cpp/_pydonut.cpp`, immediately after the `GBufferFillPass` binding ends (line 2370) and before `py::class_<PyPassthroughDrawStrategy, ...>`:

```cpp
    // Same trio shape as GBufferFillPass above. depthBias/depthBiasClamp/slopeScaledDepthBias
    // are exposed because a shadow map is exactly the consumer that needs them; they take effect
    // at Init(), so changing one means recreating the pass.
    //
    // Skipped: materialBindings (the pass creates its own MaterialBindingCache when this is
    // null, and nothing in this repo constructs one) and PipelineKey (an internal detail of the
    // pass's own pipeline cache).
    py::class_<donut::render::DepthPass::CreateParameters>(m, "DepthPassCreateParameters")
        .def(py::init<>())
        .def_readwrite("depthBias", &donut::render::DepthPass::CreateParameters::depthBias)
        .def_readwrite("depthBiasClamp", &donut::render::DepthPass::CreateParameters::depthBiasClamp)
        .def_readwrite("slopeScaledDepthBias", &donut::render::DepthPass::CreateParameters::slopeScaledDepthBias)
        .def_readwrite("trackLiveness", &donut::render::DepthPass::CreateParameters::trackLiveness)
        .def_readwrite("useInputAssembler", &donut::render::DepthPass::CreateParameters::useInputAssembler)
        .def_readwrite("numConstantBufferVersions", &donut::render::DepthPass::CreateParameters::numConstantBufferVersions);

    py::class_<donut::render::DepthPass::Context, donut::render::GeometryPassContext>(m, "DepthPassContext")
        .def(py::init<>());

    py::class_<donut::render::DepthPass, donut::render::IGeometryPass, std::shared_ptr<donut::render::DepthPass>>(m, "DepthPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::CommonRenderPasses>>(),
            py::arg("device"), py::arg("commonPasses"))
        .def("Init", &donut::render::DepthPass::Init, py::arg("shaderFactory"), py::arg("params"))
        .def("ResetBindingCache", &donut::render::DepthPass::ResetBindingCache);

```

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, immediately after the `GBufferFillPass` class stub and before `class PassthroughDrawStrategy`:

```python
# Depth-only geometry pass. Its consumer here is the shadow map, which is why the depth bias
# fields are exposed -- they are applied at Init(), so changing one means a new pass.
# materialBindings is intentionally unbound: the pass creates its own when it is null.
class DepthPassCreateParameters():
    def __init__(self: DepthPassCreateParameters) -> None: ...
    depthBias: int
    depthBiasClamp: float
    slopeScaledDepthBias: float
    trackLiveness: bool
    useInputAssembler: bool
    numConstantBufferVersions: int

class DepthPassContext(GeometryPassContext):
    def __init__(self: DepthPassContext) -> None: ...

class DepthPass(IGeometryPass):
    def __init__(self: DepthPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: DepthPass, shaderFactory: ShaderFactory, params: DepthPassCreateParameters) -> None: ...
    def ResetBindingCache(self: DepthPass) -> None: ...

```

- [ ] **Step 6: Re-export from `__init__.py`**

Add next to the `GBufferFillPass` imports:

```python
from pydonut._pydonut import DepthPassCreateParameters
from pydonut._pydonut import DepthPassContext
from pydonut._pydonut import DepthPass
```

and in `__all__`, in the same relative position:

```python
    'DepthPassCreateParameters',
    'DepthPassContext',
    'DepthPass',
```

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync && uv run pytest -v`
Expected: PASS — 38 tests.

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_shadow_bindings.py
git commit -m "Bind DepthPass, DepthPassContext and DepthPassCreateParameters"
```

---

### Task 4: Widen `RenderCompositeView` and `RenderView`

The only task that changes an existing signature. Five other examples call these functions, so it ends by running all of them.

**Files:**
- Modify: `src/cpp/_pydonut.cpp:2686-2704`
- Modify: `src/pydonut/_pydonut.pyi:1467-1468`
- Test: `test/test_shadow_bindings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RenderCompositeView(commandList, view, viewPrev, framebufferFactory, rootNode, drawStrategy, pass_, passContext, materialEvents=False, passEvent=None)` where `view` is an `ICompositeView` and `viewPrev` may be `None`; and `RenderView(commandList, view, viewPrev, framebuffer, drawStrategy, pass_, context, materialEvents=False)` where both views are `IView` and `viewPrev` may be `None`. Task 6 calls the first with a `CascadedShadowMap.GetView()`.

**`passEvent` goes LAST, after `materialEvents`** — not in the C++ parameter order. Five examples call `RenderCompositeView`, but only `feature_demo.py` passes `materialEvents`, as the ninth *positional* argument, at three call sites; the other four stop at `passContext`. One positional caller is enough: inserting `passEvent` ahead of `materialEvents` would rebind those three arguments from the bool they mean to a str, so the decision stands as written.

- [ ] **Step 1: Write the failing test**

Append to `test/test_shadow_bindings.py`:

```python
def test_render_composite_view_takes_a_composite_view() -> None:
    # CascadedShadowMap.GetView() returns a CompositeView, which derives from ICompositeView and
    # is NOT an IView (View.h:55,150) -- an IView parameter would reject the very argument this
    # widening exists to accept. pybind11 renders the C++ type name here because ICompositeView
    # is registered further down the module than this function.
    doc = pyd.RenderCompositeView.__doc__
    assert "ICompositeView" in doc
    assert "PlanarView" not in doc


def test_render_composite_view_keeps_material_events_ninth() -> None:
    # feature_demo.py passes materialEvents positionally, at three call sites; no other example
    # passes it at all. passEvent is appended after it precisely so those three keep binding to
    # the argument they meant instead of silently taking a str for a bool.
    doc = pyd.RenderCompositeView.__doc__
    assert doc.index("materialEvents") < doc.index("passEvent")


def test_planar_view_still_converts_to_both_widened_parameters() -> None:
    # The widening's backward compatibility, checked where it actually lives: every existing
    # caller passes a PlanarView, and it keeps binding because PlanarView derives from IView
    # derives from ICompositeView. Calling the functions for real needs a device, so the five
    # examples that do are run in this task's verification step instead.
    assert issubclass(pyd.PlanarView, pyd.IView)
    assert issubclass(pyd.IView, pyd.ICompositeView)


def test_render_view_takes_an_iview() -> None:
    # RenderView's C++ signature takes const IView*, not ICompositeView* (GeometryPasses.h:70-78),
    # so it widens one step less far than RenderCompositeView.
    doc = pyd.RenderView.__doc__
    assert "IView" in doc
    assert "PlanarView" not in doc
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_shadow_bindings.py -v`
Expected: FAIL — the docstrings still read `view: donut::engine::PlanarView`.

- [ ] **Step 3: Widen the two bindings**

In `src/cpp/_pydonut.cpp`, replace lines 2686-2704 (both `m.def` blocks) with:

```cpp
    // view/viewPrev are IView, not PlanarView: the C++ takes const IView* (GeometryPasses.h:70-78)
    // and stage 1 bound only the concrete type it happened to call with. viewPrev accepts None --
    // the C++ has always allowed nullptr, and a pass with no history has no previous view.
    m.def("RenderView", [](nvrhi::ICommandList* commandList, donut::engine::IView &view,
            donut::engine::IView* viewPrev,
            nvrhi::IFramebuffer* framebuffer, donut::render::IDrawStrategy &drawStrategy,
            donut::render::IGeometryPass &pass,
            donut::render::GeometryPassContext &context, bool materialEvents) {
        donut::render::RenderView(commandList, &view, viewPrev, framebuffer, drawStrategy, pass,
            context, materialEvents);
    }, py::arg("commandList"), py::arg("view"), py::arg("viewPrev").none(true), py::arg("framebuffer"),
       py::arg("drawStrategy"), py::arg("pass"), py::arg("context"), py::arg("materialEvents") = false);

    // view/viewPrev are ICompositeView -- one step wider than RenderView, because this is the
    // call that renders a CascadedShadowMap's cascades in one go and CascadedShadowMap::GetView()
    // returns a CompositeView, which derives from ICompositeView and is NOT an IView
    // (View.h:55,150). PlanarView still converts, through IView.
    //
    // passEvent is the marker name the C++ has always taken and this binding used to hardcode to
    // nullptr; naming the shadow pass makes it legible in a graphics capture. It is appended
    // AFTER materialEvents rather than placed in the C++ parameter order on purpose: of the five
    // examples that call this function, feature_demo.py passes materialEvents as the ninth
    // positional argument (three call sites; the other four examples stop before it), and
    // inserting a parameter ahead of it would silently rebind those bools to a str.
    m.def("RenderCompositeView", [](nvrhi::ICommandList* commandList, donut::engine::ICompositeView &view,
            donut::engine::ICompositeView* viewPrev,
            donut::engine::FramebufferFactory &framebufferFactory, std::shared_ptr<donut::engine::SceneGraphNode> rootNode,
            donut::render::IDrawStrategy &drawStrategy, donut::render::IGeometryPass &pass,
            donut::render::GeometryPassContext &passContext, bool materialEvents,
            std::optional<std::string> passEvent) {
        donut::render::RenderCompositeView(commandList, &view, viewPrev, framebufferFactory, rootNode,
            drawStrategy, pass, passContext, passEvent ? passEvent->c_str() : nullptr, materialEvents);
    }, py::arg("commandList"), py::arg("view"), py::arg("viewPrev").none(true), py::arg("framebufferFactory"),
       py::arg("rootNode"), py::arg("drawStrategy"), py::arg("pass"), py::arg("passContext"),
       py::arg("materialEvents") = false, py::arg("passEvent") = py::none(),
       // See the comment on CommandList.open above -- released for threaded_rendering.py's
       // concurrent per-face recording. Safe: this walks read-only scene-graph/mesh/material
       // data and issues draws into the caller's own CommandList, touching no Python objects.
       // Argument conversion (including passEvent's string) completes before the guard applies.
       py::call_guard<py::gil_scoped_release>());
```

- [ ] **Step 4: Update the type stubs**

In `src/pydonut/_pydonut.pyi`, replace lines 1467-1468 with:

```python
def RenderView(commandList: CommandList, view: IView, viewPrev: Optional[IView], framebuffer: Framebuffer, drawStrategy: IDrawStrategy, pass_: IGeometryPass, context: GeometryPassContext, materialEvents: bool = False) -> None: ...
# view is an ICompositeView, one step wider than RenderView's IView: CascadedShadowMap.GetView()
# returns a CompositeView, which derives from ICompositeView directly and is not an IView.
# passEvent names the pass in a graphics capture. It sits after materialEvents rather than in the
# C++ parameter order because existing callers pass materialEvents positionally.
def RenderCompositeView(commandList: CommandList, view: ICompositeView, viewPrev: Optional[ICompositeView], framebufferFactory: FramebufferFactory, rootNode: SceneGraphNode, drawStrategy: IDrawStrategy, pass_: IGeometryPass, passContext: GeometryPassContext, materialEvents: bool = False, passEvent: Optional[str] = None) -> None: ...
```

- [ ] **Step 5: Rebuild and run the tests**

Run: `uv sync && uv run pytest -v`
Expected: PASS — 42 tests.

`viewPrev=None` has no assertion here on purpose: whether pybind11 renders `Optional[T]` for a
`.none(true)` pointer argument is version-dependent, so a docstring test for it could fail for a
reason unrelated to this code. Task 6 passes `None` for real, and the example run verifies it.

- [ ] **Step 6: Verify every existing caller still runs**

The widening is source-compatible by construction, but overload resolution and implicit conversion are where "obviously compatible" goes wrong. Run each of the five examples that call these functions, let each render for a few seconds, and close its window:

```bash
uv run deferred_shading.py
uv run threaded_rendering.py
uv run variable_shading.py
uv run rt_reflections.py
uv run rt_shadows.py
```

Expected for each: a rendered window, no `TypeError` in the console, no NVRHI validation errors.

- [ ] **Step 7: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi test/test_shadow_bindings.py
git commit -m "Widen RenderCompositeView to ICompositeView and add the pass marker name"
```

---

### Task 5: `feature_demo.py` — create the shadow map and depth pass

Everything is allocated and rebuilt correctly; nothing renders into it yet. The example must look exactly as it did before at the end of this task.

**Files:**
- Modify: `feature_demo.py`

**Interfaces:**
- Consumes: `pyd.CascadedShadowMap`, `pyd.DepthPass`, `pyd.DepthPassContext`, `pyd.DepthPassCreateParameters` from Tasks 2-3.
- Produces: `self.shadowMap`, `self.shadowFramebuffer`, `self.depthPass`, `self.depthContext`, and `CreateShadowMap()`. Task 6 renders with them; Task 7 drives the recreate.

- [ ] **Step 1: Add the module constants**

In `feature_demo.py`, immediately after the `SAMPLE_COUNTS` dict (near line 68):

```python
    # Fixed rather than a UI slider: changing it needs the same recreate path as the cascade
    # count, and a demo learns nothing from a resolution slider that the cascade slider does not
    # already show.
    SHADOW_MAP_RESOLUTION = 2048

    # Minimum depth range of the shadow projection along the light direction, in world units:
    # CascadedShadowMap takes max(cascade's own half-extent, this) for each side
    # (CascadedShadowMap.cpp:137-138), so these only matter for the near cascades, where they are
    # what keeps a caster above the camera from falling outside the box. Sized to Sponza with
    # headroom; not UI controls, because the only correct setting is "big enough".
    SHADOW_LIGHT_SPACE_Z_UP = 20.0
    SHADOW_LIGHT_SPACE_Z_DOWN = 20.0
```

- [ ] **Step 2: Add the UIData fields**

In `UIData.__init__`, immediately after `self.EnableAnimations = False`:

```python
            self.EnableShadows = True
            self.UseStableCascades = True
            self.ShadowCascades = 4
            self.MaxShadowDistance = 50.0
            # Must stay > 1.0: CascadedShadowMap.cpp:83 asserts on it, so a debug build aborts
            # at exactly 1.0.
            self.ShadowExponent = 4.0
            self.ShadowFalloffDistance = 1.0
            self.ShadowLitOutOfBounds = True
```

- [ ] **Step 3: Add the instance state**

In `FeatureDemo.__init__`, immediately after `self.bloomPass: pyd.BloomPass | None = None`:

```python
            self.shadowMap: pyd.CascadedShadowMap | None = None
            self.shadowFramebuffer: pyd.FramebufferFactory | None = None
            self.depthPass: pyd.DepthPass | None = None
            self.depthContext = pyd.DepthPassContext()
            self.shadowMapCascades = 0
```

- [ ] **Step 4: Create the depth pass in `Init`**

In `FeatureDemo.Init`, immediately after the `self.forwardPass.Init(...)` call and before `return True`:

```python
            # Size-independent, like the other geometry passes: it is created once here and
            # only recreated on a shader reload. depthBias/slopeScaledDepthBias take effect at
            # Init(), which is why they are constants rather than sliders -- a bias slider would
            # mean recreating the pass on every drag.
            depthParams = pyd.DepthPassCreateParameters()
            depthParams.depthBias = 100
            depthParams.slopeScaledDepthBias = 2.0
            self.depthPass = pyd.DepthPass(device, self.m_CommonPasses)
            self.depthPass.Init(self.shaderFactory, depthParams)

            self.CreateShadowMap()
```

- [ ] **Step 5: Add `CreateShadowMap`**

In `feature_demo.py`, immediately before `def CreateSunLight(...)`:

```python
        def CreateShadowMap(self: FeatureDemo) -> None:
            """(Re)builds the cascaded shadow map and the framebuffer factory over it.

            Deliberately NOT part of CreateRenderPasses. That runs off
            RenderTargets.IsUpdateRequired(width, height, sampleCount), and this map's size comes
            from the UI, not the back buffer -- folding it in would destroy and reallocate a
            64 MB texture array on every window resize and every AA-mode change, for nothing.

            Called from Init, and again whenever the cascade count changes. The cascade count is
            a construction parameter because the composite view GetView() returns is built once
            in the constructor and never rebuilt (CascadedShadowMap.cpp:67).
            """
            device = self.GetDevice()

            # Released before the replacement is allocated, so the two 64 MB arrays are not both
            # resident: the same reason the render-target rebuild block clears first. The light
            # is unhooked first -- it holds a shared_ptr to the outgoing map, so dropping only
            # this reference would keep it alive.
            #
            # depthPass.ResetBindingCache() is deliberately NOT called: it clears material
            # bindings and vertex-buffer SRVs (DepthPass.cpp:91-95), neither of which references
            # the shadow texture. Nothing the pass caches becomes stale when this map is
            # replaced.
            self.shadowMap = None
            self.shadowFramebuffer = None
            if self.sunLight is not None:
                self.sunLight.shadowMap = None

            self.shadowMapCascades = self.ui.ShadowCascades
            self.shadowMap = pyd.CascadedShadowMap(
                device,
                SHADOW_MAP_RESOLUTION,
                self.shadowMapCascades,
                0,  # no per-object shadows: they need light types stage 2b binds
                pyd.Format.D32,
                False,
            )
            self.shadowMap.SetFalloffDistance(self.ui.ShadowFalloffDistance)
            self.shadowMap.SetLitOutOfBounds(self.ui.ShadowLitOutOfBounds)

            # One factory serves every cascade: it caches framebuffers per subresource set
            # (FramebufferFactory.cpp:30) and each cascade view carries its own array slice.
            self.shadowFramebuffer = pyd.FramebufferFactory(device)
            self.shadowFramebuffer.depthTarget = self.shadowMap.GetTexture()

```

`CreateShadowMap` is called from `Init` **after** `CreateSunLight()` has run, so `self.sunLight` already exists; the `is not None` guard is for the recreate path in Task 7, which can run before a scene is loaded.

- [ ] **Step 6: Rebuild the depth pass on a shader reload**

In `FeatureDemo.ReloadShaders`, immediately after the `self.forwardPass.Init(...)` call:

```python
            # Holds pipelines compiled from the bytecode ClearCache just dropped, so it is
            # rebuilt with the other geometry passes. The shadow map itself holds no shaders and
            # is left alone.
            depthParams = pyd.DepthPassCreateParameters()
            depthParams.depthBias = 100
            depthParams.slopeScaledDepthBias = 2.0
            self.depthPass = pyd.DepthPass(device, self.m_CommonPasses)
            self.depthPass.Init(self.shaderFactory, depthParams)
```

Nothing is added to `Render`'s render-target release block. That block drops binding sets that
reference back-buffer-sized textures; `DepthPass::ResetBindingCache` clears material bindings and
vertex-buffer SRVs (`DepthPass.cpp:91-95`), which reference neither the render targets nor the
shadow map. Adding it there would be cargo-culting the lines above it.

- [ ] **Step 7: Run it**

Run: `uv run feature_demo.py`
Expected: the example renders exactly as before — no visual change, since nothing renders into the shadow map yet and no light references it. Resize the window and switch AA modes: still no errors.

- [ ] **Step 8: Run under the debug layers**

Run: `uv run feature_demo.py -debug`
Expected: no D3D debug-layer or NVRHI validation errors. In particular, allocating a 2048×2048×4 D32 typeless array must not warn.

- [ ] **Step 9: Commit**

```bash
git add feature_demo.py
git commit -m "Create the cascaded shadow map and depth pass in feature_demo.py"
```

---

### Task 6: `feature_demo.py` — render the cascades and light the scene with them

**Files:**
- Modify: `feature_demo.py`

**Interfaces:**
- Consumes: everything Task 5 produced, plus the widened `RenderCompositeView` from Task 4.
- Produces: `RenderShadowMap(commandList)`; shadows visible on both shading paths.

- [ ] **Step 1: Add `RenderShadowMap`**

In `feature_demo.py`, immediately after `CreateShadowMap`:

```python
        def RenderShadowMap(self: FeatureDemo, commandList: pyd.CommandList) -> None:
            """Fits the cascades to the current view, clears the map and fills every cascade.

            Runs before the G-buffer fill or forward opaque pass: the lighting passes sample this
            texture in the same frame.
            """
            assert self.shadowMap is not None and self.sunLight is not None

            # The two fits differ in what they take off the view -- the tight one the view
            # frustum, the stable one the projection frustum plus the inverse view matrix -- but
            # the binding hides that, so both take the view itself.
            setup = (
                self.shadowMap.SetupForPlanarViewStable
                if self.ui.UseStableCascades
                else self.shadowMap.SetupForPlanarView
            )
            setup(
                self.sunLight,
                self.view,
                self.ui.MaxShadowDistance,
                SHADOW_LIGHT_SPACE_Z_UP,
                SHADOW_LIGHT_SPACE_Z_DOWN,
                self.ui.ShadowExponent,
            )

            self.shadowMap.Clear(commandList)

            # One call fills every cascade: GetView() is the composite of the per-cascade planar
            # views, and RenderCompositeView iterates it. viewPrev is None -- a shadow map has no
            # history, and nothing in a depth-only pass reads motion vectors.
            pyd.RenderCompositeView(
                commandList,
                self.shadowMap.GetView(),
                None,
                self.shadowFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                self.depthPass,
                self.depthContext,
                self.ui.EnableMaterialEvents,
                "ShadowMap",
            )

```

- [ ] **Step 2: Render it, and attach it to the sun**

In `FeatureDemo.Render`, immediately after `self.renderTargets.Clear(self.commandList)` and before the `ambient = self.ui.AmbientIntensity` line:

```python
            # Assigning the map to the light is the entire wiring -- both lighting passes read
            # light->shadowMap themselves. None is the off switch, and costs nothing but a null
            # check inside those passes, so the toggle needs no pass rebuild.
            if self.ui.EnableShadows:
                self.RenderShadowMap(self.commandList)
                self.sunLight.shadowMap = self.shadowMap
            else:
                self.sunLight.shadowMap = None
```

- [ ] **Step 3: Run and verify shadows on the deferred path**

Run: `uv run feature_demo.py`
Expected: Sponza is shadowed — the pillars and the upper gallery cast onto the floor, and the two robots cast onto whatever is under them. Unchecking "Deferred Shading" is not yet possible from the UI for shadows (Task 7 adds the section), but the deferred path is the default, so this is what the first run shows.

- [ ] **Step 4: Verify shadows on the forward path**

Temporarily change `UIData.__init__`'s `self.UseDeferredShading = True` to `False`, run `uv run feature_demo.py`, confirm the shadows are still there, then change it back to `True`.

Expected: shadows present on both paths. The forward pass reads the same `light->shadowMap`, so a difference here means the shadow map itself is wrong, not the wiring.

- [ ] **Step 5: Run under the debug layers**

Run: `uv run feature_demo.py -debug`
Expected: no validation errors. The most likely one here is a resource-state mismatch on the shadow texture — it is created in `ShaderResource` with `keepInitialState`, and NVRHI transitions it for the depth writes itself.

- [ ] **Step 6: Commit**

```bash
git add feature_demo.py
git commit -m "Render the cascaded shadow map and light Sponza with it"
```

---

### Task 7: `feature_demo.py` — the Shadows UI section

**Files:**
- Modify: `feature_demo.py`

**Interfaces:**
- Consumes: the `UIData` fields from Task 5 and `CreateShadowMap` from Task 5.
- Produces: nothing later tasks depend on. This is the last task.

- [ ] **Step 1: Add the UI section**

In `UIRenderer.buildUI`, immediately before `if pyd.ImGui.CollapsingHeader("Sky"):`:

```python
            if pyd.ImGui.CollapsingHeader("Shadows"):
                _, self.ui.EnableShadows = pyd.ImGui.Checkbox("Enabled", self.ui.EnableShadows)

                _, self.ui.UseStableCascades = pyd.ImGui.Checkbox(
                    "Stable Cascades", self.ui.UseStableCascades
                )
                pyd.ImGui.SameLine()
                pyd.ImGui.Text("(off = tighter fit, edges shimmer when turning)")

                # Changing the count recreates the shadow map: the composite view is built once
                # in the constructor, so the count cannot be lowered in place without leaving
                # GetView() rendering slices that were never set up.
                #
                # A Combo, not a slider: ImGui.SliderInt is not bound (only SliderFloat is), and
                # four discrete values do not need one. The index is the count minus one.
                changed, cascadeIndex = pyd.ImGui.Combo(
                    "Cascades", self.ui.ShadowCascades - 1, ["1", "2", "3", "4"]
                )
                if changed:
                    self.ui.ShadowCascades = cascadeIndex + 1

                _, self.ui.MaxShadowDistance = pyd.ImGui.SliderFloat(
                    "Max Distance", self.ui.MaxShadowDistance, 5.0, 200.0
                )
                # Lower bound is 1.01, not 1.0: CascadedShadowMap.cpp:83 asserts exponent > 1,
                # so a debug build aborts at exactly 1.0.
                _, self.ui.ShadowExponent = pyd.ImGui.SliderFloat(
                    "Cascade Distribution", self.ui.ShadowExponent, 1.01, 8.0
                )

                changed, falloff = pyd.ImGui.SliderFloat(
                    "Falloff Distance", self.ui.ShadowFalloffDistance, 0.0, 10.0
                )
                if changed and self.app.shadowMap is not None:
                    self.ui.ShadowFalloffDistance = falloff
                    self.app.shadowMap.SetFalloffDistance(falloff)

                changed, litOutOfBounds = pyd.ImGui.Checkbox(
                    "Lit Out Of Bounds", self.ui.ShadowLitOutOfBounds
                )
                if changed and self.app.shadowMap is not None:
                    self.ui.ShadowLitOutOfBounds = litOutOfBounds
                    self.app.shadowMap.SetLitOutOfBounds(litOutOfBounds)

```

- [ ] **Step 2: Recreate the shadow map when the cascade count changes**

In `FeatureDemo.Render`, immediately after the `if self.ui.ShaderReloadRequested:` block near the top:

```python
            # A discrete UI change, not a per-frame check that could thrash: shadowMapCascades is
            # what the current map was built with, so this fires once per slider change.
            if self.ui.ShadowCascades != self.shadowMapCascades:
                self.GetDevice().waitForIdle()
                self.CreateShadowMap()
```

`waitForIdle` because the outgoing texture may still be referenced by frames in flight, and the replacement is allocated immediately.

- [ ] **Step 3: Run and exercise every control**

Run: `uv run feature_demo.py`
Expected, each verified by hand:
- "Enabled" unchecked removes shadows with no hitch and no rebuild.
- "Stable Cascades" toggled while turning the camera visibly changes shadow-edge shimmer.
- The cascade count taking effect live, with a brief pause on change (the recreate) and no error.
- "Max Distance" moving the far edge of the shadowed region.
- "Cascade Distribution" changing how the cascade splits are spaced.
- "Lit Out Of Bounds" changing whether geometry beyond the last cascade is lit or dark.

- [ ] **Step 4: Verify the resize path does NOT touch the shadow map**

Add a temporary `print("shadow map rebuilt", flush=True)` at the end of `CreateShadowMap`, run the example, resize the window several times and switch through every AA mode.

Expected: the line prints **once**, at startup — never on a resize or AA change. That is the whole point of `CreateShadowMap` standing apart from `CreateRenderPasses`. Remove the print afterwards.

- [ ] **Step 5: Verify every AA mode**

Run: `uv run feature_demo.py -debug` and cycle all five AA modes with shadows on.
Expected: no validation errors. MSAA is the interesting one — the shadow map is single-sampled while the G-buffer is not, and the forward path is what runs there.

- [ ] **Step 6: Confirm the binding tests still pass**

Run: `uv run pytest -v`
Expected: 42 passed.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Add the shadow settings UI to feature_demo.py"
```

---

## Stage 2a Done

At this point `feature_demo.py` renders Sponza with cascaded sun shadows on both shading paths, with a live cascade-fit toggle, and `uv run pytest` covers the new binding surface. Stage 2b (scene cameras, material/light editors, spot and point lights) gets its own spec and plan.
