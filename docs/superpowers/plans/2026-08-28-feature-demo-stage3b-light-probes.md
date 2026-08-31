# FeatureDemo Stage 3b: Light Probes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Note, 2026-08-31 — DLSS is no longer out of scope.** This plan's quoted docstrings and
> commit messages say DLSS is permanently out of scope; that was true when it was written.
> DLSS was ported on 2026-08-31 behind donut's `DONUT_WITH_DLSS=ON` build option — see the
> superseded note in `docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md`. The
> snippets below are left exactly as this stage wrote them: they record that stage, not the
> current `feature_demo.py`. taskflow and the ImGui console do remain out of scope.

**Goal:** Port FeatureDemo's light probes — four on-demand cube-map captures, processed into diffuse irradiance and roughness-filtered specular maps, feeding both the forward and the deferred shading path — completing the PyDonut FeatureDemo port.

**Architecture:** Seven tasks. Tasks 1–3 add the native bindings (`LightProbe` and its two consumers; `LightProbeProcessingPass`; six supporting accessors) and are mutually independent. Tasks 4–7 wire them into `feature_demo.py` sequentially: probe allocation, the capture routine, per-frame plumbing, then UI. Every binding task ships tests in one new GPU-free file; the behavioural proof that a probe actually lights the scene is the manual run at the end of Task 7.

**Tech Stack:** C++17 + pybind11 3.x (`src/cpp/_pydonut.cpp`), type stubs (`src/pydonut/_pydonut.pyi`), re-exports (`src/pydonut/__init__.py`), Python 3 example (`feature_demo.py`), pytest via `uv`.

**Spec:** `docs/superpowers/specs/2026-08-28-feature-demo-stage3b-light-probes-design.md`

## Global Constraints

- **Donut math types never cross into Python.** `dm::frustum`, `dm::box3`, `dm::float3`, `dm::affine3` and `nvrhi::TextureSubresourceSet` stay in C++. Flatten to scalars/tuples, or fold the argument away entirely. Stated at `src/pydonut/_pydonut.pyi:1676`; applied by every prior stage.
- **Every binding change is mirrored in three places:** `src/cpp/_pydonut.cpp`, `src/pydonut/_pydonut.pyi`, and (for new top-level names) both the import block and the `__all__` list in `src/pydonut/__init__.py`.
- **Build and test with `uv sync && uv run pytest -q`.** `uv sync` rebuilds the native module; a bare `pytest` run tests a stale `.pyd`.
- **Test baseline is 105 passing.** Each task states its expected new total. The suite is GPU-free and runs in well under a second — nothing in it may create a device.
- **pybind11 3.x docstring rendering:** integral parameters render as `typing.SupportsInt | typing.SupportsIndex`, floats as `typing.SupportsFloat | typing.SupportsIndex`, `std::vector<std::shared_ptr<T>>` as `collections.abc.Sequence[pydonut._pydonut.T]`. Signature assertions must match that spelling, never a bare `int`/`float`.
- **Release build, asserts compiled out.** Any donut precondition guarded only by `assert` must be re-checked in the binding and raised as a Python exception, or documented as unguarded.
- **New files carry the project's license header** — copy the 22-line block verbatim from `test/test_stereo_bindings.py`.
- **Commit on `main`,** as every prior stage in this port did.

---

## Task 1: `LightProbe` and its two consumers

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (register `LightProbe` immediately before `PyDeferredLightingInputs` at `:2682`; extend `PyDeferredLightingInputs` at `:341-357`; widen `PrepareLights` at `:2723-2732`)
- Modify: `src/pydonut/_pydonut.pyi` (new `LightProbe` class; `DeferredLightingPassInputs.SetLightProbes`; `ForwardShadingPass.PrepareLights`)
- Modify: `src/pydonut/__init__.py` (import + `__all__`)
- Test: `test/test_lightprobe_bindings.py` (create)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces, for Tasks 4–6: `pyd.LightProbe()` with read/write `name: str`, `diffuseMap`/`specularMap`/`environmentBrdf: Texture | None`, `diffuseArrayIndex`/`specularArrayIndex: int`, `diffuseScale`/`specularScale: float`, `enabled: bool`; methods `IsActive() -> bool`, `SetBoundsEmpty() -> None`, `SetBoundsInfinite() -> None`, `SetBoundsFromBox(minX, minY, minZ, maxX, maxY, maxZ) -> None`. Also `DeferredLightingPassInputs.SetLightProbes(probes: list[LightProbe]) -> None` and `ForwardShadingPass.PrepareLights(context, commandList, lights, topR, topG, topB, bottomR, bottomG, bottomB, lightProbes: list[LightProbe] = []) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `test/test_lightprobe_bindings.py`. Start with the 22-line license header copied verbatim from `test/test_stereo_bindings.py`, then:

```python
"""Surface tests for the FeatureDemo stage 3b light-probe bindings.

These need no GPU. LightProbe is a plain struct and is constructible standalone;
LightProbeProcessingPass and the passes that consume probes all need a device, so those get
presence-and-signature checks against __doc__ instead of live calls -- the same split
test_picking_bindings.py uses for MaterialIDPass and PixelReadbackPass.

One thing deliberately NOT tested here: that SetBoundsFromBox makes a probe active. IsActive()
requires a non-empty bounds AND an assigned diffuse or specular map (SceneTypes.cpp:379-389),
and a Texture cannot be created without a device. The behavioural proof that the bounds helpers
reach the real field is the manual run at the end of the stage: feature_demo.py sets every
probe's bounds empty at creation, so if SetBoundsFromBox silently no-oped, IsActive() would stay
false and a captured probe would light nothing.
"""

from __future__ import annotations

import pydonut as pyd


def test_light_probe_is_constructible() -> None:
    assert pyd.LightProbe() is not None


def test_light_probe_is_re_exported() -> None:
    # Reachable as pyd.LightProbe, not just pyd._pydonut.LightProbe -- feature_demo.py builds
    # them by name.
    assert "LightProbe" in pyd.__all__


def test_light_probe_defaults_match_the_struct() -> None:
    # SceneTypes.h:362-367. Nothing in feature_demo.py sets the scales or `enabled` at
    # construction, so the C++ defaults are what a fresh probe starts with.
    probe = pyd.LightProbe()
    assert probe.diffuseArrayIndex == 0
    assert probe.specularArrayIndex == 0
    assert probe.diffuseScale == 1.0
    assert probe.specularScale == 1.0
    assert probe.enabled is True
    assert probe.diffuseMap is None
    assert probe.specularMap is None
    assert probe.environmentBrdf is None


def test_light_probe_fields_round_trip() -> None:
    # The UI writes diffuseScale/specularScale onto the probe every frame and CreateLightProbes
    # writes the name and both array indices, so every one of these must be settable.
    probe = pyd.LightProbe()
    probe.name = "3"
    probe.diffuseArrayIndex = 2
    probe.specularArrayIndex = 2
    probe.diffuseScale = 0.25
    probe.specularScale = 4.0
    probe.enabled = False
    assert probe.name == "3"
    assert probe.diffuseArrayIndex == 2
    assert probe.specularArrayIndex == 2
    assert probe.diffuseScale == 0.25
    assert probe.specularScale == 4.0
    assert probe.enabled is False


def test_fresh_light_probe_is_inactive() -> None:
    # IsActive() has three conditions (SceneTypes.cpp:379-389). It is worth being precise about
    # WHICH one rejects a fresh probe, because the obvious guess is wrong: a default-constructed
    # probe's bounds are frustum::infinite(), not empty, so the bounds check PASSES. What fails
    # is the map check -- neither diffuseMap nor specularMap is assigned.
    probe = pyd.LightProbe()
    assert probe.IsActive() is False


def test_disabled_light_probe_is_inactive() -> None:
    probe = pyd.LightProbe()
    probe.enabled = False
    assert probe.IsActive() is False


def test_bounds_helpers_replace_the_frustum_type() -> None:
    # dm::frustum never crosses into Python: `bounds` is not a property, it is three
    # construction methods. This pins both halves -- the methods exist and are callable, and
    # no Frustum type was introduced alongside them.
    probe = pyd.LightProbe()
    assert probe.SetBoundsEmpty() is None
    assert probe.SetBoundsInfinite() is None
    assert probe.SetBoundsFromBox(-1.0, -2.0, -3.0, 1.0, 2.0, 3.0) is None
    assert not hasattr(pyd, "Frustum")
    assert not hasattr(pyd.LightProbe, "bounds")


def test_set_bounds_from_box_takes_six_flat_floats() -> None:
    # dm::box3 does not cross into Python, exactly as for
    # SceneGraphNode.GetGlobalBoundingBox's six-float return.
    doc = pyd.LightProbe.SetBoundsFromBox.__doc__
    assert doc is not None
    for name in ("minX", "minY", "minZ", "maxX", "maxY", "maxZ"):
        assert f"{name}: typing.SupportsFloat" in doc, name
    assert "box3" not in doc


def test_prepare_lights_still_accepts_the_nine_argument_form() -> None:
    # THE regression guard for this task. deferred_shading.py, threaded_rendering.py and every
    # other existing caller passes nine arguments; lightProbes is trailing and defaulted so they
    # keep working untouched. If a future edit reorders the parameters, this fails first.
    doc = pyd.ForwardShadingPass.PrepareLights.__doc__
    assert doc is not None
    assert "lightProbes: collections.abc.Sequence[pydonut._pydonut.LightProbe] = []" in doc
    # bottomB is the last of the nine originals, so lightProbes following it proves it is
    # trailing rather than inserted mid-list.
    assert doc.index("bottomB") < doc.index("lightProbes")


def test_deferred_inputs_take_light_probes() -> None:
    # Inputs::lightProbes is a non-owning pointer to a vector (DeferredLightingPass.h:82), so
    # the binding wrapper has to own the vector -- the same trick SetLights already uses. A live
    # call plus a surviving reference is what proves the vector outlived the call.
    inputs = pyd.DeferredLightingPassInputs()
    probes = [pyd.LightProbe(), pyd.LightProbe()]
    assert inputs.SetLightProbes(probes) is None
    del probes
    # No crash and no error means the wrapper kept its own shared_ptr copies.
    assert inputs.SetLightProbes([]) is None


