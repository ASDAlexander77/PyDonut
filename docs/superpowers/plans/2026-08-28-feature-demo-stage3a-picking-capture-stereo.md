# FeatureDemo Stage 3a Implementation Plan — picking, capture and stereo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port FeatureDemo's right-click MaterialID picking, screenshots, MipMapGen test pass and stereo rendering into `feature_demo.py`, adding the native bindings each needs.

**Architecture:** Seven tasks. Task 1 widens ten bound view parameters that were narrowed to `PlanarView` — a correctness fix on its own merits and a hard prerequisite for stereo. Tasks 2–4 add the new bindings for picking, capture and stereo, each with its own new GPU-free test file. Tasks 5–7 wire each feature into `feature_demo.py`.

**Tech Stack:** C++17, pybind11 3.x (`src/cpp/_pydonut.cpp`), NVIDIA Donut (vendored at `extern/donut`), Python 3.11+, pytest, uv, scikit-build-core.

**Spec:** `docs/superpowers/specs/2026-08-28-feature-demo-stage3a-picking-capture-stereo-design.md`

## Global Constraints

- **No Donut math types cross into Python.** Vectors go in as flat scalars and come back as Python tuples. Precedent: `SceneGraphNode.GetWorldPosition` returns `tuple[float, float, float]`; `TemporalAntiAliasingPass.GetCurrentPixelOffset` returns a 2-tuple. This applies to `dm::box3`, `dm::uint2`, `dm::uint4`, `dm::float4`, `dm::int4`, `dm::affine3` and `dm::float4x4`.
- **No GLFW constants are bound.** Use the raw numeric code with a naming comment, the convention already in `feature_demo.py:762`, `rt_bindless.py:198`, `threaded_rendering.py:197`.
- **Tests in `test/` are GPU-free surface tests.** They construct no device and render nothing. Anything needing a device is verified by running the example instead and gets a presence/signature check in the test file. Do not add a device fixture.
- **Every new binding gets a matching entry in `src/pydonut/_pydonut.pyi` and a re-export in `src/pydonut/__init__.py`** (both the `from pydonut._pydonut import X` line and the `'X'` entry in `__all__`).
- **Every new enum binds all of its real values,** not only those the example currently uses. (Stage 2c shipped a `MaterialDomain` binding with 2 of 6 values and it raised `ValueError` on real scene data.)
- **Asserts are compiled out in this project's Release build.** A Donut method whose failure path is `assert(false)` fails silently here. Treat every such method as a live hazard.
- Every task ends with `uv run pytest` green. Baseline entering this plan: **74 tests**.
- Copyright header: every new file under `test/` starts with the same 22-line `Copyright (C) 1991-2026 ASDAlexander77` block used by `test/test_camera_bindings.py:1-22`. Copy it verbatim.

## Deviations from the spec, decided while planning

Three spec statements are corrected here. Implementers follow this plan.

1. **Spec says the tests check that `MaterialIDPass`, `MipMapGenPass` and `SaveTextureToFile` behave** ("is constructible", "returns `False` for an unwritable path"). All three need a live device, which this test layer never creates. Each becomes a presence-and-signature check, with a comment naming what a device would have proven.
2. **Spec says `CreateRenderPasses` builds `materialIDPass`.** It builds `pixelReadbackPass` and `mipMapGenPass` there — both bind a texture that is recreated on resize — but `materialIDPass` holds only pipelines, so it goes where `gbufferPass` already lives: `Init` and `ReloadShaders`. The C++ sample puts all three in `CreateRenderPasses` (`FeatureDemo.cpp:800-804`), but the Python port already deliberately split size-independent geometry passes out of that method. Matching the port's own structure beats matching the sample's here.
3. **Spec's bounding-box test says "mins componentwise `<=` maxs".** `box3::empty()` is mins = `FLT_MAX`, maxs = `-FLT_MAX` (`box.h:139-143`), so a fresh node's box has mins **greater** than maxs. The test pins that sentinel instead, and Task 5 guards `PointThirdPersonCameraAt` against it.

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/cpp/_pydonut.cpp` | All binding changes: ten widened signatures, six new classes/functions | 1, 2, 3, 4 |
| `src/pydonut/_pydonut.pyi` | Type stubs mirroring every binding change | 1, 2, 3, 4 |
| `src/pydonut/__init__.py` | Re-exports for the new public names | 2, 3, 4 |
| `test/test_shadow_bindings.py` | Existing; owns the widening-convention tests since stage 2b | 1 |
| `test/test_picking_bindings.py` | New; picking bindings | 2 |
| `test/test_capture_bindings.py` | New; MipMapGen, screenshot and file-dialog bindings | 3 |
| `test/test_stereo_bindings.py` | New; `StereoPlanarView` | 4 |
| `feature_demo.py` | The example itself | 5, 6, 7 |

---

## Task 1: Widen the ten narrowed view signatures

Ten bound call sites take a concrete `donut::engine::PlanarView&` where the C++ they wrap takes `const ICompositeView&` or `const IView&`. A stereo view cannot pass through any of them. Nine widen mechanically; `SetupForPlanarViewStable` also needs a correction that prevents a silent Release-build failure.

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (ten sites, listed in Step 3)
- Modify: `src/pydonut/_pydonut.pyi:833`, `:837`, `:1394`, `:1462`, `:1512`, `:1513`, `:1514`, `:1611`, `:1612`, `:1630`
- Test: `test/test_shadow_bindings.py` (update one test, add four)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CommandList.clearTextureFloat(texture, clearColor, view: IView)`, `CommandList.clearDepthStencilTexture(texture, clearDepth, depth, clearStencil, stencil, view: IView)`, `GBufferRenderTargets.GetFramebuffer(view: IView) -> Framebuffer`, `DeferredLightingPass.Render(commandList, view: ICompositeView, inputs)`, `TemporalAntiAliasingPass.__init__(device, shaderFactory, commonPasses, compositeView: ICompositeView, params)`, `TemporalAntiAliasingPass.RenderMotionVectors(commandList, compositeView: ICompositeView, compositeViewPrevious: ICompositeView)`, `TemporalAntiAliasingPass.TemporalResolve(commandList, params, feedbackIsValid, compositeViewInput: ICompositeView, compositeViewOutput: ICompositeView)`, `CascadedShadowMap.SetupForPlanarView(light, view: IView, maxShadowDistance, lightSpaceZUp, lightSpaceZDown, exponent=4.0) -> bool`, `CascadedShadowMap.SetupForPlanarViewStable(light, view: IView, maxShadowDistance, lightSpaceZUp, lightSpaceZDown, exponent=4.0) -> bool`, `FramebufferFactory.GetFramebuffer(view: IView) -> Framebuffer`. Task 4 relies on all ten accepting a `StereoPlanarView`.

- [ ] **Step 1: Record the baseline**

Run: `uv run pytest -q`

Expected: 74 passed. Write the number down; every later task's expected count is derived from it. If it is not 74, use the real number and say so in the commit message.

- [ ] **Step 2: Update the one existing test the widening invalidates, and add four new ones**

`test/test_shadow_bindings.py:108-120` currently asserts the **old** spelling and will fail after Step 3. Replace that whole function with the version below, then append the four new tests to the end of the file.

**Critical detail:** `pyd.CascadedShadowMap.SetupForPlanarView.__doc__` begins with the method's own name, which contains the substring `PlanarView`. A bare `assert "PlanarView" not in doc` would fail even after a correct widening. Assert on the qualified parameter spelling `"view: donut::engine::PlanarView"` instead — that is why the original test was written that way.

```python
def test_cascaded_shadow_map_setup_takes_a_view_not_a_frustum() -> None:
    # The frustum is pulled off the view C++-side: donut math types never cross into Python.
    # Nothing here constructs a shadow map (that needs a device), so this checks the bound
    # signature names a view type for `view` and that no frustum type appears anywhere in it.
    #
    # IView, not PlanarView: a stereo view has to reach both setup calls, and both of the
    # accessors they use (GetViewFrustum, GetProjectionFrustum) are declared on IView
    # (View.h:71-72) and meaningfully overridden by StereoView (View.h:235-255).
    #
    # Assert the *qualified parameter* spelling, not a bare "PlanarView" substring: the method
    # name itself contains "PlanarView", so a bare check can never fail here. pybind11 renders
    # the C++ type name because CascadedShadowMap is registered ahead of IView in the module.
    for setup in (
        pyd.CascadedShadowMap.SetupForPlanarView,
        pyd.CascadedShadowMap.SetupForPlanarViewStable,
    ):
        doc = setup.__doc__
        assert doc is not None
        assert "view: donut::engine::IView" in doc
        assert "view: donut::engine::PlanarView" not in doc
        assert "Frustum" not in doc


def test_deferred_lighting_render_takes_a_composite_view() -> None:
    # DeferredLightingPass::Render takes const ICompositeView& (DeferredLightingPass.h:97-101);
    # the binding narrowed it to PlanarView, which a stereo view cannot satisfy.
    doc = pyd.DeferredLightingPass.Render.__doc__
    assert doc is not None
    assert "ICompositeView" in doc
    assert "PlanarView" not in doc


def test_temporal_aa_signatures_take_composite_views() -> None:
    # All three take const ICompositeView& in C++ (TemporalAntiAliasingPass.h:106-124). The
    # constructor matters as much as the two render calls: the pass caches state derived from
    # the view it was built with.
    for member in (
        pyd.TemporalAntiAliasingPass.__init__,
        pyd.TemporalAntiAliasingPass.RenderMotionVectors,
        pyd.TemporalAntiAliasingPass.TemporalResolve,
    ):
        doc = member.__doc__
        assert doc is not None
        assert "ICompositeView" in doc
        assert "PlanarView" not in doc


def test_get_framebuffer_signatures_take_an_iview() -> None:
    # FramebufferFactory::GetFramebuffer takes const IView& (FramebufferFactory.h:48) -- one
    # step narrower than ICompositeView, because it needs GetSubresources.
    for member in (
        pyd.FramebufferFactory.GetFramebuffer,
        pyd.GBufferRenderTargets.GetFramebuffer,
    ):
        doc = member.__doc__
        assert doc is not None
        assert "view: donut::engine::IView" in doc
        assert "view: donut::engine::PlanarView" not in doc


def test_view_scoped_clear_overloads_take_an_iview() -> None:
    # Both overloads call view.GetSubresources(), declared on IView. __doc__ here carries every
    # overload of the name, so the AllSubresources variants appear alongside the view-taking ones.
    for member in (
        pyd.CommandList.clearTextureFloat,
        pyd.CommandList.clearDepthStencilTexture,
    ):
        doc = member.__doc__
        assert doc is not None
        assert "view: donut::engine::IView" in doc
        assert "PlanarView" not in doc
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest test/test_shadow_bindings.py -q`

Expected: 5 failures — the updated `test_cascaded_shadow_map_setup_takes_a_view_not_a_frustum` plus the four new ones, each on an assertion about `IView`/`ICompositeView` not appearing in a docstring that still says `PlanarView`.

- [ ] **Step 4: Widen the eight mechanical `PlanarView` parameters**

In `src/cpp/_pydonut.cpp`, change only the parameter type on each of these. Do not touch the lambda bodies, the `py::arg` names, the defaults, the return policies or the `call_guard`s.