def test_set_light_probes_empty_list_is_the_off_switch() -> None:
    # DeferredLightingPass::Render guards with `if (inputs.lightProbes)` and then iterates
    # (DeferredLightingPass.cpp:221-224), so a non-null pointer to an empty vector iterates zero
    # times -- indistinguishable from the sample's nullptr. feature_demo.py relies on that:
    # it passes [] rather than needing a way to null the pointer.
    inputs = pyd.DeferredLightingPassInputs()
    assert inputs.SetLightProbes([]) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_lightprobe_bindings.py -q`

Expected: collection succeeds, then failures — `AttributeError: module 'pydonut' has no attribute 'LightProbe'` on most tests, and a missing `SetLightProbes` / missing `lightProbes` in the `__doc__` assertions.

- [ ] **Step 3: Register `LightProbe`**

In `src/cpp/_pydonut.cpp`, immediately **before** the `py::class_<PyDeferredLightingInputs>` block at `:2682`. Order matters: `SetLightProbes`' argument type and `PrepareLights`' default argument are both converted at `def` time, so `LightProbe` must already be registered.

```cpp
    // engine::LightProbe (SceneTypes.h:356-371). shared_ptr holder is mandatory, not stylistic:
    // both consumers take const std::vector<std::shared_ptr<LightProbe>>&.
    //
    // `bounds` (a dm::frustum) is NOT a property -- donut math types never cross into Python.
    // The sample only ever CONSTRUCTS a probe's bounds: frustum::empty() at creation
    // (FeatureDemo.cpp:1294) and frustum::fromBox(box3(p, p).grow(10)) after a capture
    // (:1430-1431). It never reads them back, so three construction methods cover every use
    // and no Frustum type is needed.
    //
    // Load-bearing rather than cosmetic: IsActive() rejects empty bounds
    // (SceneTypes.cpp:383-384), so a probe whose bounds were never set past empty contributes
    // nothing to either shading path -- which is exactly how feature_demo.py keeps an
    // uncaptured probe dark.
    py::class_<donut::engine::LightProbe, std::shared_ptr<donut::engine::LightProbe>>(m, "LightProbe")
        .def(py::init<>())
        .def_readwrite("name", &donut::engine::LightProbe::name)
        // The three maps are nvrhi::TextureHandle, so they need def_property with a raw
        // ITexture* on the Python side, matching DeferredLightingPassInputs.output below.
        .def_property("diffuseMap",
            [](const donut::engine::LightProbe &self) -> nvrhi::ITexture* { return self.diffuseMap; },
            [](donut::engine::LightProbe &self, nvrhi::ITexture* tex) { self.diffuseMap = tex; },
            py::return_value_policy::reference)
        .def_property("specularMap",
            [](const donut::engine::LightProbe &self) -> nvrhi::ITexture* { return self.specularMap; },
            [](donut::engine::LightProbe &self, nvrhi::ITexture* tex) { self.specularMap = tex; },
            py::return_value_policy::reference)
        .def_property("environmentBrdf",
            [](const donut::engine::LightProbe &self) -> nvrhi::ITexture* { return self.environmentBrdf; },
            [](donut::engine::LightProbe &self, nvrhi::ITexture* tex) { self.environmentBrdf = tex; },
            py::return_value_policy::reference)
        .def_readwrite("diffuseArrayIndex", &donut::engine::LightProbe::diffuseArrayIndex)
        .def_readwrite("specularArrayIndex", &donut::engine::LightProbe::specularArrayIndex)
        .def_readwrite("diffuseScale", &donut::engine::LightProbe::diffuseScale)
        .def_readwrite("specularScale", &donut::engine::LightProbe::specularScale)
        .def_readwrite("enabled", &donut::engine::LightProbe::enabled)
        // enabled AND non-empty bounds AND at least one map with a non-zero scale
        // (SceneTypes.cpp:379-389). Both lighting passes skip probes failing this.
        .def("IsActive", &donut::engine::LightProbe::IsActive)
        .def("SetBoundsEmpty", [](donut::engine::LightProbe &self) {
            self.bounds = donut::math::frustum::empty();
        })
        .def("SetBoundsInfinite", [](donut::engine::LightProbe &self) {
            self.bounds = donut::math::frustum::infinite();
        })
        // Six flat floats rather than a box3, matching SceneGraphNode.GetGlobalBoundingBox's
        // six-float return on the other side of the same rule.
        .def("SetBoundsFromBox", [](donut::engine::LightProbe &self,
                float minX, float minY, float minZ, float maxX, float maxY, float maxZ) {
            self.bounds = donut::math::frustum::fromBox(donut::math::box3(
                donut::math::float3(minX, minY, minZ),
                donut::math::float3(maxX, maxY, maxZ)));
        }, py::arg("minX"), py::arg("minY"), py::arg("minZ"),
           py::arg("maxX"), py::arg("maxY"), py::arg("maxZ"));
```

If `donut/core/math/frustum.h` is not already reachable, add `#include <donut/core/math/math.h>` to the include block at the top of the file (it aggregates `frustum.h`, `box.h` and `vector.h`).

- [ ] **Step 4: Give `PyDeferredLightingInputs` an owned probe vector**

In `src/cpp/_pydonut.cpp`, extend the wrapper at `:345-357`:

```cpp
struct PyDeferredLightingInputs : donut::render::DeferredLightingPass::Inputs {
    std::vector<std::shared_ptr<donut::engine::Light>> ownedLights;
    std::vector<std::shared_ptr<donut::engine::LightProbe>> ownedLightProbes;

    void SetLights(std::vector<std::shared_ptr<donut::engine::Light>> newLights) {
        ownedLights = std::move(newLights);
        lights = &ownedLights;
    }

    // Inputs::lightProbes is a non-owning pointer, exactly like Inputs::lights -- same fix.
    // An empty list is the off switch and needs no null path: DeferredLightingPass::Render
    // guards with `if (inputs.lightProbes)` and then iterates (DeferredLightingPass.cpp:221-224),
    // so a non-null pointer to an empty vector leaves numLightProbes at 0, exactly as nullptr
    // does.
    void SetLightProbes(std::vector<std::shared_ptr<donut::engine::LightProbe>> newProbes) {
        ownedLightProbes = std::move(newProbes);
        lightProbes = &ownedLightProbes;
    }

    void SetAmbientColors(float topR, float topG, float topB, float bottomR, float bottomG, float bottomB) {
        ambientColorTop = donut::math::float3(topR, topG, topB);
        ambientColorBottom = donut::math::float3(bottomR, bottomG, bottomB);
    }
};
```

Then add the `def` to the class block at `:2682`, directly after the existing `SetLights` line:

```cpp
        // Every probe submitted in one call must carry the SAME diffuseMap, specularMap and
        // environmentBrdf: DeferredLightingPass::Render logs an error and returns WITHOUT
        // RENDERING THE FRAME otherwise (DeferredLightingPass.cpp:246-253). That is why
        // feature_demo.py allocates two shared cube-map arrays indexed by slice rather than a
        // private texture pair per probe. Same failure mode as two lights with different
        // shadow maps (:172-175).
        .def("SetLightProbes", &PyDeferredLightingInputs::SetLightProbes, py::arg("lightProbes"))
```

- [ ] **Step 5: Widen `PrepareLights`**

Replace the binding at `src/cpp/_pydonut.cpp:2721-2732` with:

```cpp
        // lightProbes is trailing and defaulted so the nine-argument form every other example
        // uses (deferred_shading.py, threaded_rendering.py, rt_bindless.py) keeps compiling
        // untouched. Stage 3b replaced the previously hardcoded empty vector with this.
        .def("PrepareLights", [](donut::render::ForwardShadingPass &self, donut::render::ForwardShadingPass::Context &context,
                nvrhi::ICommandList* commandList, const std::vector<std::shared_ptr<donut::engine::Light>> &lights,
                float topR, float topG, float topB, float bottomR, float bottomG, float bottomB,
                const std::vector<std::shared_ptr<donut::engine::LightProbe>> &lightProbes) {
            self.PrepareLights(context, commandList, lights,
                donut::math::float3(topR, topG, topB), donut::math::float3(bottomR, bottomG, bottomB),
                lightProbes);
        }, py::arg("context"), py::arg("commandList"), py::arg("lights"),
           py::arg("topR"), py::arg("topG"), py::arg("topB"), py::arg("bottomR"), py::arg("bottomG"), py::arg("bottomB"),
           py::arg("lightProbes") = std::vector<std::shared_ptr<donut::engine::LightProbe>>{},
           // See the comment on CommandList.open above -- released for threaded_rendering.py's
           // concurrent per-face recording.
           py::call_guard<py::gil_scoped_release>());
```

- [ ] **Step 6: Mirror in the type stubs**

In `src/pydonut/_pydonut.pyi`, add `LightProbe` above `class DeferredLightingPassInputs` (`:1508`):

```python
# engine::LightProbe (SceneTypes.h:356-371) -- image-based ambient light captured from a point
# in the scene. Held by shared_ptr in C++; both lighting passes take a list of them.
#
# `bounds` (a dm::frustum) is not a property: donut math types never cross into Python, and the
# only uses are constructions, never reads. The three SetBounds* methods cover them. Bounds are
# load-bearing -- IsActive() rejects an empty frustum, so an uncaptured probe stays dark.
class LightProbe():
    def __init__(self: LightProbe) -> None: ...
    name: str
    diffuseMap: Optional[Texture]
    specularMap: Optional[Texture]
    environmentBrdf: Optional[Texture]
    # Slice indices into the shared cube-map ARRAYS. The pass multiplies by 6 at the call site.
    diffuseArrayIndex: int
    specularArrayIndex: int
    diffuseScale: float
    specularScale: float
    enabled: bool
    # enabled AND non-empty bounds AND at least one map with a non-zero scale.
    def IsActive(self: LightProbe) -> bool: ...
    def SetBoundsEmpty(self: LightProbe) -> None: ...
    def SetBoundsInfinite(self: LightProbe) -> None: ...
    def SetBoundsFromBox(self: LightProbe, minX: float, minY: float, minZ: float, maxX: float, maxY: float, maxZ: float) -> None: ...
```

In `class DeferredLightingPassInputs`, after `SetLights`:

```python
    # Every probe in one call must share diffuseMap, specularMap and environmentBrdf --
    # DeferredLightingPass::Render logs an error and returns without rendering otherwise
    # (DeferredLightingPass.cpp:246-253). An empty list is the off switch.
    def SetLightProbes(self: DeferredLightingPassInputs, lightProbes: list[LightProbe]) -> None: ...
```

Replace the `PrepareLights` stub and its comment at `:1537-1538`:

```python
    # lightProbes is trailing and defaulted: the nine-argument form used by deferred_shading.py
    # and the other examples still works.
    def PrepareLights(self: ForwardShadingPass, context: ForwardShadingPassContext, commandList: CommandList, lights: list[Light], topR: float, topG: float, topB: float, bottomR: float, bottomG: float, bottomB: float, lightProbes: list[LightProbe] = ...) -> None: ...
```

- [ ] **Step 7: Re-export `LightProbe`**

In `src/pydonut/__init__.py`, add the import beside the other scene-type imports and the name to `__all__`:

```python
from pydonut._pydonut import LightProbe
```

```python
    'LightProbe',
```

- [ ] **Step 8: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`

Expected: 116 passed (105 baseline + 11 new).

- [ ] **Step 9: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_lightprobe_bindings.py
git commit -m "Bind LightProbe and its two consumers

LightProbe::bounds is a dm::frustum, but the sample only ever constructs
it -- empty at creation, fromBox after a capture -- and never reads it
back, so three SetBounds* methods cover every use and no Frustum type is
introduced. Bounds are load-bearing: IsActive() rejects an empty frustum.

PrepareLights' lightProbes argument is trailing and defaulted, so the
nine-argument form deferred_shading.py and the other examples use keeps
working; a test pins that explicitly.

SetLightProbes gives Inputs::lightProbes an owned vector to point at, the
same fix SetLights already applies. An empty list is the off switch:
DeferredLightingPass::Render guards on the pointer and then iterates, so
a non-null pointer to an empty vector behaves exactly as nullptr does."
```

---

## Task 2: `LightProbeProcessingPass`

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (include; new class block beside `MipMapGenPass` at `:2898`)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_lightprobe_bindings.py` (append)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces, for Tasks 4–6: `pyd.LightProbeProcessingPass(device, shaderFactory, commonPasses, intermediateTextureSize=1024, intermediateTextureFormat=Format.RGBA16_FLOAT)` with `.BlitCubemap(commandList, inCubeMap, inBaseArraySlice, inMipLevel, outCubeMap, outBaseArraySlice, outMipLevel)`, `.GenerateCubemapMips(commandList, cubeMap, baseArraySlice, sourceMipLevel, levelsToGenerate)`, `.RenderDiffuseMap(commandList, inEnvironmentMap, outDiffuseMap, outBaseArraySlice, outMipLevel)`, `.RenderSpecularMap(commandList, roughness, inEnvironmentMap, outSpecularMap, outBaseArraySlice, outMipLevel)`, `.RenderEnvironmentBrdfTexture(commandList)`, `.GetEnvironmentBrdfTexture() -> Texture`, `.ResetCaches()`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_lightprobe_bindings.py`:

```python
def test_light_probe_processing_pass_is_re_exported() -> None:
    assert "LightProbeProcessingPass" in pyd.__all__


def test_light_probe_processing_pass_exposes_every_method() -> None:
    # All seven bind. BlitCubemap is the one the sample never calls, but it is a single line and
    # omitting it would leave a visibly incomplete class.
    for name in ("BlitCubemap", "GenerateCubemapMips", "RenderDiffuseMap", "RenderSpecularMap",
                 "RenderEnvironmentBrdfTexture", "GetEnvironmentBrdfTexture", "ResetCaches"):
        assert hasattr(pyd.LightProbeProcessingPass, name), name


def test_light_probe_processing_pass_constructor_defaults() -> None:
    # LightProbeProcessingPass.h:93-99. feature_demo.py passes neither, so the defaults are what
    # it actually runs with.
    doc = pyd.LightProbeProcessingPass.__init__.__doc__
    assert doc is not None
    assert "intermediateTextureSize: typing.SupportsInt | typing.SupportsIndex = 1024" in doc
    assert "intermediateTextureFormat: pydonut._pydonut.Format = " in doc
    assert "RGBA16_FLOAT" in doc


def test_render_diffuse_map_folds_away_the_subresource_set() -> None:
    # C++ takes nvrhi::TextureSubresourceSet inSubresources (LightProbeProcessingPass.h:118).
    # That type is not exposed to Python anywhere, AllSubresources is what the sample passes
    # (FeatureDemo.cpp:1413), and the existing clear/resolve bindings already set the precedent
    # of folding the subresource argument away. So the parameter is absent, not optional.
    doc = pyd.LightProbeProcessingPass.RenderDiffuseMap.__doc__
    assert doc is not None
    assert "inSubresources" not in doc
    assert "TextureSubresourceSet" not in doc
    assert "inEnvironmentMap" in doc
    assert "outDiffuseMap" in doc


def test_render_specular_map_takes_roughness_before_the_source() -> None:
    # Argument order matches C++ (LightProbeProcessingPass.h:126-132): roughness precedes the
    # environment map. feature_demo.py loops mip levels computing roughness per level, so
    # getting this backwards would silently pass a mip index as a roughness.
    doc = pyd.LightProbeProcessingPass.RenderSpecularMap.__doc__
    assert doc is not None
    assert doc.index("roughness") < doc.index("inEnvironmentMap")
    assert "inSubresources" not in doc


def test_render_specular_map_names_its_own_target() -> None:
    # donut's header calls this parameter outDiffuseMap (LightProbeProcessingPass.h:131), a
    # copy-paste slip from RenderDiffuseMap. The binding names it outSpecularMap.
    doc = pyd.LightProbeProcessingPass.RenderSpecularMap.__doc__
    assert doc is not None
    assert "outSpecularMap" in doc
    assert "outDiffuseMap" not in doc


def test_generate_cubemap_mips_signature() -> None:
    # feature_demo.py calls this with (colorTexture, 0, 0, mipLevels - 1).
    doc = pyd.LightProbeProcessingPass.GenerateCubemapMips.__doc__
    assert doc is not None
    for name in ("cubeMap", "baseArraySlice", "sourceMipLevel", "levelsToGenerate"):
        assert name in doc, name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_lightprobe_bindings.py -q`

Expected: 11 passed, 7 failed — `AttributeError: module 'pydonut' has no attribute 'LightProbeProcessingPass'`.

- [ ] **Step 3: Bind the pass**

Add the include beside `#include <donut/render/MipMapGenPass.h>` at `src/cpp/_pydonut.cpp:67`:

```cpp
#include <donut/render/LightProbeProcessingPass.h>
```

Add the class block immediately after the `MipMapGenPass` block (which ends at `:2909`):

```cpp
    // Turns a rendered environment cube map into the two maps a LightProbe samples: a diffuse
    // irradiance cube and a roughness-filtered specular cube, plus the split-sum environment
    // BRDF LUT shared by every probe (LightProbeProcessingPass.h:93-137).
    //
    // RenderDiffuseMap and RenderSpecularMap DROP their nvrhi::TextureSubresourceSet parameter
    // and pass AllSubresources internally. That type is not exposed to Python anywhere,
    // AllSubresources is what the sample passes at both call sites (FeatureDemo.cpp:1413, :1419),
    // and clearTextureFloat/clearDepthStencilTexture/resolveTexture above already fold the same
    // argument away. Adding a subresource-set type for two call sites that both want "all"
    // would be the tail wagging the dog.
    py::class_<donut::render::LightProbeProcessingPass, std::shared_ptr<donut::render::LightProbeProcessingPass>>(
        m, "LightProbeProcessingPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::ShaderFactory>,
                std::shared_ptr<donut::engine::CommonRenderPasses>, uint32_t, nvrhi::Format>(),
            py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"),
            py::arg("intermediateTextureSize") = 1024,
            py::arg("intermediateTextureFormat") = nvrhi::Format::RGBA16_FLOAT)
        // Bound for completeness; nothing in this repo calls it. The sample does not either.
        .def("BlitCubemap", &donut::render::LightProbeProcessingPass::BlitCubemap,
            py::arg("commandList"), py::arg("inCubeMap"), py::arg("inBaseArraySlice"), py::arg("inMipLevel"),
            py::arg("outCubeMap"), py::arg("outBaseArraySlice"), py::arg("outMipLevel"))
        .def("GenerateCubemapMips", &donut::render::LightProbeProcessingPass::GenerateCubemapMips,
            py::arg("commandList"), py::arg("cubeMap"), py::arg("baseArraySlice"),
            py::arg("sourceMipLevel"), py::arg("levelsToGenerate"))
        .def("RenderDiffuseMap", [](donut::render::LightProbeProcessingPass &self,
                nvrhi::ICommandList* commandList, nvrhi::ITexture* inEnvironmentMap,
                nvrhi::ITexture* outDiffuseMap, uint32_t outBaseArraySlice, uint32_t outMipLevel) {
            self.RenderDiffuseMap(commandList, inEnvironmentMap, nvrhi::AllSubresources,
                outDiffuseMap, outBaseArraySlice, outMipLevel);
        }, py::arg("commandList"), py::arg("inEnvironmentMap"),
           py::arg("outDiffuseMap"), py::arg("outBaseArraySlice"), py::arg("outMipLevel"))
        // The out-parameter is named outSpecularMap here, not outDiffuseMap as the header has it
        // (LightProbeProcessingPass.h:131) -- a copy-paste slip in donut, not a real alias.
        .def("RenderSpecularMap", [](donut::render::LightProbeProcessingPass &self,
                nvrhi::ICommandList* commandList, float roughness, nvrhi::ITexture* inEnvironmentMap,
                nvrhi::ITexture* outSpecularMap, uint32_t outBaseArraySlice, uint32_t outMipLevel) {
            self.RenderSpecularMap(commandList, roughness, inEnvironmentMap, nvrhi::AllSubresources,
                outSpecularMap, outBaseArraySlice, outMipLevel);
        }, py::arg("commandList"), py::arg("roughness"), py::arg("inEnvironmentMap"),
           py::arg("outSpecularMap"), py::arg("outBaseArraySlice"), py::arg("outMipLevel"))
        .def("RenderEnvironmentBrdfTexture", &donut::render::LightProbeProcessingPass::RenderEnvironmentBrdfTexture,
            py::arg("commandList"))
        // Raw ITexture* owned by the pass. reference (not reference_internal) matches the other
        // texture getters in this module; the caller is responsible for not outliving the pass,
        // which is why feature_demo.py disables every probe when it recreates this pass.
        .def("GetEnvironmentBrdfTexture", &donut::render::LightProbeProcessingPass::GetEnvironmentBrdfTexture,
            py::return_value_policy::reference)
        // Drops the framebuffer, PSO and binding-set caches. Correct for a caller that KEEPS the
        // pass but has invalidated what it cached. feature_demo.py's shader reload recreates the
        // pass instead -- the constructor is what compiles its five shaders.
        .def("ResetCaches", &donut::render::LightProbeProcessingPass::ResetCaches);
```