| Line | Binding | Change |
|---|---|---|
| 1703 | `clearTextureFloat` (view overload) | `const donut::engine::PlanarView &view` → `const donut::engine::IView &view` |
| 1711 | `clearDepthStencilTexture` (view overload) | same |
| 2520 | `GBufferRenderTargets.GetFramebuffer` | `donut::engine::PlanarView &view` → `const donut::engine::IView &view` |
| 2619 | `DeferredLightingPass.Render` | `donut::engine::PlanarView &view` → `const donut::engine::ICompositeView &view` |
| 2706 | `TemporalAntiAliasingPass` ctor | `donut::engine::PlanarView &compositeView` → `const donut::engine::ICompositeView &compositeView` |
| 2711 | `RenderMotionVectors` | both `donut::engine::PlanarView &` → `const donut::engine::ICompositeView &` |
| 2716 | `TemporalResolve` | both `donut::engine::PlanarView &` → `const donut::engine::ICompositeView &` |
| 2980 | `FramebufferFactory.GetFramebuffer` | `donut::engine::PlanarView &view` → `const donut::engine::IView &view` |

Also update the stale comment at `src/cpp/_pydonut.cpp:2881-2886`, which claims "Both setup calls take the PlanarView". Replace that sentence with:

```cpp
    // Both setup calls take an IView where C++ takes a dm::frustum (and, for the stable
    // variant, a dm::affine3): donut math types never cross into Python, and the view already
```

- [ ] **Step 5: Widen the two `CascadedShadowMap` setup calls, correcting the stable variant**

`SetupForPlanarView` is pure widening — `GetViewFrustum` is declared on `IView` and `StereoView` overrides it meaningfully (`View.h:235-244`):

```cpp
        .def("SetupForPlanarView", [](donut::render::CascadedShadowMap &self,
                const donut::engine::DirectionalLight &light, const donut::engine::IView &view,
                float maxShadowDistance, float lightSpaceZUp, float lightSpaceZDown, float exponent) {
            RequireCascadeExponent("SetupForPlanarView", exponent);
            return self.SetupForPlanarView(light, view.GetViewFrustum(), maxShadowDistance,
                lightSpaceZUp, lightSpaceZDown, exponent);
        }, py::arg("light"), py::arg("view"), py::arg("maxShadowDistance"),
            py::arg("lightSpaceZUp"), py::arg("lightSpaceZDown"), py::arg("exponent") = 4.0f)
```

`SetupForPlanarViewStable` needs more than a type change. It currently calls `view.GetInverseViewMatrix()`, which `StereoView` overrides to `assert(false); return dm::affine3::identity()` (`View.h:263-267`). Asserts compile out in this project's Release build, so under stereo that would hand the shadow fit an identity matrix and place every cascade at the world origin — no crash, no error, just wrong shadows. Take it from the first planar child view, exactly as `FeatureDemo.cpp:944` does:

```cpp
        .def("SetupForPlanarViewStable", [](donut::render::CascadedShadowMap &self,
                const donut::engine::DirectionalLight &light, const donut::engine::IView &view,
                float maxShadowDistance, float lightSpaceZUp, float lightSpaceZDown, float exponent) {
            RequireCascadeExponent("SetupForPlanarViewStable", exponent);
            // GetProjectionFrustum is safe on the composite view -- StereoView overrides it to
            // merge both eyes' frusta (View.h:246-255). GetInverseViewMatrix is NOT: StereoView
            // overrides it to assert(false) + identity (View.h:263-267), and asserts compile out
            // in this project's Release build, so a stereo view would silently fit every cascade
            // around the world origin. Take it from a planar child view instead, as
            // FeatureDemo.cpp:944 does. IView::GetChildView returns `this` for a PlanarView, so
            // this is unchanged behaviour for the non-stereo callers.
            const donut::engine::IView* planarView =
                view.GetChildView(donut::engine::ViewType::PLANAR, 0);
            return self.SetupForPlanarViewStable(light, view.GetProjectionFrustum(),
                planarView->GetInverseViewMatrix(), maxShadowDistance, lightSpaceZUp,
                lightSpaceZDown, exponent);
        }, py::arg("light"), py::arg("view"), py::arg("maxShadowDistance"),
            py::arg("lightSpaceZUp"), py::arg("lightSpaceZDown"), py::arg("exponent") = 4.0f)
```

- [ ] **Step 6: Mirror all ten in the type stubs**

In `src/pydonut/_pydonut.pyi`, change the annotated type on each line. Nothing else on these lines changes.

```python
# line 833
    def clearTextureFloat(self: CommandList, texture: Texture, clearColor: Color, view: IView) -> None: ...
# line 837
    def clearDepthStencilTexture(self: CommandList, texture: Texture, clearDepth: bool, depth: float, clearStencil: bool, stencil: int, view: IView) -> None: ...
# line 1394
    def GetFramebuffer(self: GBufferRenderTargets, view: IView) -> Framebuffer: ...
# line 1462
    def Render(self: DeferredLightingPass, commandList: CommandList, view: ICompositeView, inputs: DeferredLightingPassInputs) -> None: ...
# line 1512
    def __init__(self: TemporalAntiAliasingPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, compositeView: ICompositeView, params: TemporalAntiAliasingCreateParameters) -> None: ...
# line 1513
    def RenderMotionVectors(self: TemporalAntiAliasingPass, commandList: CommandList, compositeView: ICompositeView, compositeViewPrevious: ICompositeView) -> None: ...
# line 1514
    def TemporalResolve(self: TemporalAntiAliasingPass, commandList: CommandList, params: TemporalAntiAliasingParameters, feedbackIsValid: bool, compositeViewInput: ICompositeView, compositeViewOutput: ICompositeView) -> None: ...
# line 1611
    def SetupForPlanarView(self: CascadedShadowMap, light: DirectionalLight, view: IView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
# line 1612
    def SetupForPlanarViewStable(self: CascadedShadowMap, light: DirectionalLight, view: IView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
# line 1630
    def GetFramebuffer(self: FramebufferFactory, view: IView) -> Framebuffer: ...
```

Add this comment directly above the `SetupForPlanarViewStable` stub at line 1612:

```python
    # Takes its inverse view matrix from a planar child view, not from `view` itself: a stereo
    # view's own GetInverseViewMatrix is assert(false) + identity, which is silent in Release.
```

- [ ] **Step 7: Rebuild and run the full suite**

Run: `uv sync && uv run pytest -q`

Expected: 78 passed (74 baseline + 4 new; the fifth changed test was already counted).

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi test/test_shadow_bindings.py
git commit -m "Widen ten bound view parameters from PlanarView to IView/ICompositeView

The C++ these wrap already takes const ICompositeView&/const IView&; the
bindings narrowed it, so no composite view could reach them.

SetupForPlanarViewStable also changes behaviour: it now takes its inverse
view matrix from a planar child view. StereoView overrides
GetInverseViewMatrix to assert(false) + identity, and asserts compile out
in this project's Release build, so a stereo view would have silently
fitted every shadow cascade around the world origin."
```

**Manual verification (not a blocking gate — needs a GPU and a display):** run `uv run deferred_shading.py`, `uv run rt_bindless.py` and `uv run threaded_rendering.py`. Each drives at least one of the widened passes. A `PlanarView` still converts because it derives from `IView` derives from `ICompositeView`, so no example source changes; these runs are what prove that in practice. Report the result; do not block the task on being unable to run them headless.

---

## Task 2: Picking bindings

**Files:**
- Modify: `src/cpp/_pydonut.cpp`
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_picking_bindings.py` (create)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces, for Task 5: `pyd.MaterialIDPass(device, commonPasses)` with `.Init(shaderFactory, params)`; `pyd.PixelReadbackPass(device, shaderFactory, inputTexture, format, arraySlice=0, mipLevel=0)` with `.Capture(commandList, x, y)`, `.ReadUInts() -> tuple[int, int, int, int]`, `.ReadFloats() -> tuple[float, ...]`, `.ReadInts() -> tuple[int, ...]`; `CommandList.clearTextureUInt(texture, clearValue)` and `CommandList.clearTextureUInt(texture, clearValue, view)`; `SceneGraphNode.GetGlobalBoundingBox() -> tuple[float, float, float, float, float, float]`; `SceneGraphNode.GetPath() -> str`; `SceneGraphLeaf.GetNodeSharedPtr() -> SceneGraphNode | None`.

- [ ] **Step 1: Write the failing tests**

Create `test/test_picking_bindings.py`. Start with the 22-line copyright block copied verbatim from `test/test_camera_bindings.py:1-22`, then:

```python
"""Surface tests for the FeatureDemo stage 3a picking bindings.

These need no GPU: they construct no device and render nothing. Constructing a MaterialIDPass
or a PixelReadbackPass needs a device, so those get presence-and-signature checks here and are
verified by running feature_demo.py in task 5.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def _graph_with_root() -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Returns a fresh graph and its real root node.

    SetRootNode returns the *previous* root (SceneGraph.cpp:670-679) -- None on a fresh
    graph -- so the root has to be read back with GetRootNode().
    """
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    return graph, graph.GetRootNode()


def test_material_id_pass_is_a_gbuffer_fill_pass() -> None:
    # MaterialIDPass derives from GBufferFillPass and overrides only Init and the protected
    # CreatePixelShader (GBufferFillPass.h:148-159), so it reuses that pass's create-parameters
    # and context types rather than getting its own. Constructing one needs a device.
    assert issubclass(pyd.MaterialIDPass, pyd.GBufferFillPass)
    assert issubclass(pyd.MaterialIDPass, pyd.IGeometryPass)


def test_material_id_pass_has_no_context_type_of_its_own() -> None:
    # Reusing GBufferFillPassContext is the point -- a "MaterialIDPassContext" would mean the
    # binding invented a type the C++ does not have.
    assert not hasattr(pyd, "MaterialIDPassContext")
    assert not hasattr(pyd, "MaterialIDPassCreateParameters")


def test_material_id_pass_exposes_init() -> None:
    doc = pyd.MaterialIDPass.Init.__doc__
    assert doc is not None
    assert "shaderFactory" in doc
    assert "params" in doc


def test_pixel_readback_pass_exposes_all_three_readers() -> None:
    # All three bind because the class is meaningless without whichever one matches the
    # caller's format, and each is a single line. feature_demo.py uses ReadUInts.
    for name in ("Capture", "ReadUInts", "ReadFloats", "ReadInts"):
        assert hasattr(pyd.PixelReadbackPass, name), name


def test_pixel_readback_capture_takes_flat_pixel_coordinates() -> None:
    # C++ takes a dm::uint2 (PixelReadbackPass.h:62); donut math types never cross into Python,
    # so it is flattened to two ints -- the same rule as PlanarView.SetPixelOffset.
    doc = pyd.PixelReadbackPass.Capture.__doc__
    assert doc is not None
    assert "x: int" in doc
    assert "y: int" in doc
    assert "uint2" not in doc


def test_pixel_readback_constructor_defaults_the_subresource() -> None:
    # arraySlice and mipLevel default to 0 in C++ (PixelReadbackPass.h:59-60); the binding keeps
    # them optional rather than forcing every caller to pass them.
    doc = pyd.PixelReadbackPass.__init__.__doc__
    assert doc is not None
    assert "arraySlice: int = 0" in doc
    assert "mipLevel: int = 0" in doc


def test_command_list_can_clear_a_uint_texture() -> None:
    # Needed to reset MaterialIDs to 0xffff before each pick. Mirrors clearTextureFloat: an
    # AllSubresources overload and a view-scoped one.
    doc = pyd.CommandList.clearTextureUInt.__doc__
    assert doc is not None
    assert "clearValue: int" in doc
    assert "view: donut::engine::IView" in doc


def test_global_bounding_box_returns_six_flat_floats() -> None:
    # dm::box3 does not cross into Python. A fresh node's box is box3::empty(), which is
    # mins = FLT_MAX and maxs = -FLT_MAX (box.h:139-143) -- so mins are GREATER than maxs here.
    # That sentinel is exactly what PointThirdPersonCameraAt has to guard against, since its
    # radius would otherwise be infinite.
    node = pyd.SceneGraphNode()
    bounds = node.GetGlobalBoundingBox()
    assert isinstance(bounds, tuple)
    assert len(bounds) == 6
    assert all(isinstance(v, float) for v in bounds)
    minX, minY, minZ, maxX, maxY, maxZ = bounds
    assert minX > maxX and minY > maxY and minZ > maxZ


def test_scene_graph_node_reports_its_path() -> None:
    # std::filesystem::path does not cross into Python either -- generic_string() C++-side.
    # Drives the "Picked node:" log line.
    #
    # SceneGraph binds no way to attach a bare node, only AttachLeafNode -- so the node under
    # test is the one that call returns, and the leaf is just the vehicle for creating it.
    graph, root = _graph_with_root()
    node = graph.AttachLeafNode(root, pyd.PointLight())
    node.SetName("nave")
    path = node.GetPath()
    assert isinstance(path, str)
    assert "nave" in path


def test_leaf_reports_its_owning_node() -> None:
    # A weak_ptr::lock(), so it legitimately returns None for a leaf that is not attached.
    # Bound on SceneGraphLeaf rather than MeshInstance so every leaf type gets it.
    #
    # `light` is freshly constructed and therefore attached rather than cloned -- AttachLeafNode
    # only clones a leaf that is already attached elsewhere (SceneGraph.cpp:844-847) -- so the
    # local object really is the one that ends up on the returned node.
    graph, root = _graph_with_root()
    light = pyd.PointLight()
    assert light.GetNodeSharedPtr() is None

    node = graph.AttachLeafNode(root, light)
    node.SetName("probe")

    owner = light.GetNodeSharedPtr()
    assert owner is not None
    # SceneGraphNode binds no GetName, so compare on the path instead.
    assert owner.GetPath() == node.GetPath()


def test_mesh_instance_inherits_the_owning_node_accessor() -> None:
    # MeshInstance.GetNode() already existed but returns a non-owning raw pointer. Picking
    # stores the node across frames, so it needs the shared_ptr form.
    assert hasattr(pyd.MeshInstance, "GetNodeSharedPtr")
    assert hasattr(pyd.MeshInstance, "GetNode")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_picking_bindings.py -q`