- [ ] **Step 4: Mirror in the type stubs**

In `src/pydonut/_pydonut.pyi`, after the `MipMapGenPass` class:

```python
# Turns a rendered environment cube map into the two maps a LightProbe samples -- a diffuse
# irradiance cube and a roughness-filtered specular cube -- plus the split-sum environment BRDF
# LUT shared by every probe (LightProbeProcessingPass.h:93-137).
#
# RenderDiffuseMap and RenderSpecularMap take no subresource-set argument: nvrhi::
# TextureSubresourceSet is not exposed to Python and both call sites want AllSubresources, which
# they pass internally. Same fold as clearTextureFloat and resolveTexture.
class LightProbeProcessingPass():
    def __init__(self: LightProbeProcessingPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, intermediateTextureSize: int = 1024, intermediateTextureFormat: Format = ...) -> None: ...
    # Bound for completeness; nothing in this repo calls it.
    def BlitCubemap(self: LightProbeProcessingPass, commandList: CommandList, inCubeMap: Texture, inBaseArraySlice: int, inMipLevel: int, outCubeMap: Texture, outBaseArraySlice: int, outMipLevel: int) -> None: ...
    def GenerateCubemapMips(self: LightProbeProcessingPass, commandList: CommandList, cubeMap: Texture, baseArraySlice: int, sourceMipLevel: int, levelsToGenerate: int) -> None: ...
    def RenderDiffuseMap(self: LightProbeProcessingPass, commandList: CommandList, inEnvironmentMap: Texture, outDiffuseMap: Texture, outBaseArraySlice: int, outMipLevel: int) -> None: ...
    # roughness precedes the source map, as in C++. The caller loops the specular mip chain,
    # computing roughness per level.
    def RenderSpecularMap(self: LightProbeProcessingPass, commandList: CommandList, roughness: float, inEnvironmentMap: Texture, outSpecularMap: Texture, outBaseArraySlice: int, outMipLevel: int) -> None: ...
    def RenderEnvironmentBrdfTexture(self: LightProbeProcessingPass, commandList: CommandList) -> None: ...
    # Owned by the pass -- it dies with the pass, which is why recreating the pass means
    # invalidating every probe holding this handle as its environmentBrdf.
    def GetEnvironmentBrdfTexture(self: LightProbeProcessingPass) -> Texture: ...
    def ResetCaches(self: LightProbeProcessingPass) -> None: ...
```

- [ ] **Step 5: Re-export it**

In `src/pydonut/__init__.py`, beside the `MipMapGenPass` import (`:174`) and in `__all__` (`:372`):

```python
from pydonut._pydonut import LightProbeProcessingPass
```

```python
    'LightProbeProcessingPass',
```

- [ ] **Step 6: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`

Expected: 123 passed (116 + 7 new).

- [ ] **Step 7: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_lightprobe_bindings.py
git commit -m "Bind LightProbeProcessingPass

All seven methods, with one shape change: RenderDiffuseMap and
RenderSpecularMap drop their nvrhi::TextureSubresourceSet parameter and
pass AllSubresources internally. That type is exposed nowhere in this
project, AllSubresources is what both call sites in the sample pass, and
clearTextureFloat/clearDepthStencilTexture/resolveTexture already fold
the same argument away.

RenderSpecularMap's target is named outSpecularMap; donut's header calls
it outDiffuseMap, which is a copy-paste slip."
```

---

## Task 3: Supporting bindings

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (`CubemapView` at `:3499-3517`; `CascadedShadowMap` at `:3003-3010` and `:3041-3058`; `ForwardShadingPassCreateParameters`; `BaseCamera` at `:3202-3212`; `SwitchableCamera` at `:3296-3306`; `SceneCamera` at `:2380-2386`)
- Modify: `src/pydonut/_pydonut.pyi`
- Test: `test/test_lightprobe_bindings.py` (append)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces, for Tasks 5–6: `CubemapView.SetTransformFromPosition(x, y, z, zNear, cullDistance, useReverseInfiniteProjections=True) -> None`; `CascadedShadowMap.SetupForCubemapView(light, view: IView, maxShadowDistance, lightSpaceZUp, lightSpaceZDown, exponent=4.0) -> bool`; `ForwardShadingPassCreateParameters.singlePassCubemap: bool`; `BaseCamera.GetPosition() -> tuple[float, float, float]`; `SwitchableCamera.GetActiveUserCamera() -> BaseCamera`; `SceneCamera.GetPosition() -> tuple[float, float, float]`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_lightprobe_bindings.py`:

```python
def test_cubemap_view_set_transform_from_position_defaults_the_projection_flag() -> None:
    # C++ SetTransform takes a dm::affine3 (View.h:361), which cannot cross into Python, and the
    # only affine3 the sample ever builds for it is dm::translation(-probePosition)
    # (FeatureDemo.cpp:1353). So the binding takes the position and builds the matrix itself,
    # named to sit beside the existing SetTransformFromCamera.
    doc = pyd.CubemapView.SetTransformFromPosition.__doc__
    assert doc is not None
    assert "useReverseInfiniteProjections: bool = True" in doc
    assert "affine3" not in doc


def test_cubemap_view_set_transform_from_position_moves_the_faces() -> None:
    # Behavioural, not a doc check: CubemapView is constructible without a device, and its faces
    # are PlanarViews, which expose FillPlanarViewConstants(). Two different probe positions must
    # therefore produce different face constants -- that is what proves the position reaches the
    # matrix rather than being dropped.
    near = pyd.CubemapView()
    near.SetArrayViewports(256, 0)
    near.SetTransformFromPosition(0.0, 0.0, 0.0, 0.1, 100.0)
    near.UpdateCache()

    far = pyd.CubemapView()
    far.SetArrayViewports(256, 0)
    far.SetTransformFromPosition(10.0, 5.0, -3.0, 0.1, 100.0)
    far.UpdateCache()

    assert near.GetFaceView(0).FillPlanarViewConstants() != far.GetFaceView(0).FillPlanarViewConstants()


def test_cubemap_view_still_takes_a_camera() -> None:
    # Regression: SetTransformFromPosition is an addition, not a replacement.
    # threaded_rendering.py drives the camera form.
    assert hasattr(pyd.CubemapView, "SetTransformFromCamera")


def test_setup_for_cubemap_view_takes_a_view_not_a_centre() -> None:
    # C++ takes a dm::float3 centre (CascadedShadowMap.h:79-85) and the sample passes
    # view.GetViewOrigin(). Rather than bind GetViewOrigin and round-trip three floats, the
    # binding takes the view and reads the origin off it -- deliberately the same shape as the
    # already-bound SetupForPlanarView(light, view, ...), which likewise extracts what it needs
    # internally. GetViewOrigin is pure virtual on IView (View.h:69), so any view type works.
    doc = pyd.CascadedShadowMap.SetupForCubemapView.__doc__
    assert doc is not None
    assert "view: donut::engine::IView" in doc
    assert "exponent: typing.SupportsFloat | typing.SupportsIndex = 4.0" in doc
    assert "center" not in doc
    assert "float3" not in doc


def test_single_pass_cubemap_defaults_off_and_round_trips() -> None:
    # The sample sets this from queryFeatureSupport(FastGeometryShader)
    # (FeatureDemo.cpp:1379). Default False matters: the app's own forward pass must stay
    # six-pass, and only the throwaway pass built per probe capture opts in.
    params = pyd.ForwardShadingPassCreateParameters()
    assert params.singlePassCubemap is False
    params.singlePassCubemap = True
    assert params.singlePassCubemap is True


def test_base_camera_reports_its_position() -> None:
    # Flat 3-tuple, matching the GetDir/GetUp already on this class -- math types never cross
    # into Python. Needed because a probe captures at the active camera's position.
    camera = pyd.FirstPersonCamera()
    camera.LookAt(1.0, 2.0, 3.0, 1.0, 2.0, 4.0)
    assert camera.GetPosition() == (1.0, 2.0, 3.0)


def test_get_active_user_camera_returns_the_owned_camera() -> None:
    # A reference to the camera the SwitchableCamera owns, not a copy: writes through it must
    # stick, the same guarantee GetFirstPersonCamera already documents.
    switchable = pyd.SwitchableCamera()
    switchable.SwitchToFirstPerson(copyView=False)
    active = switchable.GetActiveUserCamera()
    active.SetMoveSpeed(7.5)
    assert switchable.GetActiveUserCamera().GetPosition() == active.GetPosition()


def test_get_active_user_camera_follows_the_switch() -> None:
    # Two cameras at distinguishable positions, so the switch is observable through GetPosition.
    switchable = pyd.SwitchableCamera()
    switchable.SwitchToFirstPerson(copyView=False)
    switchable.GetFirstPersonCamera().LookAt(1.0, 0.0, 0.0, 2.0, 0.0, 0.0)
    switchable.GetThirdPersonCamera().SetTargetPosition(50.0, 50.0, 50.0)
    switchable.GetThirdPersonCamera().SetDistance(1.0)
    switchable.GetThirdPersonCamera().Animate(0.0)

    assert switchable.GetActiveUserCamera().GetPosition() == (1.0, 0.0, 0.0)
    switchable.SwitchToThirdPerson(copyView=False)
    assert switchable.GetActiveUserCamera().GetPosition() != (1.0, 0.0, 0.0)


def _graph_with_root() -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Returns a fresh graph and its real root node.

    Copied from test_camera_bindings.py's helper of the same name. SetRootNode returns the
    *previous* root (SceneGraph.cpp:670-679) -- None on a fresh graph -- so the root has to be
    read back with GetRootNode(); passing SetRootNode's result as AttachLeafNode's parent
    silently re-roots the graph on every attach instead of adding siblings.
    """
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    return graph, graph.GetRootNode()


def test_scene_camera_reports_its_world_position() -> None:
    # A scene camera's position comes from its node's transform, so it needs an attached node.
    # AttachLeafNode takes the leaf and creates the wrapping node itself.
    graph, root = _graph_with_root()
    camera = pyd.PerspectiveCamera()
    node = graph.AttachLeafNode(root, camera)
    node.SetPositionAndDirection(-8.0, 2.0, 5.0, 1.0, 0.0, 0.0)

    x, y, z = camera.GetPosition()
    assert (round(x, 4), round(y, 4), round(z, 4)) == (-8.0, 2.0, 5.0)


def test_scene_camera_position_is_not_the_world_to_view_translation() -> None:
    # THE test for this task's one deliberate correction. The sample reads
    # GetWorldToViewMatrix().m_translation (FeatureDemo.cpp:1351), which is -R*p, not p. For an
    # axis-aligned camera the two happen to differ only in sign; for a ROTATED one they are
    # unrelated. These are Sponza's own Gallery camera placement, which is rotated, so a binding
    # built on the world-to-view translation cannot produce the node's own position.
    graph, root = _graph_with_root()
    camera = pyd.PerspectiveCamera()
    node = graph.AttachLeafNode(root, camera)
    node.SetPositionAndDirection(0.0, 8.0, -4.0, 0.0, -0.4, 1.0)

    x, y, z = camera.GetPosition()
    assert (round(x, 4), round(y, 4), round(z, 4)) == (0.0, 8.0, -4.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest test/test_lightprobe_bindings.py -q`

Expected: 18 passed, 10 failed — missing `SetTransformFromPosition`, `SetupForCubemapView`, `singlePassCubemap`, `GetPosition`, `GetActiveUserCamera`.

- [ ] **Step 3: Bind `CubemapView.SetTransformFromPosition`**

In `src/cpp/_pydonut.cpp`, after the `SetTransformFromCamera` def at `:3504-3507`:

```cpp
    // The probe-capture form. CubemapView::SetTransform takes a dm::affine3 (View.h:361), and
    // the only affine3 the sample ever builds for it is a pure negated translation
    // (FeatureDemo.cpp:1353) -- so take the position and build the matrix here, exactly as
    // SetTransformFromCamera takes the camera and fetches its matrix here.
    cubemapView.def("SetTransformFromPosition", [](donut::engine::CubemapView &self,
            float x, float y, float z, float zNear, float cullDistance,
            bool useReverseInfiniteProjections) {
        self.SetTransform(donut::math::translation(-donut::math::float3(x, y, z)),
            zNear, cullDistance, useReverseInfiniteProjections);
    }, py::arg("x"), py::arg("y"), py::arg("z"), py::arg("zNear"), py::arg("cullDistance"),
       py::arg("useReverseInfiniteProjections") = true);
```

- [ ] **Step 4: Bind `CascadedShadowMap.SetupForCubemapView`**

In `src/cpp/_pydonut.cpp`, add after the `SetupForPlanarViewStable` def (ends `:3058`):

```cpp
        // Cascades all centred on one point, for an omnidirectional view. Takes the VIEW rather
        // than the dm::float3 centre the C++ wants (CascadedShadowMap.h:79-85) and reads
        // GetViewOrigin() off it -- the same shape as the two planar variants above, which
        // likewise take an IView and extract the frustum data internally. GetViewOrigin is pure
        // virtual on IView (View.h:69), so this is not CubemapView-specific.
        //
        // numberOfCascades stays unbound, as it does on both planar variants.
        .def("SetupForCubemapView", [](donut::render::CascadedShadowMap &self,
                const donut::engine::DirectionalLight &light, const donut::engine::IView &view,
                float maxShadowDistance, float lightSpaceZUp, float lightSpaceZDown, float exponent) {
            RequireCascadeExponent("SetupForCubemapView", exponent);
            return self.SetupForCubemapView(light, view.GetViewOrigin(), maxShadowDistance,
                lightSpaceZUp, lightSpaceZDown, exponent);
        }, py::arg("light"), py::arg("view"), py::arg("maxShadowDistance"),
            py::arg("lightSpaceZUp"), py::arg("lightSpaceZDown"), py::arg("exponent") = 4.0f)
```

Update the "Skipped" comment at `:3003-3010` — it currently says `SetupForCubemapView` is skipped. Replace its first sentence with:

```cpp
    // Skipped: SetupPerObjectShadow (it needs the per-object shadow slices a later stage would
    // bind), SetupProxyViews, GetPerObjectView, and SetNumberOfCascadesUnsafe -- that setter
```

- [ ] **Step 5: Bind `singlePassCubemap`**

In `src/cpp/_pydonut.cpp`, in the `ForwardShadingPassCreateParameters` class block (just above `:2717`):

```cpp
        // Renders all six cube faces in one pass using a fast geometry shader instead of six
        // draws. Only meaningful when the device reports Feature::FastGeometryShader; the sample
        // gates it exactly that way (FeatureDemo.cpp:1379). Default false -- the app's own
        // forward pass targets the back buffer and must stay six-pass; only the throwaway pass
        // built per probe capture opts in.
        .def_readwrite("singlePassCubemap", &donut::render::ForwardShadingPass::CreateParameters::singlePassCubemap)
```

- [ ] **Step 6: Bind the three camera accessors**

`BaseCamera.GetPosition`, in the class block at `src/cpp/_pydonut.cpp:3202-3212`, after `GetUp`:

```cpp
        // (x, y, z) -- math types aren't exposed to Python, same as GetDir/GetUp above. A light
        // probe captures at the active camera's position, which is the only caller.
        .def("GetPosition", [](const donut::app::BaseCamera &self) {
            const donut::math::float3 &p = self.GetPosition();
            return py::make_tuple(p.x, p.y, p.z);
        })
```

`SwitchableCamera.GetActiveUserCamera`, appended to that class block (before the trailing `;` on the `Animate` def at `:3302`):

```cpp
        // Returns the first- or third-person camera the SwitchableCamera owns, whichever is
        // active -- a live reference, not a copy, same guarantee as GetFirstPersonCamera.
        // reference_internal keeps the owner alive for as long as Python holds the camera.
        //
        // Returns the last-active USER camera even when a scene camera is active; callers that
        // care check IsSceneCameraActive() first, as feature_demo.py's probe capture does.
        .def("GetActiveUserCamera", [](donut::app::SwitchableCamera &self) -> donut::app::BaseCamera* {
            return self.GetActiveUserCamera();
        }, py::return_value_policy::reference_internal)
```

Then update the trailing comment at `:3303-3306` so it no longer claims `GetActiveUserCamera` is unbound:

```cpp
    // GetWorldToViewMatrix stays unbound: it returns a matrix, which
    // SetMatricesFromSwitchableCamera consumes in C++. JoystickUpdate and JoystickButtonUpdate
    // stay unbound -- no example handles joystick input.
```

`SceneCamera.GetPosition`, replacing the empty class registration at `:2380-2386`:

```cpp
    // GetViewToWorldMatrix and GetWorldToViewMatrix stay unbound: both return dm::affine3,
    // which SwitchableCamera consumes internally (see SetMatricesFromSwitchableCamera).
    // GetPosition below is the one thing Python needs off them.
    py::class_<donut::engine::SceneCamera, donut::engine::SceneGraphLeaf,
               std::shared_ptr<donut::engine::SceneCamera>>(m, "SceneCamera")
        // The camera's WORLD position, from the view-to-world translation.
        //
        // NOTE this deliberately differs from FeatureDemo.cpp:1351, which reads
        // GetWorldToViewMatrix().m_translation for the same purpose. That is -R*p, not p: for
        // any camera with a non-identity rotation it is not the camera's position, and Sponza's
        // Gallery camera is rotated. Reading the view-to-world translation gives the real one.
        .def("GetPosition", [](const donut::engine::SceneCamera &self) {
            const donut::math::float3 p = self.GetViewToWorldMatrix().m_translation;
            return py::make_tuple(p.x, p.y, p.z);
        });
```

- [ ] **Step 7: Mirror all six in the type stubs**

In `src/pydonut/_pydonut.pyi`:

```python
# --- class BaseCamera, after GetUp ---
    # (x, y, z) -- math types aren't exposed to Python. A light probe captures at the active
    # camera's position.
    def GetPosition(self: BaseCamera) -> tuple[float, float, float]: ...

# --- class SwitchableCamera, after Animate ---
    # The owned first- or third-person camera, whichever is active -- a live reference, not a
    # copy. Returns the last-active USER camera even when a scene camera is active; check
    # IsSceneCameraActive() first if that matters.
    def GetActiveUserCamera(self: SwitchableCamera) -> BaseCamera: ...

# --- class SceneCamera ---
    # The camera's WORLD position, taken from the view-to-world translation. FeatureDemo.cpp:1351
    # reads the world-to-VIEW translation for the same purpose, which is -R*p and therefore wrong
    # for any rotated camera; this is the deliberate correction.
    def GetPosition(self: SceneCamera) -> tuple[float, float, float]: ...

# --- class CubemapView, after SetTransformFromCamera ---
    # The probe-capture form: builds dm::translation(-position) internally, since CubemapView.
    # SetTransform takes a dm::affine3 and the only one the caller ever wants is that.
    def SetTransformFromPosition(self: CubemapView, x: float, y: float, z: float, zNear: float, cullDistance: float, useReverseInfiniteProjections: bool = True) -> None: ...

# --- class ForwardShadingPassCreateParameters ---
    # Renders all six cube faces in one geometry-shader pass instead of six draws. Only
    # meaningful when the device reports Feature.FastGeometryShader.
    singlePassCubemap: bool

# --- class CascadedShadowMap, after SetupForPlanarViewStable ---
    # Cascades all centred on one point, for an omnidirectional view. Takes the view rather than
    # a centre and reads GetViewOrigin() off it, matching the two planar variants above.
    def SetupForCubemapView(self: CascadedShadowMap, light: DirectionalLight, view: IView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
```

Also update the comment block at `_pydonut.pyi:1676-1678` if it names `SetupForCubemapView` as unbound.

- [ ] **Step 8: Rebuild and run the tests**

Run: `uv sync && uv run pytest -q`

Expected: 133 passed (123 + 10 new).

- [ ] **Step 9: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi test/test_lightprobe_bindings.py
git commit -m "Bind the six accessors a light-probe capture needs

CubemapView.SetTransformFromPosition and CascadedShadowMap.
SetupForCubemapView both take the scalars/view the caller has and build
the dm::affine3 / read the dm::float3 in C++, matching how
SetTransformFromCamera and SetupForPlanarView already handle the same
problem.

SceneCamera.GetPosition deliberately differs from FeatureDemo.cpp:1351,
which reads the world-to-view translation. That is -R*p, not p, and is
wrong for any rotated camera -- Sponza's Gallery camera among them. This
reads the view-to-world translation instead, and a test with a rotated
camera pins the difference."
```

---

## Task 4: `feature_demo.py` — probe allocation

**Files:**
- Modify: `feature_demo.py` (`UIData.__init__`; `FeatureDemo.__init__`; `FeatureDemo.Init`; new `CreateLightProbes`; new module constants)

**Interfaces:**
- Consumes: Task 1's `pyd.LightProbe`; Task 2's `pyd.LightProbeProcessingPass`.
- Produces, for Tasks 5–7: `self.lightProbes: list[pyd.LightProbe]`, `self.lightProbePass: pyd.LightProbeProcessingPass | None`, `self.lightProbeDiffuseTexture`, `self.lightProbeSpecularTexture`, and `ui.EnableLightProbe` / `ui.LightProbeDiffuseScale` / `ui.LightProbeSpecularScale`.

- [ ] **Step 1: Add the module constants**

In `feature_demo.py`, after `SHADOW_LIGHT_SPACE_Z_DOWN` (`:90`):

```python
    # The light probes this example adds. All four share one diffuse and one specular cube-map
    # ARRAY, indexed by slice -- not a private texture pair each. That is load-bearing:
    # DeferredLightingPass logs an error and returns *without rendering the frame* if two
    # submitted probes present different maps (DeferredLightingPass.cpp:246-253), the same
    # failure mode CreateSceneLights documents for two lights with different shadow maps.
    #
    # Sizes and mip counts from FeatureDemo.cpp:1252-1256. The specular chain's 8 levels are
    # the roughness axis: RenderLightProbe filters one level per roughness step.
    LIGHT_PROBE_COUNT = 4
    LIGHT_PROBE_DIFFUSE_SIZE = 256
    LIGHT_PROBE_DIFFUSE_MIPS = 1
    LIGHT_PROBE_SPECULAR_SIZE = 512
    LIGHT_PROBE_SPECULAR_MIPS = 8
```

- [ ] **Step 2: Add the UI fields**

In `UIData.__init__`, after `self.Stereo = False` (`:187`):

```python
            # Light probes. The two scales are pushed onto every enabled probe each frame in
            # Render -- LightProbe::FillLightProbeConstants reads them off the struct, so the UI
            # has no other route to them.
            self.EnableLightProbe = True
            self.LightProbeDiffuseScale = 1.0
            self.LightProbeSpecularScale = 1.0
```

- [ ] **Step 3: Add the app fields**

In `FeatureDemo.__init__`, after `self.mipMapGenPass = None` (`:354`):

```python
            self.lightProbePass: pyd.LightProbeProcessingPass | None = None
            self.lightProbes: list[pyd.LightProbe] = []
            # Held so the shared arrays outlive the probes that index into them: LightProbe's
            # diffuseMap/specularMap are nvrhi handles, but nothing else on the Python side
            # keeps a reference.
            self.lightProbeDiffuseTexture: pyd.Texture | None = None
            self.lightProbeSpecularTexture: pyd.Texture | None = None
```

- [ ] **Step 4: Write `CreateLightProbes`**

Add this method to `FeatureDemo`, after `CreateShadowMap` (which ends `:685`):

```python
        def CreateLightProbes(self: FeatureDemo, numProbes: int) -> None:
            """Allocates the two shared cube-map arrays and the probes that index into them.

            Ports FeatureDemo.cpp:1249-1299. One diffuse array and one specular array serve every
            probe, sliced by index -- see LIGHT_PROBE_COUNT's comment for why that sharing is
            required rather than merely economical.

            Every probe starts disabled AND with empty bounds. Either alone would be enough to
            keep it out of the lighting passes (LightProbe::IsActive checks both,
            SceneTypes.cpp:379-389); both are set because a probe with no captured content in its
            slices must not light anything, and RenderLightProbe is what flips both back.
            """
            device = self.GetDevice()

            def makeCubemapArray(size: int, mipLevels: int, name: str) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = size
                desc.height = size
                desc.mipLevels = mipLevels
                desc.arraySize = 6 * numProbes
                desc.dimension = pyd.TextureDimension.TextureCubeArray
                desc.isRenderTarget = True
                desc.format = pyd.Format.RGBA16_FLOAT
                # ShaderResource, not RenderTarget: these are only ever written by
                # LightProbeProcessingPass and read by the lighting passes.
                desc.initialState = pyd.ResourceStates.ShaderResource
                desc.keepInitialState = True
                desc.debugName = name
                return device.createTexture(desc)

            self.lightProbeDiffuseTexture = makeCubemapArray(
                LIGHT_PROBE_DIFFUSE_SIZE, LIGHT_PROBE_DIFFUSE_MIPS, "LightProbeDiffuse"
            )
            self.lightProbeSpecularTexture = makeCubemapArray(
                LIGHT_PROBE_SPECULAR_SIZE, LIGHT_PROBE_SPECULAR_MIPS, "LightProbeSpecular"
            )

            self.lightProbes = []
            for index in range(numProbes):
                probe = pyd.LightProbe()
                # The UI labels each button with this, so it is "1".."4", not a zero-based index.
                probe.name = str(index + 1)
                probe.diffuseMap = self.lightProbeDiffuseTexture
                probe.specularMap = self.lightProbeSpecularTexture
                probe.diffuseArrayIndex = index
                probe.specularArrayIndex = index
                probe.SetBoundsEmpty()
                probe.enabled = False
                self.lightProbes.append(probe)
```

- [ ] **Step 5: Create the pass and the probes in `Init`**

In `FeatureDemo.Init`, after `self.CreateShadowMap()` (`:454`):

```python
            # Size-independent, like the geometry passes above: it holds shaders and an
            # intermediate texture of its own, not anything sized to the back buffer, so it
            # belongs here rather than in CreateRenderPasses. (The C++ sample builds it in
            # CreateRenderPasses, FeatureDemo.cpp:830.)
            self.lightProbePass = pyd.LightProbeProcessingPass(
                device, self.shaderFactory, self.m_CommonPasses
            )
            self.CreateLightProbes(LIGHT_PROBE_COUNT)
```

- [ ] **Step 6: Verify the module still imports and the suite is unchanged**

Run: `uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('feature_demo.py').read_text()); print('parsed')" && uv run pytest -q`

Expected: `parsed`, then 133 passed. `feature_demo.py` guards its body behind `if __name__ == "__main__":`, so importing it runs nothing — the parse check is the static gate, and the manual run in Task 7 is the real one.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Allocate the light probes and their processing pass

One diffuse and one specular cube-map array serve all four probes,
indexed by slice. That sharing is required, not economical:
DeferredLightingPass returns without rendering the frame if two
submitted probes carry different maps.

Every probe starts disabled and with empty bounds -- either alone keeps
it out of the lighting passes, and RenderLightProbe flips both."
```

---

## Task 5: `feature_demo.py` — `RenderLightProbe`

**Files:**
- Modify: `feature_demo.py` (new `RenderLightProbe` method; new module constants)

**Interfaces:**
- Consumes: Task 4's `self.lightProbePass` and `self.lightProbes`; Task 2's pass methods; Task 3's `SetTransformFromPosition`, `SetupForCubemapView`, `singlePassCubemap`, `GetPosition`, `GetActiveUserCamera`.
- Produces, for Task 7: `FeatureDemo.RenderLightProbe(probe: pyd.LightProbe) -> None`.

- [ ] **Step 1: Add the capture constants**

In `feature_demo.py`, after the `LIGHT_PROBE_*` constants from Task 4:

```python
    # The throwaway environment cube map each capture renders into, before it is filtered down
    # into the probe's array slices (FeatureDemo.cpp:1304-1305). Bigger than either output: the
    # filtering reduces it.
    LIGHT_PROBE_ENVIRONMENT_SIZE = 1024
    LIGHT_PROBE_ENVIRONMENT_MIPS = 8
    # Near plane and far cull distance for the capture's six face views, and the half-extent of
    # the box the probe's bounds are built from (FeatureDemo.cpp:1347-1348, :1430).
    LIGHT_PROBE_Z_NEAR = 0.1
    LIGHT_PROBE_CULL_DISTANCE = 100.0
    LIGHT_PROBE_BOUNDS_EXTENT = 10.0
```

- [ ] **Step 2: Write `RenderLightProbe`**

Add to `FeatureDemo`, after `CreateLightProbes`:

```python
        def RenderLightProbe(self: FeatureDemo, probe: pyd.LightProbe) -> None:
            """Captures the scene into `probe` from the active camera's position.

            Ports FeatureDemo.cpp:1301-1433. Stands up a throwaway render graph -- its own
            cube-map colour and depth targets, framebuffer, view, sky pass, forward pass and
            command list -- renders one omnidirectional frame, filters it into the probe's array
            slices, and tears the whole thing down again.

            Called DIRECTLY from the UI button handler, not through a flag like the screenshot.
            Two things make that safe, and they are worth stating because the screenshot's
            deferred path invites the opposite assumption:

              * ImGui_Renderer::Render calls buildUI() BEFORE it opens its own command list
                (imgui_renderer.cpp:360-367), and this app's Render has already closed and
                executed its own by then -- no command list is open on the immediate context.
              * This method creates, executes and drains its own command list, so it needs
                nothing from the caller's frame.

            The screenshot needs a flag only because it must run at one specific point inside
            Render, after executeCommandList, with the back buffer in hand. A capture has no
            such constraint, so a flag would buy nothing and cost a frame of latency.
            """
            assert self.scene is not None and self.sunLight is not None
            assert self.lightProbePass is not None
            device = self.GetDevice()

            # The environment map this capture renders into. Discarded at the end of the method;
            # only its filtered reduction survives, in the probe's array slices.
            colorDesc = pyd.TextureDesc()
            colorDesc.width = LIGHT_PROBE_ENVIRONMENT_SIZE
            colorDesc.height = LIGHT_PROBE_ENVIRONMENT_SIZE
            colorDesc.mipLevels = LIGHT_PROBE_ENVIRONMENT_MIPS
            colorDesc.arraySize = 6
            colorDesc.dimension = pyd.TextureDimension.TextureCube
            colorDesc.isRenderTarget = True
            colorDesc.format = pyd.Format.RGBA16_FLOAT
            colorDesc.initialState = pyd.ResourceStates.RenderTarget
            colorDesc.keepInitialState = True
            colorDesc.useClearValue = True
            colorDesc.clearValue = pyd.Color(0.0)
            colorDesc.debugName = "LightProbeEnvironment"
            colorTexture = device.createTexture(colorDesc)

            # D32 rather than the sample's nvrhi::utils::ChooseFormat over
            # {D24S8, D32, D16, D32S8} (FeatureDemo.cpp:1384-1395). D32 is in that candidate
            # list, is universally supported, and is already what CreateShadowMap uses -- binding
            # ChooseFormat plus the FormatSupport flag enum to reach a format we can name
            # directly is not worth it. Consequence: there is never a stencil aspect, so the
            # clear below passes clearStencil=False rather than computing it.
            depthDesc = pyd.TextureDesc()
            depthDesc.width = LIGHT_PROBE_ENVIRONMENT_SIZE
            depthDesc.height = LIGHT_PROBE_ENVIRONMENT_SIZE
            depthDesc.mipLevels = 1
            depthDesc.arraySize = 6
            depthDesc.dimension = pyd.TextureDimension.TextureCube
            depthDesc.isRenderTarget = True
            depthDesc.format = pyd.Format.D32
            depthDesc.initialState = pyd.ResourceStates.DepthWrite
            depthDesc.keepInitialState = True
            depthDesc.debugName = "LightProbeDepth"
            depthTexture = device.createTexture(depthDesc)

            framebuffer = pyd.FramebufferFactory(device)
            framebuffer.SetRenderTargets([colorTexture])
            framebuffer.depthTarget = depthTexture

            # The probe sits wherever the camera is. A scene camera's position comes off its
            # node; a user camera's off the camera itself.
            if self.camera.IsSceneCameraActive():
                probeX, probeY, probeZ = self.camera.GetSceneCamera().GetPosition()
            else:
                probeX, probeY, probeZ = self.camera.GetActiveUserCamera().GetPosition()

            view = pyd.CubemapView()
            view.SetArrayViewports(LIGHT_PROBE_ENVIRONMENT_SIZE, 0)
            view.SetTransformFromPosition(
                probeX, probeY, probeZ, LIGHT_PROBE_Z_NEAR, LIGHT_PROBE_CULL_DISTANCE
            )
            view.UpdateCache()

            skyPass = pyd.SkyPass(
                device, self.shaderFactory, self.m_CommonPasses, framebuffer, view
            )

            # A fresh forward pass rather than self.forwardPass, and this is not an oversight:
            # the app's pass has singlePassCubemap False and caches its pipelines against the
            # back buffer's FramebufferInfo, neither of which suits a cube-map target. This runs
            # on a button press, so two pass constructions cost nothing.
            forwardParams = pyd.ForwardShadingPassCreateParameters()
            forwardParams.singlePassCubemap = device.queryFeatureSupport(
                pyd.Feature.FastGeometryShader
            )
            forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
            forwardPass.Init(self.shaderFactory, forwardParams)

            commandList = device.createCommandList()
            commandList.open()
            commandList.clearTextureFloat(colorTexture, pyd.Color(0.0))
            # clearDepth=True, depth=0.0: reverse-Z, as everywhere else in this file.
            # clearStencil=False -- D32 has no stencil aspect, see the format comment above.
            commandList.clearDepthStencilTexture(depthTexture, True, 0.0, False, 0)

            # Refit the cascades around the probe rather than around the camera frustum. This
            # CLOBBERS the fit the current frame's RenderShadowMap made -- harmless, because
            # RenderShadowMap refits from scratch at the top of every Render, so the damage
            # lasts until the next frame begins. The sample behaves identically.
            minX, minY, minZ, maxX, maxY, maxZ = (
                self.scene.GetSceneGraph().GetRootNode().GetGlobalBoundingBox()
            )
            dx, dy, dz = maxX - minX, maxY - minY, maxZ - minZ
            zRange = math.sqrt(dx * dx + dy * dy + dz * dz) * 0.5
            self.shadowMap.SetupForCubemapView(
                self.sunLight,
                view,
                LIGHT_PROBE_CULL_DISTANCE,
                zRange,
                zRange,
                self.ui.ShadowExponent,
            )
            self.shadowMap.Clear(commandList)

            shadowContext = pyd.DepthPassContext()
            pyd.RenderCompositeView(
                commandList,
                self.shadowMap.GetView(),
                None,
                self.shadowFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                self.depthPass,
                shadowContext,
                self.ui.EnableMaterialEvents,
                "ShadowMap",
            )

            forwardContext = pyd.ForwardShadingPassContext()
            # An EMPTY probe list, deliberately: a probe capture must not be lit by other
            # probes, or probes would feed back into each other (FeatureDemo.cpp:1388-1389).
            ambient = self.ui.AmbientIntensity
            forwardPass.PrepareLights(
                forwardContext,
                commandList,
                self.scene.GetSceneGraph().GetLights(),
                ambient * 0.2, ambient * 0.2, ambient * 0.2,
                ambient * 0.1, ambient * 0.1, ambient * 0.1,
                [],
            )

            # viewPrev is None throughout: a one-off capture has no history, and nothing here
            # reads motion vectors.
            pyd.RenderCompositeView(
                commandList,
                view,
                None,
                framebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                forwardPass,
                forwardContext,
                self.ui.EnableMaterialEvents,
                "ForwardOpaque",
            )

            skyPass.Render(commandList, view, self.sunLight, self.ui.SkyParams)

            pyd.RenderCompositeView(
                commandList,
                view,
                None,
                framebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.transparentDrawStrategy,
                forwardPass,
                forwardContext,
                self.ui.EnableMaterialEvents,
                "ForwardTransparent",
            )

            # levelsToGenerate is mips - 1: level 0 is the rendered image, the rest are reduced
            # from it.
            self.lightProbePass.GenerateCubemapMips(
                commandList, colorTexture, 0, 0, LIGHT_PROBE_ENVIRONMENT_MIPS - 1
            )

            # * 6 on both array indices: a cube "slice" is six faces.
            self.lightProbePass.RenderDiffuseMap(
                commandList, colorTexture, probe.diffuseMap, probe.diffuseArrayIndex * 6, 0
            )

            # One specular mip per roughness step, squared so the low-roughness levels get the
            # resolution (FeatureDemo.cpp:1416-1420).
            for mipLevel in range(LIGHT_PROBE_SPECULAR_MIPS):
                roughness = (mipLevel / (LIGHT_PROBE_SPECULAR_MIPS - 1)) ** 2.0
                self.lightProbePass.RenderSpecularMap(
                    commandList,
                    roughness,
                    colorTexture,
                    probe.specularMap,
                    probe.specularArrayIndex * 6,
                    mipLevel,
                )

            self.lightProbePass.RenderEnvironmentBrdfTexture(commandList)

            commandList.close()
            device.executeCommandList(commandList)
            # Both are the sample's (FeatureDemo.cpp:1426-1427). The wait is what makes the
            # capture synchronous with the button press; the collection retires the throwaway
            # colour, depth and framebuffer objects now rather than at some later frame.
            device.waitForIdle()
            device.runGarbageCollection()

            probe.environmentBrdf = self.lightProbePass.GetEnvironmentBrdfTexture()
            # Bounds must become non-empty or IsActive() stays false and the probe lights
            # nothing, whatever `enabled` says.
            probe.SetBoundsFromBox(
                probeX - LIGHT_PROBE_BOUNDS_EXTENT,
                probeY - LIGHT_PROBE_BOUNDS_EXTENT,
                probeZ - LIGHT_PROBE_BOUNDS_EXTENT,
                probeX + LIGHT_PROBE_BOUNDS_EXTENT,
                probeY + LIGHT_PROBE_BOUNDS_EXTENT,
                probeZ + LIGHT_PROBE_BOUNDS_EXTENT,
            )
            probe.enabled = True
```

- [ ] **Step 3: Confirm the `RenderCompositeView` argument order**

The bound signature is, verbatim:

```
RenderCompositeView(commandList, view, viewPrev, framebufferFactory, rootNode,
                    drawStrategy, pass, passContext, materialEvents=False, passEvent=None)
```

All four calls in Step 2 match it. Re-read them against this line before running — a positional error here is silent, and the existing call sites at `feature_demo.py:717-728` (shadow, passing `"ShadowMap"`) and `:1278-1288` (G-buffer, omitting the name) are the working references.

Run: `uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('feature_demo.py').read_text()); print('parsed')"`

Expected: `parsed`.

- [ ] **Step 4: Run the suite**

Run: `uv run pytest -q`

Expected: 133 passed, unchanged — this task adds no tests. `RenderLightProbe` needs a GPU and cannot be exercised headless; Task 7's manual run is its gate.

- [ ] **Step 5: Commit**

```bash
git add feature_demo.py
git commit -m "Add RenderLightProbe

Stands up a throwaway cube-map render graph, captures one
omnidirectional frame at the active camera's position, and filters it
into the probe's array slices.

Called directly from the UI button rather than through a flag: buildUI
runs before ImGui_Renderer opens its command list and this method drives
its own, so there is nothing for a flag to buy. The screenshot needs one
only because it must run at a specific point inside Render.

The depth cube is D32 rather than the sample's ChooseFormat pick -- D32
is in its candidate list and is what CreateShadowMap already uses, so
binding ChooseFormat plus the FormatSupport enum earns nothing."
```

---

## Task 6: `feature_demo.py` — per-frame plumbing and shader reload

**Files:**
- Modify: `feature_demo.py` (`Render` at `:1252-1341`; `ReloadShaders` at `:555-611`)

**Interfaces:**
- Consumes: Tasks 1, 4 and 5.
- Produces: nothing new; Task 7 only adds UI over this.

- [ ] **Step 1: Build the probe list in `Render`**

In `FeatureDemo.Render`, immediately before `self.renderTargets.Clear(self.commandList)` (`:1252`):

```python
            # Built once, before the shading branch, and handed to whichever path runs
            # (FeatureDemo.cpp:968-978). The two scales are written onto the probe objects here
            # because LightProbe::FillLightProbeConstants reads them off the struct -- the UI has
            # no other route to them.
            lightProbes = []
            if self.ui.EnableLightProbe:
                for probe in self.lightProbes:
                    if probe.enabled:
                        probe.diffuseScale = self.ui.LightProbeDiffuseScale
                        probe.specularScale = self.ui.LightProbeSpecularScale
                        lightProbes.append(probe)
```

- [ ] **Step 2: Feed the deferred path**

In the `if useDeferred:` branch, after `deferredInputs.SetLights(...)` (`:1295`):

```python
                deferredInputs.SetLightProbes(lightProbes)
```

Add this comment above it:

```python
                # The sample passes its WHOLE probe list here while giving the forward path the
                # filtered one (FeatureDemo.cpp:1021) -- an asymmetry that only works because
                # DeferredLightingPass skips probes failing IsActive(). One filtered list feeds
                # both paths here: identical rendered result, one thing to keep in sync instead
                # of two.
```

- [ ] **Step 3: Feed the forward path**

In the `else:` branch, extend the `self.forwardPass.PrepareLights(...)` call (`:1311-1317`) with the trailing argument:

```python
                self.forwardPass.PrepareLights(
                    forwardContext,
                    self.commandList,
                    self.scene.GetSceneGraph().GetLights(),
                    ambient * 0.2, ambient * 0.2, ambient * 0.2,
                    ambient * 0.1, ambient * 0.1, ambient * 0.1,
                    lightProbes,
                )
```

- [ ] **Step 4: Handle the shader reload**

In `ReloadShaders`, after the `self.CreateDepthPass(device)` call (`:598`):

```python
            # Recreated, not merely ResetCaches()'d: the constructor is what compiles this pass's
            # five shaders, so a reload that only cleared its caches would keep running the old
            # ones. Recreating it invalidates every probe -- probe.environmentBrdf points at the
            # OUTGOING pass's internally-owned BRDF texture, which dies with it -- so every probe
            # is disabled too. That mirrors what the sample does in SceneUnloading
            # (FeatureDemo.cpp:563-573); this port has no SceneUnloading, and a shader reload is
            # the analogous "everything built from shaders is stale now" point.
            #
            # The two cube-map arrays are NOT reallocated: they hold rendered pixels, not
            # anything derived from shader bytecode, and CreateLightProbes' probe objects still
            # index them correctly. Only the captured content is stale, which is what disabling
            # expresses.
            self.lightProbePass = pyd.LightProbeProcessingPass(
                device, self.shaderFactory, self.m_CommonPasses
            )
            for probe in self.lightProbes:
                probe.enabled = False
                probe.environmentBrdf = None
```

- [ ] **Step 5: Verify and run the suite**

Run: `uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('feature_demo.py').read_text()); print('parsed')" && uv run pytest -q`

Expected: `parsed`, then 133 passed.

- [ ] **Step 6: Commit**

```bash
git add feature_demo.py
git commit -m "Feed light probes to both shading paths

One filtered list of enabled probes serves forward and deferred alike.
The sample passes its unfiltered list to the deferred path and the
filtered one to forward, which works only because DeferredLightingPass
skips probes failing IsActive(); one list is the same result with one
thing to keep in sync.

A shader reload recreates LightProbeProcessingPass rather than resetting
its caches -- its constructor is what compiles its shaders -- and
therefore disables every probe, whose environmentBrdf handle points into
the outgoing pass."
```

---

## Task 7: `feature_demo.py` — UI, docstring and the manual run

**Files:**
- Modify: `feature_demo.py` (`UIRenderer.buildUI` at `:1579-1585` and `:1731`; module docstring at `:24-38`)

**Interfaces:**
- Consumes: Tasks 4–6.
- Produces: nothing.

- [ ] **Step 1: Add the enable checkbox and the two scales**

In `UIRenderer.buildUI`, directly after the "Ambient Intensity" slider (`:1579-1581`) — the sample's own placement (`FeatureDemo.cpp:1605-1610`):

```python
            _, self.ui.EnableLightProbe = pyd.ImGui.Checkbox(
                "Enable Light Probe", self.ui.EnableLightProbe
            )
            if self.ui.EnableLightProbe and pyd.ImGui.CollapsingHeader("Light Probe"):
                # DragFloat, not SliderFloat: the sample uses one, and the useful range sits at
                # the bottom of 0-10 where a linear slider cannot resolve it. Same reasoning as
                # the TAA section's "Max Radiance".
                _, self.ui.LightProbeDiffuseScale = pyd.ImGui.DragFloat(
                    "Diffuse Scale", self.ui.LightProbeDiffuseScale, 0.01, 0.0, 10.0
                )
                _, self.ui.LightProbeSpecularScale = pyd.ImGui.DragFloat(
                    "Specular Scale", self.ui.LightProbeSpecularScale, 0.01, 0.0, 10.0
                )
```

`pyd.ImGui.DragFloat`'s bound signature is `DragFloat(label, value, speed=1.0, vMin=0.0, vMax=0.0) -> tuple[bool, float]`, so the `0.01, 0.0, 10.0` above is `speed, vMin, vMax` — matching the sample's `0.01f, 0.0f, 10.0f`. The existing call at `feature_demo.py:1793-1795` is the working reference.

- [ ] **Step 2: Add the capture button row**

After the Lights section's `pyd.ImGui.PopID()` (`:1731`), matching `FeatureDemo.cpp:1658-1668`:

```python
            # PushID for the same reason the Lights and Material Editor sections have one:
            # CollapsingHeader pushes no ID scope, so buttons labelled "1".."4" here could
            # otherwise collide with any other generically-labelled widget on the panel.
            pyd.ImGui.PushID("LightProbes")
            pyd.ImGui.Text("Render Light Probe: ")
            for probe in self.app.lightProbes:
                pyd.ImGui.SameLine()
                if pyd.ImGui.Button(probe.name):
                    # Direct call, not a flag -- see RenderLightProbe's docstring. It runs
                    # synchronously here, so the frame this button is pressed on takes visibly
                    # longer; that is the capture, not a hang.
                    self.app.RenderLightProbe(probe)
            pyd.ImGui.PopID()
```

- [ ] **Step 3: Update the module docstring**

Replace lines `:24-33` of `feature_demo.py`:

```python
"""Port of Donut's FeatureDemo sample -- stages 1, 2a, 2b, 2c, 3a and 3b.