Expected: collection error or 11 failures — `pyd.MaterialIDPass` does not exist.

- [ ] **Step 3: Bind `MaterialIDPass` and `PixelReadbackPass`**

Add `#include <donut/render/PixelReadbackPass.h>` to the include block at the top of `src/cpp/_pydonut.cpp`, alongside the existing `#include <donut/render/GBufferFillPass.h>` (`MaterialIDPass` lives in that same header, so no second include is needed for it).

Add these immediately after the `GBufferFillPass` binding that ends at `src/cpp/_pydonut.cpp:2559`:

```cpp
    // MaterialIDPass (GBufferFillPass.h:148-159) derives from GBufferFillPass and overrides only
    // Init and the protected CreatePixelShader -- it writes material and instance IDs into a
    // RG16_UINT target instead of a full gbuffer, which is what right-click picking reads back.
    // Registered with GBufferFillPass as its pybind11 base, so it reuses
    // GBufferFillPassCreateParameters and GBufferFillPassContext; the C++ declares no context
    // type of its own.
    py::class_<donut::render::MaterialIDPass, donut::render::GBufferFillPass,
               std::shared_ptr<donut::render::MaterialIDPass>>(m, "MaterialIDPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::CommonRenderPasses>>(),
            py::arg("device"), py::arg("commonPasses"))
        .def("Init", &donut::render::MaterialIDPass::Init, py::arg("shaderFactory"), py::arg("params"));

    // Copies one pixel of a texture into a readback buffer so the CPU can inspect it
    // (PixelReadbackPass.h:41-66). Capture records the copy into a command list; the Read*
    // methods are only valid once that command list has executed on the GPU.
    //
    // `format` selects the readback buffer's layout and the compute shader variant that fills
    // it -- NOT the source texture's format. FeatureDemo.cpp:803 deliberately pairs an
    // RG16_UINT MaterialIDs texture with an RGBA32_UINT readback; that is correct, not a bug.
    py::class_<donut::render::PixelReadbackPass, std::shared_ptr<donut::render::PixelReadbackPass>>(m, "PixelReadbackPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::ShaderFactory>,
                nvrhi::ITexture*, nvrhi::Format, uint32_t, uint32_t>(),
            py::arg("device"), py::arg("shaderFactory"), py::arg("inputTexture"), py::arg("format"),
            py::arg("arraySlice") = 0, py::arg("mipLevel") = 0)
        // dm::uint2 flattened to two ints, matching PlanarView.SetPixelOffset.
        .def("Capture", [](donut::render::PixelReadbackPass &self, nvrhi::ICommandList* commandList,
                uint32_t x, uint32_t y) {
            self.Capture(commandList, donut::math::uint2(x, y));
        }, py::arg("commandList"), py::arg("x"), py::arg("y"))
        // All three readers bind: the class is meaningless without whichever matches the
        // caller's format, and each is one line. feature_demo.py uses ReadUInts.
        .def("ReadUInts", [](donut::render::PixelReadbackPass &self) {
            const donut::math::uint4 value = self.ReadUInts();
            return py::make_tuple(value.x, value.y, value.z, value.w);
        })
        .def("ReadFloats", [](donut::render::PixelReadbackPass &self) {
            const donut::math::float4 value = self.ReadFloats();
            return py::make_tuple(value.x, value.y, value.z, value.w);
        })
        .def("ReadInts", [](donut::render::PixelReadbackPass &self) {
            const donut::math::int4 value = self.ReadInts();
            return py::make_tuple(value.x, value.y, value.z, value.w);
        });
```

- [ ] **Step 4: Bind `clearTextureUInt`**

Insert directly after the `clearTextureFloat` view-scoped overload, which ends at `src/cpp/_pydonut.cpp:1705`:

```cpp
    // Integer-texture counterpart of clearTextureFloat above. Picking clears the RG16_UINT
    // MaterialIDs target to 0xffff before each pick pass, so "nothing was hit" is
    // distinguishable from material 0 (FeatureDemo.cpp:1041).
    commandList.def("clearTextureUInt", [](nvrhi::ICommandList &self, nvrhi::ITexture* texture,
            uint32_t clearValue) {
        self.clearTextureUInt(texture, nvrhi::AllSubresources, clearValue);
    }, py::arg("texture"), py::arg("clearValue"));
    commandList.def("clearTextureUInt", [](nvrhi::ICommandList &self, nvrhi::ITexture* texture,
            uint32_t clearValue, const donut::engine::IView &view) {
        self.clearTextureUInt(texture, view.GetSubresources(), clearValue);
    }, py::arg("texture"), py::arg("clearValue"), py::arg("view"), py::call_guard<py::gil_scoped_release>());
```

- [ ] **Step 5: Bind the three scene-graph accessors**

Append to the `SceneGraphLeaf` binding, which currently ends at `src/cpp/_pydonut.cpp:2252` with `.def("GetName", ...)` — change that line's terminating `;` to `)` and add:

```cpp
        // The node this leaf is attached to, as an owning handle. MeshInstance.GetNode() already
        // returned a raw non-owning pointer, which is fine for a same-frame transform read but
        // not for picking, which stores the hit node across frames. This is a weak_ptr::lock()
        // (SceneGraph.h:65), so it legitimately returns None for a leaf that is not attached.
        // Bound on the leaf base so every leaf type gets it, not just MeshInstance.
        .def("GetNodeSharedPtr", &donut::engine::SceneGraphLeaf::GetNodeSharedPtr);
```

Append to the `SceneGraphNode` binding, after `.def("GetWorldPosition", ...)` at `src/cpp/_pydonut.cpp:2436-2439` (change its terminating `;` to `)`):

```cpp
        // The node's world-space bounding box as (minX, minY, minZ, maxX, maxY, maxZ) --
        // dm::box3 does not cross into Python. Picking uses it to frame the third-person camera
        // on the hit node (FeatureDemo.cpp:659-667).
        //
        // A node with no content carries box3::empty(), which is mins = FLT_MAX and
        // maxs = -FLT_MAX (box.h:139-143), NOT a zero-sized box. Callers deriving a radius from
        // it must check for that sentinel or they get an infinite one.
        .def("GetGlobalBoundingBox", [](const donut::engine::SceneGraphNode &self) {
            const donut::math::box3 &bounds = self.GetGlobalBoundingBox();
            return py::make_tuple(bounds.m_mins.x, bounds.m_mins.y, bounds.m_mins.z,
                                  bounds.m_maxs.x, bounds.m_maxs.y, bounds.m_maxs.z);
        })
        // Slash-separated path from the scene-graph root, for the "Picked node:" log line
        // (FeatureDemo.cpp:1224). std::filesystem::path does not cross into Python, so this
        // returns generic_string() -- forward slashes on every platform.
        .def("GetPath", [](const donut::engine::SceneGraphNode &self) {
            return self.GetPath().generic_string();
        });
```

- [ ] **Step 6: Mirror in the type stubs**

In `src/pydonut/_pydonut.pyi`, add to `class SceneGraphLeaf` (after `GetName` at line 1086):

```python
    # The node this leaf is attached to, as an owning handle -- None if it is not attached.
    # MeshInstance.GetNode() returns a raw non-owning pointer; use this one to store a node
    # across frames, as picking does.
    def GetNodeSharedPtr(self: SceneGraphLeaf) -> Optional[SceneGraphNode]: ...
```

Add to `class SceneGraphNode` (after `GetWorldPosition`):

```python
    # World-space bounding box as (minX, minY, minZ, maxX, maxY, maxZ) -- dm::box3 is not
    # exposed. A node with no content carries box3::empty(): mins = FLT_MAX, maxs = -FLT_MAX,
    # so mins > maxs. Check for that before deriving a radius from it.
    def GetGlobalBoundingBox(self: SceneGraphNode) -> tuple[float, float, float, float, float, float]: ...
    # Slash-separated path from the scene-graph root, on every platform.
    def GetPath(self: SceneGraphNode) -> str: ...
```

Add to `class CommandList`, after the `clearTextureFloat` overloads at line 833:

```python
    # Integer-texture counterpart of clearTextureFloat. Picking clears its RG16_UINT target to
    # 0xffff so "nothing hit" is distinguishable from material 0.
    @overload
    def clearTextureUInt(self: CommandList, texture: Texture, clearValue: int) -> None: ...
    @overload
    def clearTextureUInt(self: CommandList, texture: Texture, clearValue: int, view: IView) -> None: ...
```

Add these two classes next to `class GBufferFillPass` (after line 1416):