Renders media/sponza-plus.scene.json through the full HDR pipeline: deferred or forward
shading, a procedural sky, SSAO, TAA or MSAA, bloom, and tone mapping with eye adaptation,
with cascaded sun shadows, a spot and a point light, a switchable first-person/third-person/
scene camera, live light and material editors, right-click material picking, screenshots, a
MipMapGen test pass, a side-by-side stereo mode and four capturable light probes.

This completes the port. DLSS, taskflow and the ImGui console are out of scope permanently:
see docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md.
```

- [ ] **Step 4: Run the full suite**

Run: `uv sync && uv run pytest -q`

Expected: 133 passed.

- [ ] **Step 5: Run the example — the behavioural gate for the whole stage**

Run: `uv run feature_demo.py`

Check, in order:

1. It starts and renders Sponza as before, with no new NVRHI validation errors on the console.
2. "Enable Light Probe" is ticked by default, and the "Light Probe" header shows two DragFloats.
3. "Render Light Probe: 1 2 3 4" appears below the Lights section.
4. Pressing **1** produces a visible hitch (the synchronous capture) and then a **visible change in ambient lighting** — this is the gate that proves `SetBoundsFromBox` reached the real field, since a probe whose bounds stayed empty fails `IsActive()` and changes nothing.
5. Dragging "Diffuse Scale" to 0 and back visibly changes the scene, proving the per-frame scale push works.
6. Toggling "Deferred Shading" keeps the probe contributing — that is the deferred `SetLightProbes` path.
7. Capturing from a **scene camera** (switch to "Gallery", which is rotated, then press **2**) captures at the gallery viewpoint rather than somewhere unrelated — the `SceneCamera.GetPosition` correction.
8. Pressing **Reload Shaders** after a capture leaves the scene rendering correctly with the probe contribution gone, and a fresh capture works afterwards.
9. Untick "Enable Light Probe": the contribution disappears with no error — the empty-list off switch.

Report what you observed for each. If you cannot run a GPU build, say so plainly and do not tick this step — do not report the stage complete on a green headless suite alone.

- [ ] **Step 6: Commit**

```bash
git add feature_demo.py
git commit -m "Add the light probe UI and complete the FeatureDemo port