```python
# Writes material and instance IDs instead of a full gbuffer -- the pass right-click picking
# renders through. Derives from GBufferFillPass and reuses its create-parameters and context
# types; the C++ declares none of its own.
class MaterialIDPass(GBufferFillPass):
    def __init__(self: MaterialIDPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: MaterialIDPass, shaderFactory: ShaderFactory, params: GBufferFillPassCreateParameters) -> None: ...

# Copies one pixel into a readback buffer. Capture records the copy; the Read* methods are only
# valid once that command list has executed. `format` is the readback buffer's layout, NOT the
# source texture's -- FeatureDemo pairs an RG16_UINT texture with an RGBA32_UINT readback.
class PixelReadbackPass():
    def __init__(self: PixelReadbackPass, device: Device, shaderFactory: ShaderFactory, inputTexture: Texture, format: Format, arraySlice: int = 0, mipLevel: int = 0) -> None: ...
    # dm::uint2 flattened to two ints, matching PlanarView.SetPixelOffset.
    def Capture(self: PixelReadbackPass, commandList: CommandList, x: int, y: int) -> None: ...
    def ReadUInts(self: PixelReadbackPass) -> tuple[int, int, int, int]: ...
    def ReadFloats(self: PixelReadbackPass) -> tuple[float, float, float, float]: ...
    def ReadInts(self: PixelReadbackPass) -> tuple[int, int, int, int]: ...
```

- [ ] **Step 7: Re-export the two new classes**

In `src/pydonut/__init__.py`, add next to the existing `GBufferFillPass` import at line 150:

```python
from pydonut._pydonut import MaterialIDPass
from pydonut._pydonut import PixelReadbackPass
```

and next to `'GBufferFillPass',` at line 341 in `__all__`:

```python
    'MaterialIDPass',
    'PixelReadbackPass',
```

- [ ] **Step 8: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`

Expected: 89 passed (78 + 11).

- [ ] **Step 9: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_picking_bindings.py
git commit -m "Bind MaterialIDPass, PixelReadbackPass and the picking accessors

MaterialIDPass reuses GBufferFillPass's create-parameters and context
types, matching the C++, which declares none of its own.
GetGlobalBoundingBox returns a flat 6-tuple per the no-math-types rule;
its empty-box sentinel is mins > maxs, which callers deriving a radius
have to guard against."
```

---

## Task 3: Capture bindings — MipMapGen, screenshots and the file dialog

**Files:**
- Modify: `src/cpp/_pydonut.cpp`
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_capture_bindings.py` (create)

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces, for Task 6: `pyd.MipMapGenPassMode` with `MODE_COLOR`, `MODE_MIN`, `MODE_MAX`, `MODE_MINMAX`; `pyd.MipMapGenPass(device, shaderFactory, texture, mode=MipMapGenPassMode.MODE_MAX)` with `.Dispatch(commandList, maxLOD=-1)` and `.Display(commonPasses, commandList, target)`; `pyd.SaveTextureToFile(device, commonPasses, texture, textureState, fileName, saveAlphaChannel=True) -> bool`; `pyd.FileDialog(bOpen: bool, filters: list[tuple[str, str]]) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Create `test/test_capture_bindings.py`. Copyright block first (verbatim from `test/test_camera_bindings.py:1-22`), then:

```python
"""Surface tests for the FeatureDemo stage 3a capture bindings.

These need no GPU: they construct no device and render nothing. Constructing a MipMapGenPass or
calling SaveTextureToFile needs a device, so those get presence-and-signature checks here and
are verified by running feature_demo.py in task 6.

FileDialog is never invoked here. It is a blocking modal -- GetSaveFileNameA on Windows,
`zenity` on Linux -- and calling it would hang a headless run until someone dismissed a window.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def test_mipmapgen_mode_binds_all_four_values() -> None:
    # MipMapGenPass::Mode has exactly these four (MipMapGenPass.h:47-52). pybind11's
    # native_enum casts C++ -> Python by constructing Mode(int), which raises ValueError for an
    # unbound value -- so a partial binding is a latent crash, not a missing convenience.
    # This is the stage 2c MaterialDomain lesson applied to a new enum.
    names = {mode.name for mode in pyd.MipMapGenPassMode}
    assert names == {"MODE_COLOR", "MODE_MIN", "MODE_MAX", "MODE_MINMAX"}
    assert pyd.MipMapGenPassMode.MODE_COLOR.value == 0
    assert pyd.MipMapGenPassMode.MODE_MIN.value == 1
    assert pyd.MipMapGenPassMode.MODE_MAX.value == 2
    assert pyd.MipMapGenPassMode.MODE_MINMAX.value == 3


def test_mipmapgen_pass_exposes_dispatch_and_display() -> None:
    # Dispatch reduces LOD 0 into LOD 1 and up; Display blits the levels in a spiral for
    # debugging. Constructing one needs a device and a texture allocated with mip levels.
    for name in ("Dispatch", "Display"):
        assert hasattr(pyd.MipMapGenPass, name), name


def test_mipmapgen_dispatch_defaults_to_every_level() -> None:
    # maxLOD = -1 means "all levels" (MipMapGenPass.h:63).
    doc = pyd.MipMapGenPass.Dispatch.__doc__
    assert doc is not None
    assert "maxLOD: int = -1" in doc


def test_mipmapgen_constructor_defaults_to_max_mode() -> None:
    # Matches the C++ default (MipMapGenPass.h:59). feature_demo.py passes MODE_COLOR
    # explicitly, since it reduces an RGB colour target rather than a single-channel one.
    doc = pyd.MipMapGenPass.__init__.__doc__
    assert doc is not None
    assert "MODE_MAX" in doc


def test_save_texture_to_file_is_exposed_with_an_alpha_default() -> None:
    # A free function in donut::engine (TextureCache.h:243-249), not a method. Calling it needs
    # a device, and the header requires no immediate command list be open at the time -- which
    # is why feature_demo.py calls it after executeCommandList.
    assert callable(pyd.SaveTextureToFile)
    doc = pyd.SaveTextureToFile.__doc__
    assert doc is not None
    assert "saveAlphaChannel: bool = True" in doc


def test_file_dialog_takes_filter_pairs_not_a_packed_buffer() -> None:
    # The C++ takes a double-NUL-terminated buffer and returns through a std::string& out-param
    # (UserInterfaceUtils.h:39). Both are hostile from Python -- embedded NULs do not survive a
    # str conversion -- so the binding takes (description, pattern) pairs and returns
    # Optional[str]. This is a deliberate signature change, not a literal port.
    assert callable(pyd.FileDialog)
    doc = pyd.FileDialog.__doc__
    assert doc is not None
    assert "bOpen: bool" in doc
    assert "filters" in doc


def test_file_dialog_rejects_a_malformed_filter_list() -> None:
    # Rejected by pybind11's argument caster, before the lambda body runs -- so no dialog opens
    # and this stays safe to run headless. A bare string is the mistake this guards against:
    # it is iterable, so a looser signature would silently accept it.
    with pytest.raises(TypeError):
        pyd.FileDialog(False, "BMP files")
    with pytest.raises(TypeError):
        pyd.FileDialog(False, [("BMP files",)])


def test_folder_dialog_stays_unbound() -> None:
    # Nothing in this repo needs it; deliberately skipped rather than overlooked.
    assert not hasattr(pyd, "FolderDialog")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_capture_bindings.py -q`

Expected: collection error or 8 failures — `pyd.MipMapGenPassMode` does not exist.

- [ ] **Step 3: Bind `MipMapGenPass` and its mode enum**

Add `#include <donut/render/MipMapGenPass.h>` and `#include <donut/app/UserInterfaceUtils.h>` to the include block (`donut/engine/TextureCache.h` is where `SaveTextureToFile` lives — check whether it is already included and add it if not).

Add after the `SsaoPass` binding, which ends at `src/cpp/_pydonut.cpp:2799`:

```cpp
    // MipMapGenPass::Mode (MipMapGenPass.h:47-52), flattened to module scope the same way
    // GBufferFillPass::CreateParameters binds as GBufferFillPassCreateParameters. All four
    // values bind: native_enum casts C++ -> Python by constructing the enum from an int and
    // raises ValueError for an unbound one, so a partial binding is a latent crash.
    pybind11::native_enum<donut::render::MipMapGenPass::Mode>(m, "MipMapGenPassMode", "enum.Enum")
        .value("MODE_COLOR", donut::render::MipMapGenPass::Mode::MODE_COLOR)
        .value("MODE_MIN", donut::render::MipMapGenPass::Mode::MODE_MIN)
        .value("MODE_MAX", donut::render::MipMapGenPass::Mode::MODE_MAX)
        .value("MODE_MINMAX", donut::render::MipMapGenPass::Mode::MODE_MINMAX)
        .finalize();

    // Compute-shader mip-chain reduction. `texture` MUST already have been allocated with mip
    // levels -- the pass binds one UAV per level at construction, so a single-level texture
    // gives it nothing to write. feature_demo.py gives ResolvedColor a full chain purely to
    // exercise this (FeatureDemo.cpp:135).
    py::class_<donut::render::MipMapGenPass, std::shared_ptr<donut::render::MipMapGenPass>>(m, "MipMapGenPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::ShaderFactory>,
                nvrhi::TextureHandle, donut::render::MipMapGenPass::Mode>(),
            py::arg("device"), py::arg("shaderFactory"), py::arg("texture"),
            py::arg("mode") = donut::render::MipMapGenPass::Mode::MODE_MAX)
        // Reads LOD 0 and populates LOD 1 and up. maxLOD = -1 means every level.
        .def("Dispatch", &donut::render::MipMapGenPass::Dispatch,
            py::arg("commandList"), py::arg("maxLOD") = -1)
        // Debug only: blits the levels in a spiral over `target`, which must be large enough.
        .def("Display", &donut::render::MipMapGenPass::Display,
            py::arg("commonPasses"), py::arg("commandList"), py::arg("target"));
```

- [ ] **Step 4: Bind `SaveTextureToFile` and `FileDialog`**

Add near the other module-level free functions, after the `RenderCompositeView` binding that ends around `src/cpp/_pydonut.cpp:3020`:

```cpp
    // Writes slice 0, mip 0 of a texture to an image file; the format comes from the extension
    // (BMP, PNG, JPG, TGA). Takes a raw CommonRenderPasses* in C++ (TextureCache.h:243-249),
    // so unwrap the shared_ptr the module holds it as.
    //
    // The header requires that no immediate command list be open when this is called, and it
    // creates and destroys temporary resources internally -- so call it after
    // executeCommandList and not once per frame.
    m.def("SaveTextureToFile", [](nvrhi::IDevice* device,
            const std::shared_ptr<donut::engine::CommonRenderPasses> &commonPasses,
            nvrhi::ITexture* texture, nvrhi::ResourceStates textureState,
            const std::string &fileName, bool saveAlphaChannel) {
        return donut::engine::SaveTextureToFile(device, commonPasses.get(), texture, textureState,
            fileName.c_str(), saveAlphaChannel);
    }, py::arg("device"), py::arg("commonPasses"), py::arg("texture"), py::arg("textureState"),
       py::arg("fileName"), py::arg("saveAlphaChannel") = true);

    // Native modal save/open dialog. The C++ signature is hostile from Python on both ends
    // (UserInterfaceUtils.h:39): it wants a double-NUL-terminated filter buffer, which cannot
    // survive a str conversion, and returns its result through a std::string& out-param. So
    // this takes (description, pattern) pairs, packs the buffer here, and returns Optional[str]
    // -- None when the user cancels.
    //
    // On Windows this is GetSaveFileNameA/GetOpenFileNameA; on Linux it shells out to `zenity`
    // (UserInterfaceUtils.cpp:74-88), which may not be installed. A None return therefore does
    // not distinguish "cancelled" from "no dialog available" -- callers that need a file
    // regardless must supply their own fallback path, as feature_demo.py does.
    //
    // Blocking and modal: never call it from a test.
    m.def("FileDialog", [](bool bOpen, const std::vector<std::pair<std::string, std::string>> &filters)
            -> std::optional<std::string> {
        std::string packed;
        for (const auto &filter : filters)
        {
            packed.append(filter.first);
            packed.push_back('\0');
            packed.append(filter.second);
            packed.push_back('\0');
        }
        // The buffer is terminated by a second NUL after the last pattern. An empty filter list
        // still needs one, so the terminator is appended unconditionally.
        packed.push_back('\0');

        std::string fileName;
        if (!donut::app::FileDialog(bOpen, packed.c_str(), fileName))
            return std::nullopt;
        return fileName;
    }, py::arg("bOpen"), py::arg("filters"));
```

If `<optional>` and `<utility>` are not already included at the top of the file, add them.

- [ ] **Step 5: Mirror in the type stubs**

Add to `src/pydonut/_pydonut.pyi`, next to the other render passes:

```python
# MipMapGenPass::Mode, flattened to module scope. All four values bind -- a partial enum
# binding raises ValueError when C++ hands back an unbound one.
class MipMapGenPassMode(Enum):
    MODE_COLOR = 0
    MODE_MIN = 1
    MODE_MAX = 2
    MODE_MINMAX = 3

# Compute-shader mip-chain reduction. `texture` must already have been allocated with mip
# levels -- the pass binds one UAV per level at construction.
class MipMapGenPass():
    def __init__(self: MipMapGenPass, device: Device, shaderFactory: ShaderFactory, texture: Texture, mode: MipMapGenPassMode = ...) -> None: ...
    # Reads LOD 0 and populates LOD 1 and up. maxLOD = -1 means every level.
    def Dispatch(self: MipMapGenPass, commandList: CommandList, maxLOD: int = -1) -> None: ...
    # Debug only: blits the levels in a spiral over `target`, which must be large enough.
    def Display(self: MipMapGenPass, commonPasses: CommonRenderPasses, commandList: CommandList, target: Framebuffer) -> None: ...
```

and, next to the other module-level functions:

```python
# Writes slice 0, mip 0 of a texture to an image file; the format comes from the extension
# (BMP, PNG, JPG, TGA). Requires that no immediate command list be open, and creates and
# destroys temporary resources internally -- call it after executeCommandList, not per frame.
def SaveTextureToFile(device: Device, commonPasses: CommonRenderPasses, texture: Texture, textureState: ResourceStates, fileName: str, saveAlphaChannel: bool = True) -> bool: ...

# Native modal save/open dialog. Takes (description, pattern) pairs -- the C++ wants a
# double-NUL-terminated buffer, which cannot survive a str conversion -- and returns None when
# the user cancels. On Linux this shells out to `zenity`, so None also means "no dialog
# available"; callers needing a file regardless must supply their own fallback path.
# Blocking and modal: never call it from a test.
def FileDialog(bOpen: bool, filters: list[tuple[str, str]]) -> Optional[str]: ...
```

`Enum` is already imported at `src/pydonut/_pydonut.pyi:24`; `class TemporalAntiAliasingJitter(Enum)` at `:1483-1487` is the style to match.

- [ ] **Step 6: Re-export the four new names**

In `src/pydonut/__init__.py`, add the imports next to the other pass imports and the four `__all__` entries alongside them:

```python
from pydonut._pydonut import MipMapGenPassMode
from pydonut._pydonut import MipMapGenPass
from pydonut._pydonut import SaveTextureToFile
from pydonut._pydonut import FileDialog
```

```python
    'MipMapGenPassMode',
    'MipMapGenPass',
    'SaveTextureToFile',
    'FileDialog',
```

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`

Expected: 97 passed (89 + 8).

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_capture_bindings.py
git commit -m "Bind MipMapGenPass, SaveTextureToFile and FileDialog

FileDialog deliberately changes shape: it takes (description, pattern)
pairs and returns Optional[str], because the C++ wants a
double-NUL-terminated buffer and a std::string& out-param, neither of
which survives a Python str. All four MipMapGenPass modes bind, since
native_enum raises ValueError on an unbound value."
```

---

## Task 4: `StereoPlanarView`

**Files:**
- Modify: `src/cpp/_pydonut.cpp`
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_stereo_bindings.py` (create)

**Interfaces:**
- Consumes: Task 1's ten widened signatures — without them a `StereoPlanarView` cannot reach any pass.
- Produces, for Task 7: `pyd.StereoPlanarView()`, `pyd.StereoPlanarView(other)`, `.LeftView -> PlanarView`, `.RightView -> PlanarView` (both live references), `.SetMatricesFromSwitchableCamera(camera, aspectRatio, eyeSeparation=0.2, verticalFovRadians=PI/4, zNear=0.1)`.

- [ ] **Step 1: Write the failing tests**

Create `test/test_stereo_bindings.py`. Copyright block first, then:

```python
"""Surface tests for the FeatureDemo stage 3a stereo bindings.

These need no GPU: PlanarView and SwitchableCamera are both constructible standalone, and the
matrix work is pure math. PlanarView exposes no matrix getters, so the observable used
throughout is FillPlanarViewConstants(), which returns the raw constant-buffer bytes -- two
views whose matrices differ produce different bytes.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def _stereo_view_with_matrices() -> pyd.StereoPlanarView:
    """A stereo view with both eyes' matrices set from a default first-person camera."""
    view = pyd.StereoPlanarView()
    camera = pyd.SwitchableCamera()
    # copyView=False: SwitchableCamera starts on the third-person camera, and copying its view
    # into the first-person one would overwrite the default this test relies on.
    camera.SwitchToFirstPerson(copyView=False)
    # Per-eye aspect ratio: each eye owns half the framebuffer width.
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0 * 0.5)
    view.LeftView.UpdateCache()
    view.RightView.UpdateCache()
    return view


def test_stereo_planar_view_is_an_iview() -> None:
    # It has to reach every pass widened in task 1, all of which take IView or ICompositeView.
    assert issubclass(pyd.StereoPlanarView, pyd.IView)
    assert issubclass(pyd.StereoPlanarView, pyd.ICompositeView)


def test_stereo_planar_view_is_constructible_and_copyable() -> None:
    # The copy constructor is how the render tail snapshots this frame's view as next frame's
    # previous view, mirroring PlanarView's (FeatureDemo.cpp:753).
    view = pyd.StereoPlanarView()
    copied = pyd.StereoPlanarView(view)
    assert isinstance(copied, pyd.StereoPlanarView)


def test_eye_views_are_planar_views() -> None:
    view = pyd.StereoPlanarView()
    assert isinstance(view.LeftView, pyd.PlanarView)
    assert isinstance(view.RightView, pyd.PlanarView)


def test_eye_views_are_live_references_not_copies() -> None:
    # This is the whole point of reference_internal. If LeftView handed back a copy, the
    # SetViewport below would land on a temporary and the second, separate property access
    # would still see the original state -- so the constants would come back unchanged.
    view = pyd.StereoPlanarView()
    view.LeftView.UpdateCache()
    before = view.LeftView.FillPlanarViewConstants()

    view.LeftView.SetViewport(pyd.Viewport(640.0, 480.0))
    view.LeftView.UpdateCache()
    after = view.LeftView.FillPlanarViewConstants()

    assert after != before


def test_writing_one_eye_does_not_disturb_the_other() -> None:
    # Confirms LeftView and RightView are distinct members, not two views of one.
    view = pyd.StereoPlanarView()
    view.RightView.UpdateCache()
    rightBefore = view.RightView.FillPlanarViewConstants()

    view.LeftView.SetViewport(pyd.Viewport(640.0, 480.0))
    view.LeftView.UpdateCache()

    assert view.RightView.FillPlanarViewConstants() == rightBefore


def test_the_two_eyes_get_different_matrices() -> None:
    # The observable proxy for the eye offset: matrices do not cross into Python, but the right
    # eye's view matrix is the left's translated along X, so their constants must differ.
    # Neither viewport is touched here, so the matrices are the only thing that can differ.
    view = _stereo_view_with_matrices()
    assert view.LeftView.FillPlanarViewConstants() != view.RightView.FillPlanarViewConstants()


def test_eye_separation_is_adjustable_and_defaults_to_the_sample_value() -> None:
    # FeatureDemo.cpp:741 hardcodes 0.2 world units; it is a named argument here so the example
    # does not have to repeat the magic number, and so the effect is testable.
    doc = pyd.StereoPlanarView.SetMatricesFromSwitchableCamera.__doc__
    assert doc is not None
    assert "eyeSeparation: float = 0.2" in doc

    camera = pyd.SwitchableCamera()
    camera.SwitchToFirstPerson(copyView=False)

    wide = pyd.StereoPlanarView()
    wide.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0 * 0.5, eyeSeparation=2.0)
    wide.RightView.UpdateCache()

    narrow = pyd.StereoPlanarView()
    narrow.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0 * 0.5, eyeSeparation=0.2)
    narrow.RightView.UpdateCache()

    assert wide.RightView.FillPlanarViewConstants() != narrow.RightView.FillPlanarViewConstants()