An Enable checkbox with diffuse/specular scale drags after Ambient
Intensity, and a per-probe capture button row after the Lights section,
both at the sample's own placements.

This is the last feature of the port; only DLSS, taskflow and the ImGui
console remain, all permanently out of scope."
```

---

## Notes for the executor

**The one thing tests cannot prove.** `LightProbe.IsActive()` needs a non-empty bounds *and* an assigned map, and a `Texture` cannot be created without a device. So the bounds helpers get callability and arity tests only; that they reach the real `dm::frustum` field is proven by Task 7 Step 5 item 4 — a captured probe that visibly changes the lighting must have had non-empty bounds. Do not "strengthen" the Task 1 tests by constructing a device; the suite's device-free property is what keeps it at sub-second runtime.

**Argument-order hazards.** Three calls in this plan are positional and silent when wrong: `RenderCompositeView` (Task 5 Step 3), `ImGui.DragFloat` (Task 7 Step 1), and `RenderSpecularMap`, whose `roughness` precedes the source map. The first two have their exact bound signatures quoted in their steps; the third is pinned by `test_render_specular_map_takes_roughness_before_the_source`. Re-read each against its reference rather than trusting the sketch.

**`SceneCamera` is abstract.** `pyd.SceneCamera()` raises `TypeError` (it inherits `SceneGraphLeaf::Clone()` pure and does not override it), which is why the Task 3 tests instantiate `pyd.PerspectiveCamera` and reach `GetPosition` through inheritance. Do not add a `SceneCamera()` construction test — `test_camera_bindings.py` already pins that it raises.

**Do not reorder `PrepareLights`' parameters.** `lightProbes` must stay last and defaulted. `test_prepare_lights_still_accepts_the_nine_argument_form` is the guard, and `deferred_shading.py`, `threaded_rendering.py` and `rt_bindless.py` are what break if it is removed.