def test_stereo_view_has_no_update_cache_of_its_own() -> None:
    # StereoView declares none -- the caches live on the two child PlanarViews, and each has to
    # be updated individually (FeatureDemo.cpp:748-749). A bound UpdateCache here would be an
    # invention that silently did nothing.
    assert not hasattr(pyd.StereoPlanarView, "UpdateCache")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_stereo_bindings.py -q`

Expected: collection error or 8 failures — `pyd.StereoPlanarView` does not exist.

- [ ] **Step 3: Bind `StereoPlanarView`**

Add immediately after the `PlanarView` binding block ends and before `CubemapView`'s, in `src/cpp/_pydonut.cpp`:

```cpp
    // StereoView<PlanarView> (View.h:337): two PlanarView members with the composite-view
    // interface fanning out over both. feature_demo.py renders both eyes side by side into one
    // framebuffer, so this needs no stereo hardware.
    //
    // Registered as an IView (not just ICompositeView) because StereoView derives from IView
    // directly, and several of the passes widened alongside this take IView.
    //
    // NOTE most of the IView accessors are dangerous on this type: GetViewMatrix,
    // GetInverseViewMatrix, GetProjectionMatrix, GetViewProjectionMatrix and their inverses are
    // all assert(false) + identity (View.h:256-292), and asserts compile out in this project's
    // Release build. None of them is bound here. GetViewFrustum and GetProjectionFrustum ARE
    // meaningfully overridden (View.h:235-255) and reach C++ through the widened pass
    // signatures, which is why CascadedShadowMap.SetupForPlanarViewStable takes its inverse
    // view matrix from a planar child view rather than from the composite.
    py::class_<donut::engine::StereoPlanarView, donut::engine::IView> stereoPlanarView(m, "StereoPlanarView");
    stereoPlanarView.def(py::init<>());
    // Copy constructor, mirroring PlanarView's: how Python snapshots this frame's view as next
    // frame's previous view (FeatureDemo.cpp:753).
    stereoPlanarView.def(py::init<const donut::engine::StereoPlanarView&>(), py::arg("other"));
    // Live references into the stereo view, NOT copies. A copy would silently discard every
    // viewport and pixel-offset write the caller makes -- the same trap
    // SwitchableCamera.GetFirstPersonCamera documents. reference_internal also keeps the owning
    // StereoPlanarView alive for as long as Python holds an eye.
    stereoPlanarView.def_property_readonly("LeftView",
        [](donut::engine::StereoPlanarView &self) -> donut::engine::PlanarView* { return &self.LeftView; },
        py::return_value_policy::reference_internal);
    stereoPlanarView.def_property_readonly("RightView",
        [](donut::engine::StereoPlanarView &self) -> donut::engine::PlanarView* { return &self.RightView; },
        py::return_value_policy::reference_internal);
    // The stereo counterpart of PlanarView.SetMatricesFromSwitchableCamera, with the eye offset
    // applied C++-side so dm::affine3 never crosses into Python. Reproduces
    // FeatureDemo.cpp:735-744: one shared projection, and the right eye's view matrix is the
    // left's translated along X.
    //
    // `aspectRatio` is the PER-EYE aspect ratio -- the caller passes width / height * 0.5,
    // since each eye owns half the framebuffer width (FeatureDemo.cpp:736). This does not halve
    // it internally, so the argument means the same thing it does on the planar shim.
    //
    // Neither eye's UpdateCache is called here: StereoView has no cache of its own, and the two
    // children have to be updated individually, as the sample does (FeatureDemo.cpp:748-749).
    stereoPlanarView.def("SetMatricesFromSwitchableCamera", [](donut::engine::StereoPlanarView &self,
            const donut::app::SwitchableCamera &camera, float aspectRatio, float eyeSeparation,
            float verticalFovRadians, float zNear) {
        // Both are by-value parameters, so this overwrites the local copies, not the caller's.
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

If `donut::engine::StereoPlanarView` does not resolve, it is the `typedef StereoView<PlanarView> StereoPlanarView;` at `View.h:337` — `#include <donut/engine/View.h>` is already present.

- [ ] **Step 4: Mirror in the type stubs**

Add to `src/pydonut/_pydonut.pyi` immediately after `class PlanarView`:

```python
# Two PlanarViews side by side, with the composite-view interface fanning out over both. Used
# for the split-viewport stereo mode; no stereo hardware involved.
#
# Most IView matrix accessors are assert(false) + identity on this type and are deliberately
# not bound -- asserts compile out in this project's Release build, so they would fail silently.
# GetViewFrustum and GetProjectionFrustum ARE meaningfully overridden and reach C++ through the
# pass signatures.
class StereoPlanarView(IView):
    @overload
    def __init__(self: StereoPlanarView) -> None: ...
    # Copy constructor, mirroring PlanarView's: how Python snapshots this frame's view as next
    # frame's previous view.
    @overload
    def __init__(self: StereoPlanarView, other: StereoPlanarView) -> None: ...
    # Live references into the stereo view, not copies -- writes through them persist.
    @property
    def LeftView(self: StereoPlanarView) -> PlanarView: ...
    @property
    def RightView(self: StereoPlanarView) -> PlanarView: ...
    # One shared projection; the right eye's view matrix is the left's translated along X.
    # `aspectRatio` is the PER-EYE ratio -- pass width / height * 0.5, since each eye owns half
    # the framebuffer width. Call UpdateCache() on each eye afterwards: StereoPlanarView has
    # none of its own.
    def SetMatricesFromSwitchableCamera(self: StereoPlanarView, camera: SwitchableCamera, aspectRatio: float, eyeSeparation: float = 0.2, verticalFovRadians: float = ..., zNear: float = 0.1) -> None: ...
```

- [ ] **Step 5: Re-export it**

In `src/pydonut/__init__.py`, next to the `CubemapView` import at line 143:

```python
from pydonut._pydonut import StereoPlanarView
```

and next to `'CubemapView',` at line 334:

```python
    'StereoPlanarView',
```

- [ ] **Step 6: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`

Expected: 105 passed (97 + 8).

- [ ] **Step 7: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_stereo_bindings.py
git commit -m "Bind StereoPlanarView with live eye views and a stereo camera shim

LeftView/RightView are reference_internal: a copy would silently discard
every viewport write. The matrix accessors StereoView stubs out with
assert(false) are deliberately left unbound, since asserts compile out in
this project's Release build."
```

---

## Task 5: `feature_demo.py` — MaterialID picking

Retires the stage 2c material dropdown and replaces it with right-click viewport picking.

**Files:**
- Modify: `feature_demo.py` — module docstring (`:23-38`), `UIData.__init__` (`:116-147`), `RenderTargets` (`:157-257`), `FeatureDemo.__init__` (`:260-304`), `Init` (`:361-362`), `CreateRenderPasses` (`:380`), `ReloadShaders` (`:485-486`), `MousePosUpdate`/`MouseButtonUpdate` (`:779-786`), `Render` (`:1039` area and the tail at `:1214`), `UIRenderer.__init__` (`:1232`), `_buildMaterialEditorWindow` (`:1521-1576`)

**Interfaces:**
- Consumes: Task 2's `pyd.MaterialIDPass`, `pyd.PixelReadbackPass`, `CommandList.clearTextureUInt`, `SceneGraphNode.GetGlobalBoundingBox`, `SceneGraphNode.GetPath`, `SceneGraphLeaf.GetNodeSharedPtr`.
- Produces: `FeatureDemo.PointThirdPersonCameraAt(node)`, `FeatureDemo.pick: bool`, `FeatureDemo.pickPosition: tuple[int, int]`, `UIData.SelectedNode`, `UIData.SelectedMaterial`.

- [ ] **Step 1: Add the picking render target**

In `RenderTargets.__init__`, next to the other texture fields:

```python
            self.MaterialIDs: pyd.Texture | None = None
            self.MaterialIDFramebuffer: pyd.FramebufferFactory | None = None
```

In `RenderTargets.Init`, immediately after the `self.HdrColor = makeColor(...)` line:

```python
            # MSAA-matched alongside HdrColor, and non-UAV: the pick pass only ever renders into
            # it (FeatureDemo.cpp:124-127). RG16_UINT holds a material ID in .x and an instance
            # index in .y.
            self.MaterialIDs = makeColor(pyd.Format.RG16_UINT, "MaterialIDs", False)
```

and, next to the other framebuffer construction at the end of `Init`:

```python
            self.MaterialIDFramebuffer = pyd.FramebufferFactory(device)
            self.MaterialIDFramebuffer.SetRenderTargets([self.MaterialIDs])
            # Shares the gbuffer's depth so the pick pass depth-tests against the same geometry
            # the visible frame did (FeatureDemo.cpp:208-210).
            self.MaterialIDFramebuffer.depthTarget = depth
```

- [ ] **Step 2: Add the UI and app state**

In `UIData.__init__`, after `self.ShaderReloadRequested = False`:

```python
            # Written by the MaterialID readback each time a pick resolves. SelectedMaterial
            # drives the Material Editor window; SelectedNode drives the picked-node readout and
            # the third-person camera reframe.
            self.SelectedMaterial: pyd.Material | None = None
            self.SelectedNode: pyd.SceneGraphNode | None = None
```

In `FeatureDemo.__init__`, next to the other pass fields:

```python
            self.materialIDPass: pyd.MaterialIDPass | None = None
            self.pixelReadbackPass: pyd.PixelReadbackPass | None = None
            # Armed by a right mouse press, consumed by the next Render. pickPosition is updated
            # on every mouse move, so it is already correct when the press arrives.
            self.pick = False
            self.pickPosition = (0, 0)
```

Add this module-level constant next to `NAVE_CAMERA_FOV` at `feature_demo.py:105`:

```python
    # The vertical FOV the view shim actually uses -- PlanarView.SetMatricesFromSwitchableCamera
    # defaults verticalFovRadians to PI/4, and SetupView does not override it. The C++ sample
    # uses 60 degrees (FeatureDemo.cpp:323); matching the shim instead keeps the pick framing
    # consistent with what is actually on screen.
    CAMERA_VERTICAL_FOV = math.pi / 4.0
```

- [ ] **Step 3: Create the two passes**

`materialIDPass` holds only pipelines, so it goes where `gbufferPass` already lives. In `Init`, immediately after the `self.gbufferPass.Init(...)` line at `feature_demo.py:362`:

```python
            # Size-independent, like gbufferPass: it holds pipelines, not render targets, so it
            # belongs here and in ReloadShaders rather than in CreateRenderPasses. (The C++
            # sample builds it in CreateRenderPasses, FeatureDemo.cpp:800-801, but this port
            # already keeps its geometry passes out of that method.)
            self.materialIDPass = pyd.MaterialIDPass(device, self.m_CommonPasses)
            self.materialIDPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())
```

Add the identical two lines to `ReloadShaders`, immediately after its own `self.gbufferPass.Init(...)` at `feature_demo.py:486`.

`pixelReadbackPass` binds the MaterialIDs texture, which is recreated on resize, so it belongs in `CreateRenderPasses`. Add near the top of that method, after the `assert self.renderTargets is not None`:

```python
            # RGBA32_UINT is the readback *buffer's* layout and the compute shader variant that
            # fills it -- not the source texture's format, which is RG16_UINT. The mismatch is
            # deliberate and matches FeatureDemo.cpp:803.
            self.pixelReadbackPass = pyd.PixelReadbackPass(
                device,
                self.shaderFactory,
                self.renderTargets.MaterialIDs,
                pyd.Format.RGBA32_UINT,
            )
```

- [ ] **Step 4: Arm the pick from mouse input**

Replace `MousePosUpdate` and `MouseButtonUpdate` (`feature_demo.py:779-786`):

```python
        def MousePosUpdate(self: FeatureDemo, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            # Recorded unconditionally, so the position is already right when a press arrives
            # (FeatureDemo.cpp:511). The sample guards its camera call with
            # `if (!m_ui.ActiveSceneCamera)`; SwitchableCamera already routes input away from
            # the user cameras when a scene camera is active, so there is no guard here.
            self.pickPosition = (int(xpos), int(ypos))
            return True

        def MouseButtonUpdate(self: FeatureDemo, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            # No GLFW keycode enum is bound -- raw codes with a comment, the convention the other
            # examples use. Matches FeatureDemo.cpp:521-522.
            if button == 1 and action == 1:  # GLFW_MOUSE_BUTTON_2, GLFW_PRESS
                self.pick = True
            return True
```

- [ ] **Step 5: Add the camera-framing helper**

Add as a new method on `FeatureDemo`, immediately after `CreateSceneCameras` (which ends at `feature_demo.py:756`):

```python
        def PointThirdPersonCameraAt(
            self: FeatureDemo, node: pyd.SceneGraphNode | None
        ) -> None:
            """Orbits the third-person camera around `node`, framed to its bounding box.

            Mirrors FeatureDemo.cpp:659-667. Does nothing for a node with no geometry: an empty
            box3 is mins = FLT_MAX / maxs = -FLT_MAX, which would give an infinite radius and
            throw the camera to infinity. The C++ never hits that case because it only ever
            calls this with loaded geometry, so the guard is an addition, not a port.
            """
            if node is None:
                return

            minX, minY, minZ, maxX, maxY, maxZ = node.GetGlobalBoundingBox()
            if minX > maxX or minY > maxY or minZ > maxZ:
                return

            dx, dy, dz = maxX - minX, maxY - minY, maxZ - minZ
            radius = math.sqrt(dx * dx + dy * dy + dz * dz) * 0.5
            if radius <= 0.0:
                return

            thirdPerson = self.camera.GetThirdPersonCamera()
            thirdPerson.SetTargetPosition(
                (minX + maxX) * 0.5, (minY + maxY) * 0.5, (minZ + maxZ) * 0.5
            )
            thirdPerson.SetDistance(radius / math.sin(CAMERA_VERTICAL_FOV * 0.5))
            # Load-bearing: SetTargetPosition and SetDistance only stage the values. Without
            # this the camera stays exactly where it was, with no error.
            thirdPerson.Animate(0.0)
```

- [ ] **Step 6: Render the pick pass**

In `Render`, immediately before the `if self.ui.EnableProceduralSky and self.sunLight is not None:` block at `feature_demo.py:1124`, insert:

```python
            # Matches FeatureDemo.cpp:1039-1067: after the shading passes so it sees the same
            # depth buffer, before the sky so the sky cannot overwrite an ID.
            if self.pick and self.pixelReadbackPass is not None:
                # 0xffff is the "nothing here" sentinel -- material IDs and instance indices are
                # both non-negative, so no real value collides with it.
                self.commandList.clearTextureUInt(self.renderTargets.MaterialIDs, 0xFFFF)

                materialIDContext = pyd.GBufferFillPassContext()
                pyd.RenderCompositeView(
                    self.commandList,
                    self.view,
                    self.viewPrevious,
                    self.renderTargets.MaterialIDFramebuffer,
                    self.scene.GetSceneGraph().GetRootNode(),
                    self.opaqueDrawStrategy,
                    self.materialIDPass,
                    materialIDContext,
                    self.ui.EnableMaterialEvents,
                )

                if self.ui.EnableTranslucency:
                    pyd.RenderCompositeView(
                        self.commandList,
                        self.view,
                        self.viewPrevious,
                        self.renderTargets.MaterialIDFramebuffer,
                        self.scene.GetSceneGraph().GetRootNode(),
                        self.transparentDrawStrategy,
                        self.materialIDPass,
                        materialIDContext,
                        self.ui.EnableMaterialEvents,
                    )

                self.pixelReadbackPass.Capture(
                    self.commandList, self.pickPosition[0], self.pickPosition[1]
                )
```

The draw strategies are `self.opaqueDrawStrategy` and `self.transparentDrawStrategy`, both built in `FeatureDemo.__init__` (`feature_demo.py:299`).

- [ ] **Step 7: Resolve the pick after the GPU has run**

In `Render`, immediately after `device.executeCommandList(self.commandList)` at `feature_demo.py:1214`:

```python
            # After executeCommandList: the readback buffer is not populated until the GPU has
            # run the Capture recorded above (FeatureDemo.cpp:1197-1228).
            if self.pick:
                self.pick = False
                materialID, instanceIndex, _, _ = self.pixelReadbackPass.ReadUInts()

                self.ui.SelectedMaterial = None
                self.ui.SelectedNode = None

                sceneGraph = self.scene.GetSceneGraph()
                for material in sceneGraph.GetMaterials():
                    if material.materialID == materialID:
                        self.ui.SelectedMaterial = material
                        break

                for instance in sceneGraph.GetMeshInstances():
                    if instance.GetInstanceIndex() == instanceIndex:
                        # The owning handle, not GetNode()'s raw pointer: this is stored across
                        # frames and outlives the loop.
                        self.ui.SelectedNode = instance.GetNodeSharedPtr()
                        break

                if self.ui.SelectedNode is not None:
                    pyd.log.info(f"Picked node: {self.ui.SelectedNode.GetPath()}")
                    self.PointThirdPersonCameraAt(self.ui.SelectedNode)
                else:
                    self.PointThirdPersonCameraAt(sceneGraph.GetRootNode())
```

- [ ] **Step 8: Drive the material editor from the pick instead of the dropdown**

In `UIRenderer.__init__`, delete the `self.selectedMaterial: pyd.Material | None = None` field at `feature_demo.py:1232` and its comment — selection now lives on `UIData`.

Replace the call site at `feature_demo.py:1516-1519`:

```python
            # A second, separate window, as in FeatureDemo.cpp:1684-1698. Outside the Settings
            # window's Begin/End: ImGui windows do not nest. Shown only when a pick has resolved
            # to a material -- right-click in the viewport to select one.
            if self.ui.SelectedMaterial is not None:
                self._buildMaterialEditorWindow(self.ui.SelectedMaterial)
```

Replace `_buildMaterialEditorWindow` (`feature_demo.py:1521-1576`) with:

```python
        def _buildMaterialEditorWindow(
            self: UIRenderer, material: pyd.Material
        ) -> None:
            """Draws the Material Editor window over the picked material.

            Split out of buildUI purely for size -- buildUI is already long, and this is a
            self-contained second window rather than another section of the settings panel.

            Stage 2c drove this from a dropdown as an explicit stand-in for picking. The
            dropdown is gone; `material` is whatever the last right-click resolved to.
            """
            # Right-aligned, matching FeatureDemo.cpp:1687: the pivot puts the window's
            # top-right corner at the given point, which is the only way to right-align
            # without knowing the window's width beforehand.
            windowWidth, _ = self.app.GetDeviceManager().GetWindowDimensions()
            # Assumes DisplayFramebufferScale == 1 (no DPI scaling reported to ImGui); on a scaled
            # display this anchor would sit slightly off the true right edge, but ImGui's own
            # on-screen clamping keeps the visible effect small.
            pyd.ImGui.SetNextWindowPos(float(windowWidth) - 10.0, 10.0, 0, 1.0, 0.0)
            pyd.ImGui.Begin("Material Editor", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            # MaterialEditor emits generically-labelled controls, and CollapsingHeader does not
            # push an ID scope -- the same collision the Lights section is wrapped against.
            pyd.ImGui.PushID("MaterialEditor")

            # Sponza's glTF assigns no name to any of its materials (GltfImporter.cpp:914-915
            # only sets one when the source file supplies it), so the ID carries the identity.
            pyd.ImGui.Text(f"Material {material.materialID}: {material.name or '(unnamed)'}")

            if self.ui.SelectedNode is not None:
                pyd.ImGui.Text(f"Node: {self.ui.SelectedNode.GetPath()}")

            previousDomain = material.domain
            material.dirty = pyd.MaterialEditor(material, True)

            # Moving between the opaque and alpha-blended domains changes which draw list the
            # material's geometry belongs to, so the scene has to re-evaluate its content.
            if material.domain != previousDomain:
                self.app.scene.GetSceneGraph().GetRootNode().InvalidateContent()

            pyd.ImGui.PopID()
            pyd.ImGui.End()
```

- [ ] **Step 9: Update the module docstring**

Replace `feature_demo.py:23` and `:30-33`:

```python
"""Port of Donut's FeatureDemo sample -- stages 1, 2a, 2b, 2c and 3a.
```

```python
Still to come in stage 3b: light probes. DLSS, taskflow and the ImGui console are out of
scope permanently: see docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md.
```

and extend the feature sentence at `:25-28` to end with `..., live light and material editors, and right-click material picking.`

- [ ] **Step 10: Run the suite and the example**

Run: `uv run pytest -q`

Expected: 105 passed. No new tests here — this task changes the example, which the GPU-free test layer does not cover.

Run: `uv run feature_demo.py`

Expected, on a machine with a GPU and a display: the scene renders as before; the Material Editor window is absent until you right-click a surface, then appears showing that surface's material ID and node path, and the third-person camera reframes onto the picked object. Report what you observe. If you cannot run it, say so plainly and do not claim the behaviour was verified.

- [ ] **Step 11: Commit**

```bash
git add feature_demo.py
git commit -m "Replace the material dropdown with right-click MaterialID picking

Stage 2c's dropdown was an explicit stand-in for this. PointThirdPersonCameraAt
guards against an empty bounding box, which is mins = FLT_MAX / maxs = -FLT_MAX
rather than a zero-sized box -- the C++ never hits that case because it only
calls the helper with loaded geometry."
```

---

## Task 6: `feature_demo.py` — screenshots and MipMapGen

**Files:**
- Modify: `feature_demo.py` — `UIData.__init__`, `RenderTargets.Init` (`makeSingleSampled` and the `ResolvedColor` line), `FeatureDemo.__init__`, `CreateRenderPasses`, `Render` (after tone mapping, and the tail), `UIRenderer.buildUI`

**Interfaces:**
- Consumes: Task 3's `pyd.MipMapGenPass`, `pyd.MipMapGenPassMode`, `pyd.SaveTextureToFile`, `pyd.FileDialog`.
- Produces: `UIData.TestMipMapGen`, `UIData.ScreenshotFileName`, `FeatureDemo.mipMapGenPass`.

- [ ] **Step 1: Give `ResolvedColor` a mip chain**

In `RenderTargets.Init`, change `makeSingleSampled` to take a mip count, defaulting to 1 so the other four single-sampled targets are unaffected:

```python
            def makeSingleSampled(
                fmt: pyd.Format, name: str, isUav: bool, mipLevels: int = 1
            ) -> pyd.Texture:
```

Add `desc.mipLevels = mipLevels` to that helper's desc block, then change the `ResolvedColor` line:

```python
            # A full mip chain purely so the MipMapGen test pass has something to reduce
            # (FeatureDemo.cpp:135). MipMapGenPass binds one UAV per level at construction, so a
            # single-level texture would give it nothing to write.
            self.ResolvedColor = makeSingleSampled(
                pyd.Format.RGBA16_FLOAT,
                "ResolvedColor",
                True,
                int(math.floor(math.log2(max(width, height)))) + 1,
            )
```

- [ ] **Step 2: Add the UI state**

In `UIData.__init__`:

```python
            self.TestMipMapGen = False
            # Set by the Screenshot button, consumed and cleared by the next Render.
            self.ScreenshotFileName = ""
```

In `FeatureDemo.__init__`:

```python
            self.mipMapGenPass: pyd.MipMapGenPass | None = None
```

- [ ] **Step 3: Create the pass**

In `CreateRenderPasses`, next to the `pixelReadbackPass` construction added in Task 5:

```python
            # MODE_COLOR: ResolvedColor is an RGB target, so it wants the bilinear RGB reduction
            # rather than the single-channel min/max ones (MipMapGenPass.h:47-52).
            self.mipMapGenPass = pyd.MipMapGenPass(
                device,
                self.shaderFactory,
                self.renderTargets.ResolvedColor,
                pyd.MipMapGenPassMode.MODE_COLOR,
            )
```

- [ ] **Step 4: Run MipMapGen and write the screenshot**

In `Render`, immediately before the `self.m_CommonPasses.BlitTexture(...)` call at `feature_demo.py:1211`:

```python
            # Matches FeatureDemo.cpp:1162-1166: reduce ResolvedColor's mip chain, then blit the
            # levels in a spiral over the back buffer so the result is visible.
            if self.ui.TestMipMapGen and self.mipMapGenPass is not None:
                self.mipMapGenPass.Dispatch(self.commandList)
                self.mipMapGenPass.Display(
                    self.m_CommonPasses, self.commandList, framebuffer
                )
```

Immediately after `device.executeCommandList(self.commandList)` and before Task 5's pick-resolution block:

```python
            # After executeCommandList: SaveTextureToFile requires that no immediate command
            # list be open (TextureCache.h:238) and creates temporary resources internally,
            # which is why the sample calls it here too (FeatureDemo.cpp:1191-1195).
            if self.ui.ScreenshotFileName:
                fileName = self.ui.ScreenshotFileName
                self.ui.ScreenshotFileName = ""
                saved = pyd.SaveTextureToFile(
                    device,
                    self.m_CommonPasses,
                    framebuffer.getDesc().getColorAttachment(0).texture,
                    pyd.ResourceStates.RenderTarget,
                    fileName,
                )
                if saved:
                    pyd.log.info(f"Screenshot written to {fileName}")
                else:
                    pyd.log.error(f"Failed to write screenshot to {fileName}")
```

- [ ] **Step 5: Add the UI controls**

Add this module-level helper next to the other module-level constants near `feature_demo.py:105`:

```python
    def _nextScreenshotPath() -> str:
        """First unused screenshot_NNNN.bmp beside this script.

        The fallback when FileDialog returns None. That return does not distinguish "user
        cancelled" from "no dialog available" -- on Linux the dialog shells out to `zenity`,
        which may not be installed -- so a cancelled dialog also writes a file. That is
        deliberate: the alternative is a button that silently does nothing under WSL, and the
        file is trivially deleted.
        """
        directory = pathlib.Path(__file__).parent
        index = 1
        while True:
            candidate = directory / f"screenshot_{index:04d}.bmp"
            if not candidate.exists():
                return str(candidate)
            index += 1
```

Add `import pathlib` alongside `import math` at `feature_demo.py:44`.

In `UIRenderer.buildUI`, after the Tone Mapping collapsing-header section ends and before `pyd.ImGui.End()` at `feature_demo.py:1512`, matching the sample's ordering at `FeatureDemo.cpp:1669-1680`:

```python
            if pyd.ImGui.Button("Screenshot"):
                # Blocking modal. BMP first, because SaveTextureToFile picks its encoder from
                # the extension and BMP is what the sample offers (FeatureDemo.cpp:1671).
                chosen = pyd.FileDialog(
                    False, [("BMP files", "*.bmp"), ("All files", "*.*")]
                )
                self.ui.ScreenshotFileName = (
                    chosen if chosen is not None else _nextScreenshotPath()
                )

            pyd.ImGui.Separator()
            _, self.ui.TestMipMapGen = pyd.ImGui.Checkbox(
                "Test MipMapGen Pass", self.ui.TestMipMapGen
            )
```

`ImGui.Button` returns a plain `bool` (`src/cpp/_pydonut.cpp:3416`), not the `(changed, value)` tuple the out-param widgets like `Checkbox` use — so it is used bare in the `if` above.

- [ ] **Step 6: Run the suite and the example**

Run: `uv run pytest -q`

Expected: 105 passed.

Run: `uv run feature_demo.py`

Expected: the Screenshot button opens a save dialog and writes a readable BMP of the current frame; cancelling it instead writes `screenshot_0001.bmp` beside the script and logs the path. Ticking "Test MipMapGen Pass" overlays a spiral of progressively smaller copies of the frame. Report what you observe, or say plainly that you could not run it.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Add screenshots and the MipMapGen test pass to feature_demo.py

ResolvedColor gains a full mip chain so MipMapGenPass has levels to
reduce. A cancelled or unavailable file dialog falls back to an
auto-named screenshot_NNNN.bmp, since FileDialog's None return cannot
distinguish cancellation from a missing zenity under WSL."
```

---

## Task 7: `feature_demo.py` — stereo

**Files:**
- Modify: `feature_demo.py` — `UIData.__init__`, `SetupView` (`:828-853`), `Render` tail (`:1216`), `UIRenderer.buildUI`

**Interfaces:**
- Consumes: Task 4's `pyd.StereoPlanarView`; Task 1's ten widened signatures (every pass `self.view` reaches).
- Produces: `UIData.Stereo`.

- [ ] **Step 1: Add the UI flag**

In `UIData.__init__`:

```python
            # Side-by-side split viewport, not stereo hardware -- both eyes render into the one
            # back buffer (FeatureDemo.cpp:726-744).
            self.Stereo = False
```

- [ ] **Step 2: Branch `SetupView` on the view topology**

Replace `SetupView` (`feature_demo.py:828-853`) with:

```python
        def SetupView(self: FeatureDemo, width: int, height: int) -> None:
            # TAA needs a different sub-pixel offset every frame, otherwise TemporalResolve
            # accumulates identical samples and a static camera gets no anti-aliasing at all.
            # Jitter only in TEMPORAL mode, and clear it to (0, 0) in every other mode, so
            # switching away does not leave a stale offset skewing the projection matrix
            # (View.cpp:68-70 folds it into m_PixelOffsetMatrix on UpdateCache).
            # taaPass is None on the first frame, before CreateRenderPasses has run.
            if self.ui.AntiAliasingMode == AntiAliasingMode.TEMPORAL and self.taaPass is not None:
                pixelOffsetX, pixelOffsetY = self.taaPass.GetCurrentPixelOffset()
            else:
                pixelOffsetX, pixelOffsetY = 0.0, 0.0

            # Swapping the view type mid-run leaves viewPrevious holding the *other* kind, which
            # TAA would then resolve against. Rebuild both together and copy across, as
            # FeatureDemo.cpp:722-726 and :753 do.
            topologyChanged = False
            if self.ui.Stereo:
                if not isinstance(self.view, pyd.StereoPlanarView):
                    self.view = pyd.StereoPlanarView()
                    topologyChanged = True
            else:
                if not isinstance(self.view, pyd.PlanarView):
                    self.view = pyd.PlanarView()
                    topologyChanged = True

            if self.ui.Stereo:
                # Left eye owns the left half, right eye the right half of one back buffer.
                self.view.LeftView.SetViewport(pyd.Viewport(width * 0.5, float(height)))
                self.view.RightView.SetViewport(
                    pyd.Viewport(width * 0.5, float(width), 0.0, float(height), 0.0, 1.0)
                )
                self.view.LeftView.SetPixelOffset(pixelOffsetX, pixelOffsetY)
                self.view.RightView.SetPixelOffset(pixelOffsetX, pixelOffsetY)
                # PER-EYE aspect ratio: each eye is half the framebuffer wide
                # (FeatureDemo.cpp:736). The shim does not halve it internally.
                self.view.SetMatricesFromSwitchableCamera(
                    self.camera, width / height * 0.5
                )
                # StereoPlanarView has no cache of its own -- each eye is updated individually.
                self.view.LeftView.UpdateCache()
                self.view.RightView.UpdateCache()
                # The third-person camera converts mouse drags into orbit and pan amounts using
                # the view's own projection and viewport, so it needs one concrete eye, not the
                # composite (FeatureDemo.cpp:751).
                self.camera.GetThirdPersonCamera().SetView(self.view.LeftView)
            else:
                self.view.SetViewport(pyd.Viewport(float(width), float(height)))
                self.view.SetPixelOffset(pixelOffsetX, pixelOffsetY)
                self.view.SetMatricesFromSwitchableCamera(self.camera, width / height)
                self.view.UpdateCache()
                # As in FeatureDemo.cpp:773.
                self.camera.GetThirdPersonCamera().SetView(self.view)

            if topologyChanged:
                # Seed viewPrevious from the view just built, so the first frame after a switch
                # does not resolve this frame against the other topology's leftovers.
                self.viewPrevious = self._snapshotView()
                # TAA history built against the old topology is meaningless now.
                self.previousViewsValid = False
```

The TAA history-validity flag is `self.previousViewsValid`, initialised in `FeatureDemo.__init__` (`feature_demo.py:302`), already cleared on render-target rebuild at `:998`, and read at `:1133`.

- [ ] **Step 3: Make the view snapshot type-aware**

Add as a new method on `FeatureDemo`, immediately after `SetupView`:

```python
        def _snapshotView(self: FeatureDemo) -> pyd.PlanarView | pyd.StereoPlanarView:
            """Copies the current view, preserving its topology.

            The copy constructor is the only way to snapshot a view -- neither type exposes its
            matrices to Python -- and each type has its own, so this has to switch.
            """
            if isinstance(self.view, pyd.StereoPlanarView):
                return pyd.StereoPlanarView(self.view)
            return pyd.PlanarView(self.view)
```

Replace `feature_demo.py:1216` (`self.viewPrevious = pyd.PlanarView(self.view)`) with:

```python
            self.viewPrevious = self._snapshotView()
```

- [ ] **Step 4: Add the Stereo checkbox**

In `UIRenderer.buildUI`, immediately after the VSync checkbox at `feature_demo.py:1274`, matching the sample's placement at `FeatureDemo.cpp:1545`:

```python
            _, self.ui.Stereo = pyd.ImGui.Checkbox("Stereo", self.ui.Stereo)
```

- [ ] **Step 5: Update the module docstring**

Extend the feature sentence at `feature_demo.py:25-28` to end with `..., right-click material picking, screenshots, a MipMapGen test pass and a side-by-side stereo mode.`

- [ ] **Step 6: Run the suite and the example**

Run: `uv run pytest -q`

Expected: 105 passed.

Run: `uv run feature_demo.py`

Expected: ticking Stereo splits the frame into two side-by-side views offset by 0.2 world units; shadows stay correctly placed on the geometry in both eyes (the failure this mode is most likely to expose, and what Task 1's `SetupForPlanarViewStable` correction exists to prevent). Untick it and the single view returns with no TAA ghosting across the switch. Report what you observe, or say plainly that you could not run it.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Add the side-by-side stereo mode to feature_demo.py

SetupView rebuilds both view and viewPrevious together on a topology
change and invalidates the TAA history, so the first frame after a switch
cannot resolve against the other topology's leftovers."
```

---

## Self-review

**Spec coverage.** Every section maps to a task: picking → Tasks 2, 5. `MaterialIDPass`, readback format, `PointThirdPersonCameraAt` → Tasks 2, 5. Screenshots and `FileDialog` reshaping and the fallback → Tasks 3, 6. MipMapGen → Tasks 3, 6. Stereo, the ten-signature table and the non-mechanical `SetupForPlanarViewStable` correction → Tasks 1, 4, 7. All new bindings listed in the spec's "New native bindings" section appear in Tasks 2–4. The `Skipped` list is honoured: no `FolderDialog`, no `StereoView` matrix accessors, no `MipMapGenPass` binding-set internals — and Task 3 and Task 4 each assert one of those absences.

**Three spec deviations** are recorded at the top of this plan with their reasons: device-needing tests narrowed to signature checks, `materialIDPass` moved out of `CreateRenderPasses`, and the empty-bounding-box assertion inverted. The third also added a guard to `PointThirdPersonCameraAt` that the C++ has no equivalent of.

**Type consistency.** `pickPosition` is a `tuple[int, int]` everywhere; `Capture` takes it unpacked as two ints. `GetGlobalBoundingBox` returns a 6-tuple in Task 2's binding, Task 2's test and Task 5's helper. `ReadUInts` returns a 4-tuple, unpacked as `materialID, instanceIndex, _, _`. `SelectedMaterial`/`SelectedNode` live on `UIData` in Tasks 5's writer and reader; `UIRenderer.selectedMaterial` is deleted, not shadowed. `_snapshotView` is defined in Task 7 Step 3 and used in Task 7 Steps 2 and 3. `MipMapGenPassMode.MODE_COLOR` is spelled identically in Task 3's binding, stub, test and Task 6's call.

**No placeholders and no "check this yourself" steps.** Four facts the first draft deferred to the implementer were verified while reviewing and are now stated outright, each with the line that proves it: the draw-strategy attribute names (`feature_demo.py:299`), `ImGui.Button`'s plain-`bool` return (`src/cpp/_pydonut.cpp:3416`), the TAA history flag's name (`feature_demo.py:302`), and the `Enum` stub style (`src/pydonut/_pydonut.pyi:1483-1487`).

Two of Task 2's tests were rewritten during this review: they had used `SceneGraph.Attach` and `SceneGraphNode.GetLeaf`, neither of which is bound. They now build their node through `AttachLeafNode` — the only attach the binding exposes — and compare on `GetPath()`, since `SceneGraphNode` binds no `GetName`.
