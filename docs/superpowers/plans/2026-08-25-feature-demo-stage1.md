# FeatureDemo Stage 1 (post-processing chain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind Donut's four post-processing passes (`SkyPass`, `SsaoPass`, `ToneMappingPass`, `BloomPass`) to Python and build `feature_demo.py` up to a runnable Sponza render with sky, SSAO, TAA/MSAA, bloom and tone mapping.

**Architecture:** Extend the single pybind11 translation unit `src/cpp/_pydonut.cpp` with four pass bindings plus the `IView`/`ICompositeView` polymorphic bases they consume, then write `feature_demo.py` as a `pyd.ApplicationBase` subclass that composes a `pyd.GBufferRenderTargets` with its own HDR/LDR targets. No C++ trampolines are added; Python composes rather than inherits.

**Tech Stack:** C++20, pybind11 3.x, NVRHI, Donut (vendored at `extern/donut`), scikit-build-core + uv, Python 3.14, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md`

## Global Constraints

- **Donut math types are never exposed to Python.** `dm::float3`, `dm::float4x4`, `dm::affine3`, `dm::uint2` etc. are always decomposed into flat scalar arguments. Precedent: `DeferredLightingPassInputs.SetAmbientColors(topR, topG, topB, bottomR, bottomG, bottomB)` at `src/cpp/_pydonut.cpp:2344`.
- **Bind only what the sample calls.** Every skipped constructor/method must carry a comment saying it was skipped and why, so a later stage can tell a decision from an oversight.
- **Three files stay in sync for every binding:** `src/cpp/_pydonut.cpp` (the binding), `src/pydonut/_pydonut.pyi` (the type stub), `src/pydonut/__init__.py` (the `from pydonut._pydonut import X` line **and** the `__all__` entry).
- **Rebuild after every C++ change** with `uv sync --reinstall-package pydonut`. Plain `uv sync` is cached on `src/**/*.{h,c,hpp,cpp}` (`pyproject.toml:24-31`) and is usually enough, but `--reinstall-package` is the reliable form.
- **Every new `.py` file starts with the project's MIT header** — copy the 22-line block verbatim from the top of `aftermath.py`, including `Copyright (C) 1991-2026 ASDAlexander77.`
- **Examples import as `from src import pydonut as pyd`** and are run with `uv run <name>.py`. Tests import as `import pydonut as pyd`.
- **C++ `float` defaults widen lossily into Python.** A `float` field whose default is not binary-exact (0.1f, 0.8f, 0.95f, 0.02f, …) arrives in Python as a `double` carrying the float32 residue — `0.1f` becomes `0.10000000149011612`. Assert those with `pytest.approx(...)`. Defaults that ARE binary-exact (0.5, 1.0, 2.0, 3.0, 16.0, 100.0, -0.5) stay on exact `==` deliberately, so a genuine drift in them still fails the test. The test module imports `pytest` for this.
- **Out of scope for every task in this plan:** DLSS, taskflow, ImGui console, shadows, light probes, MaterialID/PixelReadback, MipMapGen, stereo, screenshots.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/cpp/_pydonut.cpp` | All native bindings (single TU, existing convention) | 1–7 |
| `src/pydonut/_pydonut.pyi` | Type stubs mirroring the bindings | 1–7 |
| `src/pydonut/__init__.py` | Re-exports + `__all__` | 1–7 |
| `test/test_postprocess_bindings.py` | GPU-free surface tests for the new bindings | 1–7 |
| `pyproject.toml` | Add `[tool.pytest.ini_options] testpaths` | 1 |
| `feature_demo.py` | The ported example | 8–11 |

Tests live in `test/` (singular) because `pyproject.toml:47` already declares `test` in pyrefly's `search_path`. There is no `test/` directory yet; Task 1 creates it.

The tests in Tasks 1–7 are **surface tests**: they check that classes exist, that inheritance is wired, that parameter structs round-trip and carry the documented defaults, and that methods are present. They need no GPU and run in milliseconds. They catch the failure modes that actually bite a binding layer — typo'd names, a binding added to `_pydonut.cpp` but forgotten in `__init__.py`, a default silently changing. Real rendering behaviour is verified by running `feature_demo.py` in Tasks 8–11.

---

### Task 1: View base classes + test scaffolding

Registers `ICompositeView` and `IView` as polymorphic bases so the four passes can accept any view, and creates the test directory the rest of the plan uses.

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (add include; `PlanarView` decl at :2536; `CubemapView` decl at :2642)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Modify: `pyproject.toml`
- Create: `test/test_postprocess_bindings.py`

**Interfaces:**
- Consumes: nothing
- Produces: `pyd.ICompositeView`, `pyd.IView` — the base classes every later task's pass signatures accept. `PlanarView` and `CubemapView` become subclasses of `IView`.

- [ ] **Step 1: Add pytest testpaths so collection ignores `extern/`**

In `pyproject.toml`, after the `[tool.pyrefly]` block, add:

```toml
[tool.pytest.ini_options]
testpaths = ["test"]
```

- [ ] **Step 2: Write the failing test**

Create `test/test_postprocess_bindings.py` with the MIT header block copied verbatim from the top of `aftermath.py`, then:

```python
"""Surface tests for the FeatureDemo stage 1 post-processing bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a parameter default drifting away from the C++ header it mirrors.
"""

from __future__ import annotations

import pydonut as pyd


def test_view_bases_are_exported() -> None:
    assert hasattr(pyd, "ICompositeView")
    assert hasattr(pyd, "IView")


def test_planar_view_derives_from_iview() -> None:
    assert issubclass(pyd.PlanarView, pyd.IView)
    assert issubclass(pyd.IView, pyd.ICompositeView)


def test_cubemap_view_derives_from_iview() -> None:
    assert issubclass(pyd.CubemapView, pyd.IView)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest test/test_postprocess_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'ICompositeView'`

- [ ] **Step 4: Register the bases in `_pydonut.cpp`**

`donut/engine/View.h` is already included at `src/cpp/_pydonut.cpp:49`, so no new include is needed for this task.

Immediately **before** the existing `py::class_<donut::engine::PlanarView> planarView(m, "PlanarView");` line (`_pydonut.cpp:2536`), insert:

```cpp
    // ICompositeView/IView are registered as real polymorphic bases rather than having every
    // pass signature hardcode PlanarView&: SkyPass/SsaoPass/ToneMappingPass/BloomPass all take
    // const ICompositeView&, and there are already two concrete views bound (PlanarView,
    // CubemapView). Same reasoning as IDrawStrategy/IGeometryPass above (see :2282-2290).
    // Neither base is constructible from Python -- they exist purely to carry the conversion.
    py::class_<donut::engine::ICompositeView>(m, "ICompositeView");
    py::class_<donut::engine::IView, donut::engine::ICompositeView>(m, "IView");
```

Then change the `PlanarView` declaration itself from:

```cpp
    py::class_<donut::engine::PlanarView> planarView(m, "PlanarView");
```

to:

```cpp
    py::class_<donut::engine::PlanarView, donut::engine::IView> planarView(m, "PlanarView");
```

And at `_pydonut.cpp:2642`, change:

```cpp
    py::class_<donut::engine::CubemapView> cubemapView(m, "CubemapView");
```

to:

```cpp
    py::class_<donut::engine::CubemapView, donut::engine::IView> cubemapView(m, "CubemapView");
```

Leave `RenderView`, `RenderCompositeView`, `FramebufferFactory.GetFramebuffer` and `GBufferRenderTargets.GetFramebuffer` taking `PlanarView&` — widening them buys nothing until stage 3.

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, immediately before the existing `class PlanarView` declaration, add:

```python
# Polymorphic bases for the view hierarchy (View.h:46, View.h:55). Not constructible from
# Python -- they exist so passes that take any view (SkyPass, SsaoPass, ToneMappingPass,
# BloomPass) can accept PlanarView or CubemapView interchangeably.
class ICompositeView(): ...

class IView(ICompositeView): ...
```

Change `class PlanarView():` to `class PlanarView(IView):` and `class CubemapView():` to `class CubemapView(IView):`.

- [ ] **Step 6: Re-export from `__init__.py`**

In `src/pydonut/__init__.py`, add these lines next to the existing view imports (the block containing `from pydonut._pydonut import PlanarView`):

```python
from pydonut._pydonut import ICompositeView
from pydonut._pydonut import IView
```

And add `'ICompositeView',` and `'IView',` to the `__all__` tuple, next to `'PlanarView',`.

- [ ] **Step 7: Rebuild and run the test**

Run: `uv sync --reinstall-package pydonut && uv run pytest test/test_postprocess_bindings.py -v`
Expected: 3 passed

- [ ] **Step 8: Verify no existing example regressed**

Run: `uv run deferred_shading.py`
Expected: the window opens and renders as before. `PlanarView` gaining a base must not change any existing call site. Close the window.

- [ ] **Step 9: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py pyproject.toml test/test_postprocess_bindings.py
git commit -m "Register ICompositeView/IView as polymorphic view bases"
```

---

### Task 2: SkyParameters + SkyPass

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (include block at :38-61; insert bindings after the `TemporalAntiAliasingPass` block which ends at :2446)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Modify: `test/test_postprocess_bindings.py`

**Interfaces:**
- Consumes: `pyd.IView` (Task 1)
- Produces:
  - `pyd.SkyParameters()` — `SetSkyColor(r,g,b)`, `SetHorizonColor(r,g,b)`, `SetGroundColor(r,g,b)`, `SetDirectionUp(x,y,z)`; fields `brightness`, `horizonSize`, `glowSize`, `glowIntensity`, `glowSharpness`, `maxLightRadiance`
  - `pyd.SkyPass(device, shaderFactory, commonPasses, framebufferFactory, view)` with `Render(commandList, view, light, params)`

- [ ] **Step 1: Write the failing test**

Append to `test/test_postprocess_bindings.py`:

```python
def test_sky_parameters_defaults_match_header() -> None:
    p = pyd.SkyParameters()
    assert p.brightness == 0.1
    assert p.horizonSize == 30.0
    assert p.glowSize == 5.0
    assert p.glowIntensity == 0.1
    assert p.glowSharpness == 4.0
    assert p.maxLightRadiance == 100.0


def test_sky_parameters_are_writable() -> None:
    p = pyd.SkyParameters()
    p.brightness = 0.25
    assert p.brightness == 0.25


def test_sky_parameters_expose_flattened_float3_setters() -> None:
    p = pyd.SkyParameters()
    # dm::float3 fields are never exposed directly -- they are set as flat scalars.
    p.SetSkyColor(0.1, 0.2, 0.3)
    p.SetHorizonColor(0.4, 0.5, 0.6)
    p.SetGroundColor(0.7, 0.8, 0.9)
    p.SetDirectionUp(0.0, 1.0, 0.0)


def test_sky_pass_is_exported_with_render() -> None:
    assert hasattr(pyd, "SkyPass")
    assert hasattr(pyd.SkyPass, "Render")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_postprocess_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'SkyParameters'`

- [ ] **Step 3: Add the include**

In the include block of `src/cpp/_pydonut.cpp` (after `#include <donut/render/TemporalAntiAliasingPass.h>` at :58), add:

```cpp
#include <donut/render/SkyPass.h>
```

- [ ] **Step 4: Add the bindings**

Insert **after** the closing `;` of the `TemporalAntiAliasingPass` binding (`_pydonut.cpp:2446`) and before `py::class_<donut::engine::FramebufferFactory ...`:

```cpp
    // SkyParameters' four dm::float3 fields (skyColor/horizonColor/groundColor/directionUp)
    // follow this codebase's flat-scalar convention rather than being exposed as math types --
    // same shape as DeferredLightingPassInputs.SetAmbientColors above.
    py::class_<donut::render::SkyParameters>(m, "SkyParameters")
        .def(py::init<>())
        .def("SetSkyColor", [](donut::render::SkyParameters &self, float r, float g, float b) {
            self.skyColor = donut::math::float3(r, g, b);
        }, py::arg("r"), py::arg("g"), py::arg("b"))
        .def("SetHorizonColor", [](donut::render::SkyParameters &self, float r, float g, float b) {
            self.horizonColor = donut::math::float3(r, g, b);
        }, py::arg("r"), py::arg("g"), py::arg("b"))
        .def("SetGroundColor", [](donut::render::SkyParameters &self, float r, float g, float b) {
            self.groundColor = donut::math::float3(r, g, b);
        }, py::arg("r"), py::arg("g"), py::arg("b"))
        .def("SetDirectionUp", [](donut::render::SkyParameters &self, float x, float y, float z) {
            self.directionUp = donut::math::float3(x, y, z);
        }, py::arg("x"), py::arg("y"), py::arg("z"))
        .def_readwrite("brightness", &donut::render::SkyParameters::brightness)
        .def_readwrite("horizonSize", &donut::render::SkyParameters::horizonSize)
        .def_readwrite("glowSize", &donut::render::SkyParameters::glowSize)
        .def_readwrite("glowIntensity", &donut::render::SkyParameters::glowIntensity)
        .def_readwrite("glowSharpness", &donut::render::SkyParameters::glowSharpness)
        .def_readwrite("maxLightRadiance", &donut::render::SkyParameters::maxLightRadiance);

    // FillShaderParameters is deliberately not bound: it is a static helper for callers that
    // drive the procedural sky constants themselves, which no sample in this repo does.
    py::class_<donut::render::SkyPass, std::shared_ptr<donut::render::SkyPass>>(m, "SkyPass")
        .def(py::init([](nvrhi::IDevice* device, const std::shared_ptr<donut::engine::ShaderFactory> &shaderFactory,
                const std::shared_ptr<donut::engine::CommonRenderPasses> &commonPasses,
                const std::shared_ptr<donut::engine::FramebufferFactory> &framebufferFactory,
                const donut::engine::IView &compositeView) {
            return new donut::render::SkyPass(device, shaderFactory, commonPasses, framebufferFactory, compositeView);
        }), py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"),
            py::arg("framebufferFactory"), py::arg("compositeView"))
        .def("Render", [](const donut::render::SkyPass &self, nvrhi::ICommandList* commandList,
                const donut::engine::IView &compositeView, const donut::engine::DirectionalLight &light,
                const donut::render::SkyParameters &params) {
            self.Render(commandList, compositeView, light, params);
        }, py::arg("commandList"), py::arg("compositeView"), py::arg("light"), py::arg("params"));
```

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, after the `TemporalAntiAliasingPass` class (:1337-1340), add:

```python
# The four dm::float3 fields (skyColor, horizonColor, groundColor, directionUp) are set
# through flat-scalar methods -- donut math types are not exposed to Python.
class SkyParameters():
    brightness: float
    horizonSize: float
    glowSize: float
    glowIntensity: float
    glowSharpness: float
    maxLightRadiance: float
    def __init__(self: SkyParameters) -> None: ...
    def SetSkyColor(self: SkyParameters, r: float, g: float, b: float) -> None: ...
    def SetHorizonColor(self: SkyParameters, r: float, g: float, b: float) -> None: ...
    def SetGroundColor(self: SkyParameters, r: float, g: float, b: float) -> None: ...
    def SetDirectionUp(self: SkyParameters, x: float, y: float, z: float) -> None: ...

# FillShaderParameters is intentionally left unbound -- see _pydonut.cpp.
class SkyPass():
    def __init__(self: SkyPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, framebufferFactory: FramebufferFactory, compositeView: IView) -> None: ...
    def Render(self: SkyPass, commandList: CommandList, compositeView: IView, light: DirectionalLight, params: SkyParameters) -> None: ...
```

- [ ] **Step 6: Re-export from `__init__.py`**

Add next to the other render-pass imports:

```python
from pydonut._pydonut import SkyParameters
from pydonut._pydonut import SkyPass
```

And add `'SkyParameters',` and `'SkyPass',` to `__all__`.

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync --reinstall-package pydonut && uv run pytest test/test_postprocess_bindings.py -v`
Expected: 7 passed

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_postprocess_bindings.py
git commit -m "Bind SkyPass and SkyParameters"
```

---

### Task 3: SsaoParameters + SsaoPass

**Files:**
- Modify: `src/cpp/_pydonut.cpp`
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Modify: `test/test_postprocess_bindings.py`

**Interfaces:**
- Consumes: `pyd.IView` (Task 1)
- Produces:
  - `pyd.SsaoParameters()` — fields `amount`, `backgroundViewDepth`, `radiusWorld`, `surfaceBias`, `powerExponent`, `enableBlur`, `blurSharpness`
  - `pyd.SsaoPass(device, shaderFactory, commonPasses, gbufferDepth, gbufferNormals, destinationTexture)` with `Render(commandList, params, compositeView)`

- [ ] **Step 1: Write the failing test**

Append to `test/test_postprocess_bindings.py`:

```python
def test_ssao_parameters_defaults_match_header() -> None:
    p = pyd.SsaoParameters()
    assert p.amount == 2.0
    assert p.backgroundViewDepth == 100.0
    assert p.radiusWorld == 0.5
    # 0.1f is not exactly representable, so widening the C++ float to a Python double
    # gives 0.10000000149011612. Exact == would be unsatisfiable. Values that ARE
    # binary-exact (2.0, 100.0, 0.5, 16.0) stay on exact equality deliberately.
    assert p.surfaceBias == pytest.approx(0.1)
    assert p.powerExponent == 2.0
    assert p.enableBlur is True
    assert p.blurSharpness == 16.0


def test_ssao_parameters_are_writable() -> None:
    p = pyd.SsaoParameters()
    p.amount = 3.5
    p.enableBlur = False
    assert p.amount == 3.5
    assert p.enableBlur is False


def test_ssao_pass_is_exported_with_render() -> None:
    assert hasattr(pyd, "SsaoPass")
    assert hasattr(pyd.SsaoPass, "Render")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_postprocess_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'SsaoParameters'`

- [ ] **Step 3: Add the include**

After the `SkyPass.h` include added in Task 2:

```cpp
#include <donut/render/SsaoPass.h>
```

- [ ] **Step 4: Add the bindings**

Insert after the `SkyPass` binding from Task 2:

```cpp
    py::class_<donut::render::SsaoParameters>(m, "SsaoParameters")
        .def(py::init<>())
        .def_readwrite("amount", &donut::render::SsaoParameters::amount)
        .def_readwrite("backgroundViewDepth", &donut::render::SsaoParameters::backgroundViewDepth)
        .def_readwrite("radiusWorld", &donut::render::SsaoParameters::radiusWorld)
        .def_readwrite("surfaceBias", &donut::render::SsaoParameters::surfaceBias)
        .def_readwrite("powerExponent", &donut::render::SsaoParameters::powerExponent)
        .def_readwrite("enableBlur", &donut::render::SsaoParameters::enableBlur)
        .def_readwrite("blurSharpness", &donut::render::SsaoParameters::blurSharpness);

    // Only the texture-taking constructor is bound. SsaoPass' other constructor takes a
    // CreateParameters (which holds a dm::int2 that would need flattening) and pairs with
    // CreateBindingSet(..., bindingSetIndex) for callers juggling several binding sets across
    // views; nothing in this repo needs that, so neither is exposed. Render's bindingSetIndex
    // is likewise fixed at its default of 0.
    py::class_<donut::render::SsaoPass, std::shared_ptr<donut::render::SsaoPass>>(m, "SsaoPass")
        .def(py::init([](nvrhi::IDevice* device, std::shared_ptr<donut::engine::ShaderFactory> shaderFactory,
                std::shared_ptr<donut::engine::CommonRenderPasses> commonPasses, nvrhi::ITexture* gbufferDepth,
                nvrhi::ITexture* gbufferNormals, nvrhi::ITexture* destinationTexture) {
            return new donut::render::SsaoPass(device, shaderFactory, commonPasses, gbufferDepth,
                gbufferNormals, destinationTexture);
        }), py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"),
            py::arg("gbufferDepth"), py::arg("gbufferNormals"), py::arg("destinationTexture"))
        .def("Render", [](donut::render::SsaoPass &self, nvrhi::ICommandList* commandList,
                const donut::render::SsaoParameters &params, const donut::engine::IView &compositeView) {
            self.Render(commandList, params, compositeView);
        }, py::arg("commandList"), py::arg("params"), py::arg("compositeView"));
```

- [ ] **Step 5: Add the type stubs**

After the `SkyPass` stub added in Task 2:

```python
class SsaoParameters():
    amount: float
    backgroundViewDepth: float
    radiusWorld: float
    surfaceBias: float
    powerExponent: float
    enableBlur: bool
    blurSharpness: float
    def __init__(self: SsaoParameters) -> None: ...

# The CreateParameters constructor and CreateBindingSet are intentionally left unbound --
# see _pydonut.cpp. Render's bindingSetIndex is fixed at 0.
class SsaoPass():
    def __init__(self: SsaoPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, gbufferDepth: Texture, gbufferNormals: Texture, destinationTexture: Texture) -> None: ...
    def Render(self: SsaoPass, commandList: CommandList, params: SsaoParameters, compositeView: IView) -> None: ...
```

- [ ] **Step 6: Re-export from `__init__.py`**

```python
from pydonut._pydonut import SsaoParameters
from pydonut._pydonut import SsaoPass
```

And add `'SsaoParameters',` and `'SsaoPass',` to `__all__`.

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync --reinstall-package pydonut && uv run pytest test/test_postprocess_bindings.py -v`
Expected: 10 passed

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_postprocess_bindings.py
git commit -m "Bind SsaoPass and SsaoParameters"
```

---

### Task 4: ToneMappingParameters + ToneMappingPass

**Files:**
- Modify: `src/cpp/_pydonut.cpp`
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Modify: `test/test_postprocess_bindings.py`

**Interfaces:**
- Consumes: `pyd.IView` (Task 1)
- Produces:
  - `pyd.ToneMappingParameters()` — 9 fields
  - `pyd.ToneMappingPassCreateParameters()` — `isTextureArray`, `histogramBins`, `numConstantBufferVersions`, `exposureBufferOverride`
  - `pyd.ToneMappingPass(device, shaderFactory, commonPasses, framebufferFactory, compositeView, params)` with `SimpleRender(commandList, params, compositeView, sourceTexture)`, `AdvanceFrame(frameTime)`, `ResetExposure(commandList, initialExposure)`, `GetExposureBuffer()`

- [ ] **Step 1: Write the failing test**

Append to `test/test_postprocess_bindings.py`:

```python
def test_tone_mapping_parameters_defaults_match_header() -> None:
    p = pyd.ToneMappingParameters()
    # 0.8f / 0.95f / 0.02f are not exactly representable, so widening the C++ float to a
    # Python double leaves a residue and exact == would be unsatisfiable. The remaining
    # defaults (1.0, 0.5, -0.5, 3.0) are binary-exact and stay on exact equality.
    assert p.histogramLowPercentile == pytest.approx(0.8)
    assert p.histogramHighPercentile == pytest.approx(0.95)
    assert p.eyeAdaptationSpeedUp == 1.0
    assert p.eyeAdaptationSpeedDown == 0.5
    assert p.minAdaptedLuminance == pytest.approx(0.02)
    assert p.maxAdaptedLuminance == 0.5
    assert p.exposureBias == -0.5
    assert p.whitePoint == 3.0
    assert p.enableColorLUT is True


def test_tone_mapping_create_parameters_defaults_match_header() -> None:
    p = pyd.ToneMappingPassCreateParameters()
    assert p.isTextureArray is False
    assert p.histogramBins == 256
    assert p.numConstantBufferVersions == 16
    # exposureBufferOverride is how eye adaptation survives a resize; it starts unset.
    assert p.exposureBufferOverride is None


def test_tone_mapping_pass_exposes_the_simple_render_path() -> None:
    assert hasattr(pyd.ToneMappingPass, "SimpleRender")
    assert hasattr(pyd.ToneMappingPass, "AdvanceFrame")
    assert hasattr(pyd.ToneMappingPass, "ResetExposure")
    assert hasattr(pyd.ToneMappingPass, "GetExposureBuffer")


def test_tone_mapping_pass_omits_the_manual_histogram_path() -> None:
    # Render/ResetHistogram/AddFrameToHistogram/ComputeExposure are deliberately unbound:
    # SimpleRender performs those steps internally and is the only path the sample takes.
    assert not hasattr(pyd.ToneMappingPass, "AddFrameToHistogram")
    assert not hasattr(pyd.ToneMappingPass, "ComputeExposure")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_postprocess_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'ToneMappingParameters'`

- [ ] **Step 3: Add the include**

```cpp
#include <donut/render/ToneMappingPasses.h>
```

- [ ] **Step 4: Add the bindings**

Insert after the `SsaoPass` binding from Task 3:

```cpp
    py::class_<donut::render::ToneMappingParameters>(m, "ToneMappingParameters")
        .def(py::init<>())
        .def_readwrite("histogramLowPercentile", &donut::render::ToneMappingParameters::histogramLowPercentile)
        .def_readwrite("histogramHighPercentile", &donut::render::ToneMappingParameters::histogramHighPercentile)
        .def_readwrite("eyeAdaptationSpeedUp", &donut::render::ToneMappingParameters::eyeAdaptationSpeedUp)
        .def_readwrite("eyeAdaptationSpeedDown", &donut::render::ToneMappingParameters::eyeAdaptationSpeedDown)
        .def_readwrite("minAdaptedLuminance", &donut::render::ToneMappingParameters::minAdaptedLuminance)
        .def_readwrite("maxAdaptedLuminance", &donut::render::ToneMappingParameters::maxAdaptedLuminance)
        .def_readwrite("exposureBias", &donut::render::ToneMappingParameters::exposureBias)
        .def_readwrite("whitePoint", &donut::render::ToneMappingParameters::whitePoint)
        .def_readwrite("enableColorLUT", &donut::render::ToneMappingParameters::enableColorLUT);

    // colorLUT is intentionally left unbound -- nothing in this repo builds a colour LUT
    // texture. exposureBufferOverride IS bound and is not incidental: it is how eye adaptation
    // survives a window resize, by handing the outgoing pass's exposure buffer to its
    // replacement (FeatureDemo.cpp:831-840).
    py::class_<donut::render::ToneMappingPass::CreateParameters>(m, "ToneMappingPassCreateParameters")
        .def(py::init<>())
        .def_readwrite("isTextureArray", &donut::render::ToneMappingPass::CreateParameters::isTextureArray)
        .def_readwrite("histogramBins", &donut::render::ToneMappingPass::CreateParameters::histogramBins)
        .def_readwrite("numConstantBufferVersions", &donut::render::ToneMappingPass::CreateParameters::numConstantBufferVersions)
        .def_property("exposureBufferOverride",
            [](const donut::render::ToneMappingPass::CreateParameters &p) -> nvrhi::IBuffer* { return p.exposureBufferOverride; },
            [](donut::render::ToneMappingPass::CreateParameters &p, nvrhi::IBuffer* b) { p.exposureBufferOverride = b; },
            py::return_value_policy::reference);

    // Render/ResetHistogram/AddFrameToHistogram/ComputeExposure are deliberately not bound:
    // SimpleRender runs the histogram and exposure steps internally, and is the only tone
    // mapping entry point the sample uses (FeatureDemo.cpp:1158).
    py::class_<donut::render::ToneMappingPass, std::shared_ptr<donut::render::ToneMappingPass>>(m, "ToneMappingPass")
        .def(py::init([](nvrhi::IDevice* device, std::shared_ptr<donut::engine::ShaderFactory> shaderFactory,
                std::shared_ptr<donut::engine::CommonRenderPasses> commonPasses,
                std::shared_ptr<donut::engine::FramebufferFactory> framebufferFactory,
                const donut::engine::IView &compositeView,
                const donut::render::ToneMappingPass::CreateParameters &params) {
            return new donut::render::ToneMappingPass(device, shaderFactory, commonPasses,
                framebufferFactory, compositeView, params);
        }), py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"),
            py::arg("framebufferFactory"), py::arg("compositeView"), py::arg("params"))
        .def("SimpleRender", [](donut::render::ToneMappingPass &self, nvrhi::ICommandList* commandList,
                const donut::render::ToneMappingParameters &params, const donut::engine::IView &compositeView,
                nvrhi::ITexture* sourceTexture) {
            self.SimpleRender(commandList, params, compositeView, sourceTexture);
        }, py::arg("commandList"), py::arg("params"), py::arg("compositeView"), py::arg("sourceTexture"))
        .def("AdvanceFrame", &donut::render::ToneMappingPass::AdvanceFrame, py::arg("frameTime"))
        .def("ResetExposure", [](donut::render::ToneMappingPass &self, nvrhi::ICommandList* commandList,
                float initialExposure) {
            self.ResetExposure(commandList, initialExposure);
        }, py::arg("commandList"), py::arg("initialExposure") = 0.f)
        .def("GetExposureBuffer", [](donut::render::ToneMappingPass &self) -> nvrhi::IBuffer* {
            return self.GetExposureBuffer();
        }, py::return_value_policy::reference_internal);
```

- [ ] **Step 5: Add the type stubs**

```python
class ToneMappingParameters():
    histogramLowPercentile: float
    histogramHighPercentile: float
    eyeAdaptationSpeedUp: float
    eyeAdaptationSpeedDown: float
    minAdaptedLuminance: float
    maxAdaptedLuminance: float
    exposureBias: float
    whitePoint: float
    enableColorLUT: bool
    def __init__(self: ToneMappingParameters) -> None: ...

# colorLUT is intentionally left unbound. exposureBufferOverride carries eye adaptation
# across a resize -- hand it the outgoing pass's GetExposureBuffer().
class ToneMappingPassCreateParameters():
    isTextureArray: bool
    histogramBins: int
    numConstantBufferVersions: int
    exposureBufferOverride: Optional[Buffer]
    def __init__(self: ToneMappingPassCreateParameters) -> None: ...

# Render/ResetHistogram/AddFrameToHistogram/ComputeExposure are intentionally left unbound --
# SimpleRender performs those steps internally.
class ToneMappingPass():
    def __init__(self: ToneMappingPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, framebufferFactory: FramebufferFactory, compositeView: IView, params: ToneMappingPassCreateParameters) -> None: ...
    def SimpleRender(self: ToneMappingPass, commandList: CommandList, params: ToneMappingParameters, compositeView: IView, sourceTexture: Texture) -> None: ...
    def AdvanceFrame(self: ToneMappingPass, frameTime: float) -> None: ...
    def ResetExposure(self: ToneMappingPass, commandList: CommandList, initialExposure: float = 0.0) -> None: ...
    def GetExposureBuffer(self: ToneMappingPass) -> Buffer: ...
```

- [ ] **Step 6: Re-export from `__init__.py`**

```python
from pydonut._pydonut import ToneMappingParameters
from pydonut._pydonut import ToneMappingPassCreateParameters
from pydonut._pydonut import ToneMappingPass
```

And add all three to `__all__`.

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync --reinstall-package pydonut && uv run pytest test/test_postprocess_bindings.py -v`
Expected: 14 passed

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_postprocess_bindings.py
git commit -m "Bind ToneMappingPass and its parameter structs"
```

---

### Task 5: BloomPass

**Files:**
- Modify: `src/cpp/_pydonut.cpp`
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Modify: `test/test_postprocess_bindings.py`

**Interfaces:**
- Consumes: `pyd.IView` (Task 1)
- Produces: `pyd.BloomPass(device, shaderFactory, commonPasses, framebufferFactory, compositeView)` with `Render(commandList, framebufferFactory, compositeView, sourceDestTexture, sigmaInPixels, blendFactor)`

- [ ] **Step 1: Write the failing test**

Append to `test/test_postprocess_bindings.py`:

```python
def test_bloom_pass_is_exported_with_render() -> None:
    assert hasattr(pyd, "BloomPass")
    assert hasattr(pyd.BloomPass, "Render")


def test_bloom_render_takes_a_framebuffer_factory_per_call() -> None:
    # BloomPass takes a FramebufferFactory at construction AND at every Render call, because
    # the sample bloom's into different targets depending on AA mode (FeatureDemo.cpp:1128
    # vs :1146). Assert the per-call parameter survives in the signature.
    import inspect

    doc = inspect.getdoc(pyd.BloomPass.Render) or ""
    assert "framebufferFactory" in doc
    assert "sigmaInPixels" in doc
    assert "blendFactor" in doc
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_postprocess_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'BloomPass'`

- [ ] **Step 3: Add the include**

```cpp
#include <donut/render/BloomPass.h>
```

- [ ] **Step 4: Add the binding**

Insert after the `ToneMappingPass` binding from Task 4:

```cpp
    // The FramebufferFactory is passed both at construction and at every Render call, and they
    // are not always the same one: the sample blooms into the resolved framebuffer on the TAA
    // path (FeatureDemo.cpp:1128) but into the HDR-or-resolved framebuffer on the MSAA path
    // (FeatureDemo.cpp:1146). Both parameters are therefore exposed.
    py::class_<donut::render::BloomPass, std::shared_ptr<donut::render::BloomPass>>(m, "BloomPass")
        .def(py::init([](nvrhi::IDevice* device, const std::shared_ptr<donut::engine::ShaderFactory> &shaderFactory,
                std::shared_ptr<donut::engine::CommonRenderPasses> commonPasses,
                std::shared_ptr<donut::engine::FramebufferFactory> framebufferFactory,
                const donut::engine::IView &compositeView) {
            return new donut::render::BloomPass(device, shaderFactory, commonPasses, framebufferFactory, compositeView);
        }), py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"),
            py::arg("framebufferFactory"), py::arg("compositeView"))
        .def("Render", [](donut::render::BloomPass &self, nvrhi::ICommandList* commandList,
                const std::shared_ptr<donut::engine::FramebufferFactory> &framebufferFactory,
                const donut::engine::IView &compositeView, nvrhi::ITexture* sourceDestTexture,
                float sigmaInPixels, float blendFactor) {
            self.Render(commandList, framebufferFactory, compositeView, sourceDestTexture, sigmaInPixels, blendFactor);
        }, py::arg("commandList"), py::arg("framebufferFactory"), py::arg("compositeView"),
            py::arg("sourceDestTexture"), py::arg("sigmaInPixels"), py::arg("blendFactor"));
```

- [ ] **Step 5: Add the type stub**

```python
# The FramebufferFactory is supplied both at construction and per Render call -- they differ
# between the TAA and MSAA paths. sourceDestTexture is read and written in place.
class BloomPass():
    def __init__(self: BloomPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, framebufferFactory: FramebufferFactory, compositeView: IView) -> None: ...
    def Render(self: BloomPass, commandList: CommandList, framebufferFactory: FramebufferFactory, compositeView: IView, sourceDestTexture: Texture, sigmaInPixels: float, blendFactor: float) -> None: ...
```

- [ ] **Step 6: Re-export from `__init__.py`**

```python
from pydonut._pydonut import BloomPass
```

And add `'BloomPass',` to `__all__`.

- [ ] **Step 7: Rebuild and run the tests**

Run: `uv sync --reinstall-package pydonut && uv run pytest test/test_postprocess_bindings.py -v`
Expected: 16 passed

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_postprocess_bindings.py
git commit -m "Bind BloomPass"
```

---

### Task 6: GBufferRenderTargets accessors + CommandList.resolveTexture

The render-target plumbing the example needs to reach the G-buffer textures by name and to resolve MSAA colour before bloom.

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (`GBufferRenderTargets` block at :2298-2314; `CommandList` block, insert after `endMarker` at :1722)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `test/test_postprocess_bindings.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `GBufferRenderTargets` read-only properties `Depth`, `GBufferDiffuse`, `GBufferSpecular`, `GBufferNormals`, `GBufferEmissive`, `MotionVectors`, `GBufferFramebuffer`; methods `GetSampleCount()`, `GetUseReverseProjection()`
  - `CommandList.resolveTexture(dest, src)`

- [ ] **Step 1: Write the failing test**

Append to `test/test_postprocess_bindings.py`:

```python
def test_gbuffer_render_targets_expose_their_textures() -> None:
    rt = pyd.GBufferRenderTargets()
    # Uninitialised (Init not called), so every handle is still null -- but the properties
    # must exist and be readable, which is what the example relies on.
    for name in (
        "Depth",
        "GBufferDiffuse",
        "GBufferSpecular",
        "GBufferNormals",
        "GBufferEmissive",
        "MotionVectors",
        "GBufferFramebuffer",
    ):
        assert hasattr(rt, name), name
        assert getattr(rt, name) is None


def test_gbuffer_render_targets_report_sample_count() -> None:
    rt = pyd.GBufferRenderTargets()
    assert rt.GetSampleCount() == 0
    assert rt.GetUseReverseProjection() is False


def test_command_list_can_resolve_textures() -> None:
    # Bound without subresource arguments, matching clearTextureFloat/clearDepthStencilTexture
    # which likewise hide nvrhi::TextureSubresourceSet from Python.
    assert hasattr(pyd.CommandList, "resolveTexture")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_postprocess_bindings.py -v`
Expected: FAIL — `AssertionError: Depth`

- [ ] **Step 3: Add the `GBufferRenderTargets` accessors**

In `src/cpp/_pydonut.cpp`, extend the existing `GBufferRenderTargets` binding. It currently ends at :2314 with:

```cpp
        }, py::arg("view"), py::return_value_policy::reference_internal);
```

Change that trailing `);` to `)` — dropping only the semicolon — then append the chain below, which supplies the new terminating `;`:

```cpp
        // The public texture handles from GBuffer.h. The example reads them by name to wire up
        // SsaoPass (Depth + GBufferNormals), the TAA create parameters (Depth + MotionVectors)
        // and the deferred lighting inputs.
        .def_property_readonly("Depth", [](donut::render::GBufferRenderTargets &self) -> nvrhi::ITexture* {
            return self.Depth;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("GBufferDiffuse", [](donut::render::GBufferRenderTargets &self) -> nvrhi::ITexture* {
            return self.GBufferDiffuse;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("GBufferSpecular", [](donut::render::GBufferRenderTargets &self) -> nvrhi::ITexture* {
            return self.GBufferSpecular;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("GBufferNormals", [](donut::render::GBufferRenderTargets &self) -> nvrhi::ITexture* {
            return self.GBufferNormals;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("GBufferEmissive", [](donut::render::GBufferRenderTargets &self) -> nvrhi::ITexture* {
            return self.GBufferEmissive;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("MotionVectors", [](donut::render::GBufferRenderTargets &self) -> nvrhi::ITexture* {
            return self.MotionVectors;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("GBufferFramebuffer", [](donut::render::GBufferRenderTargets &self) {
            return self.GBufferFramebuffer;
        })
        .def("GetSampleCount", &donut::render::GBufferRenderTargets::GetSampleCount)
        .def("GetUseReverseProjection", &donut::render::GBufferRenderTargets::GetUseReverseProjection);
```

Note: `IsUpdateRequired` is **not** added here. It is not a `GBufferRenderTargets` method — the C++ sample defines it on its own derived class. `feature_demo.py` implements it in Python (Task 8).

- [ ] **Step 4: Add `CommandList.resolveTexture`**

Insert after the `endMarker` binding (`_pydonut.cpp:1722`):

```cpp
    // Subresources are fixed at TextureSubresourceSet(0, 1, 0, 1) -- mip 0, array slice 0 --
    // matching FeatureDemo.cpp:1138 and the same hide-the-subresource-set convention already
    // used by clearTextureFloat/clearDepthStencilTexture above (which pass AllSubresources).
    commandList.def("resolveTexture", [](nvrhi::ICommandList &self, nvrhi::ITexture* dest, nvrhi::ITexture* src) {
        const nvrhi::TextureSubresourceSet subresources(0, 1, 0, 1);
        self.resolveTexture(dest, subresources, src, subresources);
    }, py::arg("dest"), py::arg("src"));
```

- [ ] **Step 5: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, add to the existing `class GBufferRenderTargets`:

```python
    # Public texture handles from GBuffer.h. All None until Init() has been called.
    Depth: Optional[Texture]
    GBufferDiffuse: Optional[Texture]
    GBufferSpecular: Optional[Texture]
    GBufferNormals: Optional[Texture]
    GBufferEmissive: Optional[Texture]
    MotionVectors: Optional[Texture]
    GBufferFramebuffer: Optional[FramebufferFactory]
    def GetSampleCount(self: GBufferRenderTargets) -> int: ...
    def GetUseReverseProjection(self: GBufferRenderTargets) -> bool: ...
```

And to the existing `class CommandList`:

```python
    # Resolves mip 0 / array slice 0 only; nvrhi::TextureSubresourceSet is not exposed to
    # Python, matching clearTextureFloat and clearDepthStencilTexture.
    def resolveTexture(self: CommandList, dest: Texture, src: Texture) -> None: ...
```

No `__init__.py` change is needed — `GBufferRenderTargets` and `CommandList` are already exported.

- [ ] **Step 6: Rebuild and run the tests**

Run: `uv sync --reinstall-package pydonut && uv run pytest test/test_postprocess_bindings.py -v`
Expected: 19 passed

- [ ] **Step 7: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi test/test_postprocess_bindings.py
git commit -m "Expose GBufferRenderTargets textures and CommandList.resolveTexture"
```

---

### Task 7: ImGui widget additions

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (`ImGui` class block at :2733-2782; append before the terminating `;` on the `Button` binding)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `test/test_postprocess_bindings.py`

**Interfaces:**
- Consumes: nothing
- Produces: `pyd.ImGui.SliderFloat(label, value, vMin, vMax) -> (changed, value)`, `pyd.ImGui.DragFloat(label, value, speed, vMin, vMax) -> (changed, value)`, `pyd.ImGui.CollapsingHeader(label) -> bool`, `pyd.ImGui.SameLine()`, `pyd.ImGui.SetItemDefaultFocus()`

- [ ] **Step 1: Write the failing test**

Append to `test/test_postprocess_bindings.py`:

```python
def test_new_imgui_widgets_are_bound() -> None:
    for name in ("SliderFloat", "DragFloat", "CollapsingHeader", "SameLine", "SetItemDefaultFocus"):
        assert hasattr(pyd.ImGui, name), name


def test_imgui_text_already_covers_text_unformatted() -> None:
    # ImGui.Text is deliberately implemented as ImGui::TextUnformatted (_pydonut.cpp:2753)
    # so Python string content can never be read as a printf format string. No separate
    # TextUnformatted binding is needed or wanted.
    assert hasattr(pyd.ImGui, "Text")
    assert not hasattr(pyd.ImGui, "TextUnformatted")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/test_postprocess_bindings.py -v`
Expected: FAIL — `AssertionError: SliderFloat`

- [ ] **Step 3: Add the bindings**

In `src/cpp/_pydonut.cpp`, the `ImGui` class chain currently ends at :2782 with:

```cpp
        }, py::arg("label"));
```

Change that trailing `);` to `)` — dropping only the semicolon — then append the chain below, which supplies the new terminating `;`:

```cpp
        // Out-params follow the (changed, newValue) tuple convention documented at the top of
        // this class -- e.g. changed, ui.bloomSigma = pyd.ImGui.SliderFloat(...).
        .def_static("SliderFloat", [](const std::string &label, float value, float vMin, float vMax) {
            bool changed = ImGui::SliderFloat(label.c_str(), &value, vMin, vMax);
            return py::make_tuple(changed, value);
        }, py::arg("label"), py::arg("value"), py::arg("vMin"), py::arg("vMax"))
        .def_static("DragFloat", [](const std::string &label, float value, float speed, float vMin, float vMax) {
            bool changed = ImGui::DragFloat(label.c_str(), &value, speed, vMin, vMax);
            return py::make_tuple(changed, value);
        }, py::arg("label"), py::arg("value"), py::arg("speed") = 1.0f, py::arg("vMin") = 0.0f, py::arg("vMax") = 0.0f)
        .def_static("CollapsingHeader", [](const std::string &label) {
            return ImGui::CollapsingHeader(label.c_str());
        }, py::arg("label"))
        .def_static("SameLine", []() { ImGui::SameLine(); })
        .def_static("SetItemDefaultFocus", &ImGui::SetItemDefaultFocus);
```

- [ ] **Step 4: Add the type stubs**

In `src/pydonut/_pydonut.pyi`, add to the existing `class ImGui`:

```python
    @staticmethod
    def SliderFloat(label: str, value: float, vMin: float, vMax: float) -> tuple[bool, float]: ...
    @staticmethod
    def DragFloat(label: str, value: float, speed: float = 1.0, vMin: float = 0.0, vMax: float = 0.0) -> tuple[bool, float]: ...
    @staticmethod
    def CollapsingHeader(label: str) -> bool: ...
    @staticmethod
    def SameLine() -> None: ...
    @staticmethod
    def SetItemDefaultFocus() -> None: ...
```

- [ ] **Step 5: Rebuild and run the tests**

Run: `uv sync --reinstall-package pydonut && uv run pytest test/test_postprocess_bindings.py -v`
Expected: 21 passed

- [ ] **Step 6: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi test/test_postprocess_bindings.py
git commit -m "Bind SliderFloat, DragFloat, CollapsingHeader, SameLine, SetItemDefaultFocus"
```

---

### Task 8: `feature_demo.py` — scene loads and presents

The first runnable milestone: Sponza on screen through the deferred path, no post-processing yet.

**Files:**
- Create: `feature_demo.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7
- Produces:
  - `RenderTargets` — `.gbuffer` (a `pyd.GBufferRenderTargets`), `.HdrColor`, `.LdrColor`, `.ResolvedColor`, `.TemporalFeedback1`, `.TemporalFeedback2`, `.AmbientOcclusion`, `.ForwardFramebuffer`, `.HdrFramebuffer`, `.LdrFramebuffer`, `.ResolvedFramebuffer`, `.Init(device, width, height, sampleCount)`, `.IsUpdateRequired(width, height, sampleCount) -> bool`, `.Clear(commandList)`
  - `AntiAliasingMode` — `IntEnum` with `NONE`, `TEMPORAL`, `MSAA_2X`, `MSAA_4X`, `MSAA_8X`
  - `UIData` — the shared UI state object
  - `FeatureDemo(pyd.ApplicationBase)` — `.Init()`, `.SetupView()`, `.CreateRenderPasses()`, `.Render(framebuffer)`, `.Animate(seconds)`, `.BackBufferResizing()`

Because `feature_demo.py` is a windowed example with no automated test surface (no example in this repo has one), each of Tasks 8–11 is verified by **running** it and observing specific, named outcomes. That is the repo's existing standard for examples; the binding layer underneath is what carries the pytest coverage.

- [ ] **Step 1: Create the file skeleton**

Create `feature_demo.py`. Start with the 22-line MIT header copied verbatim from `aftermath.py`, then a module docstring:

```python
"""Port of Donut's FeatureDemo sample -- stage 1 of 3.

Renders media/sponza-plus.scene.json through the full HDR pipeline: deferred or forward
shading, a procedural sky, SSAO, TAA or MSAA, bloom, and tone mapping with eye adaptation.

Stage 1 deliberately omits shadows, light probes, material/light editors, the scene-camera
dropdown, MaterialID readback, MipMapGen, stereo and screenshots -- those arrive in stages 2
and 3. DLSS, taskflow and the ImGui console are out of scope permanently: see
docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md.

NOTE: sponza-plus.scene.json declares no lights at all, so the directional "Sun" light this
example renders with is created here and attached to the scene graph, not loaded.
"""

from __future__ import annotations

if __name__ == "__main__":
    import sys
    from enum import IntEnum
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Feature Demo"
    folder = Path(__file__).resolve().parent

    _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE = 64

    class AntiAliasingMode(IntEnum):
        """No DLSS entry -- it needs the NGX SDK, which this repo does not vendor."""

        NONE = 0
        TEMPORAL = 1
        MSAA_2X = 2
        MSAA_4X = 3
        MSAA_8X = 4

    SAMPLE_COUNTS = {
        AntiAliasingMode.NONE: 1,
        AntiAliasingMode.TEMPORAL: 1,
        AntiAliasingMode.MSAA_2X: 2,
        AntiAliasingMode.MSAA_4X: 4,
        AntiAliasingMode.MSAA_8X: 8,
    }
```

- [ ] **Step 2: Add `UIData`**

Append inside the `if __name__ == "__main__":` block:

```python
    class UIData:
        """Shared by reference between FeatureDemo and UIRenderer.

        Same convention as work_graphs.py, rt_particles.py and aftermath.py: one plain object
        held by both, rather than the C++ original's UIRenderer-holds-FeatureDemo& plus setters.
        """

        def __init__(self: UIData) -> None:
            self.ShowUI = True
            self.UseDeferredShading = True
            self.EnableSsao = True
            self.SsaoParams = pyd.SsaoParameters()
            self.ToneMappingParams = pyd.ToneMappingParameters()
            self.TemporalAntiAliasingParams = pyd.TemporalAntiAliasingParameters()
            self.SkyParams = pyd.SkyParameters()
            self.AntiAliasingMode = AntiAliasingMode.TEMPORAL
            self.EnableVsync = True
            self.EnableProceduralSky = True
            self.EnableBloom = True
            self.BloomSigma = 32.0
            self.BloomAlpha = 0.05
            self.EnableTranslucency = True
            self.EnableMaterialEvents = False
            self.AmbientIntensity = 1.0
            self.EnableAnimations = False
            self.ShaderReloadRequested = False
```

- [ ] **Step 3: Add `RenderTargets`**

The C++ original subclasses `GBufferRenderTargets`; Python composes instead, because the only polymorphic use is `SetGBuffer`, which accepts the base directly.

```python
    class RenderTargets:
        """Composes a pyd.GBufferRenderTargets with the extra HDR/LDR targets the sample needs.

        The C++ original derives from GBufferRenderTargets and overrides Init. Composition
        works here because the one place the object is used polymorphically --
        DeferredLightingPassInputs.SetGBuffer -- takes the base class, which .gbuffer is.
        """

        def __init__(self: RenderTargets) -> None:
            self.gbuffer = pyd.GBufferRenderTargets()
            self.HdrColor: pyd.Texture | None = None
            self.LdrColor: pyd.Texture | None = None
            self.ResolvedColor: pyd.Texture | None = None
            self.TemporalFeedback1: pyd.Texture | None = None
            self.TemporalFeedback2: pyd.Texture | None = None
            self.AmbientOcclusion: pyd.Texture | None = None
            self.ForwardFramebuffer: pyd.FramebufferFactory | None = None
            self.HdrFramebuffer: pyd.FramebufferFactory | None = None
            self.LdrFramebuffer: pyd.FramebufferFactory | None = None
            self.ResolvedFramebuffer: pyd.FramebufferFactory | None = None
            self.width = 0
            self.height = 0
            self.sampleCount = 0

        def Init(
            self: RenderTargets, device: pyd.Device, width: int, height: int, sampleCount: int
        ) -> None:
            self.gbuffer.Init(device, width, height, sampleCount, True, True)
            self.width, self.height, self.sampleCount = width, height, sampleCount

            isMultisampled = sampleCount > 1

            def makeColor(fmt: pyd.Format, name: str, allowUav: bool) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = width
                desc.height = height
                desc.isRenderTarget = True
                desc.useClearValue = True
                desc.clearValue = pyd.Color(0.0)
                desc.sampleCount = sampleCount
                desc.dimension = (
                    pyd.TextureDimension.Texture2DMS
                    if isMultisampled
                    else pyd.TextureDimension.Texture2D
                )
                desc.keepInitialState = True
                desc.isTypeless = False
                desc.isUAV = allowUav and not isMultisampled
                desc.format = fmt
                desc.initialState = pyd.ResourceStates.RenderTarget
                desc.debugName = name
                return device.createTexture(desc)

            self.HdrColor = makeColor(pyd.Format.RGBA16_FLOAT, "HdrColor", True)

            # ResolvedColor and the TAA feedback pair are always single-sampled: they are the
            # *output* of resolving, so they must not themselves be multisampled.
            def makeSingleSampled(fmt: pyd.Format, name: str, isUav: bool) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = width
                desc.height = height
                desc.isRenderTarget = True
                desc.useClearValue = True
                desc.clearValue = pyd.Color(0.0)
                desc.sampleCount = 1
                desc.dimension = pyd.TextureDimension.Texture2D
                desc.keepInitialState = True
                desc.isTypeless = False
                desc.isUAV = isUav
                desc.format = fmt
                desc.initialState = pyd.ResourceStates.RenderTarget
                desc.debugName = name
                return device.createTexture(desc)

            self.ResolvedColor = makeSingleSampled(pyd.Format.RGBA16_FLOAT, "ResolvedColor", True)
            self.TemporalFeedback1 = makeSingleSampled(pyd.Format.RGBA16_SNORM, "TemporalFeedback1", True)
            self.TemporalFeedback2 = makeSingleSampled(pyd.Format.RGBA16_SNORM, "TemporalFeedback2", True)
            self.LdrColor = makeSingleSampled(pyd.Format.SRGBA8_UNORM, "LdrColor", False)
            self.AmbientOcclusion = makeSingleSampled(pyd.Format.R8_UNORM, "AmbientOcclusion", True)

            depth = self.gbuffer.Depth

            self.ForwardFramebuffer = pyd.FramebufferFactory(device)
            self.ForwardFramebuffer.SetRenderTargets([self.HdrColor])
            self.ForwardFramebuffer.depthTarget = depth

            self.HdrFramebuffer = pyd.FramebufferFactory(device)
            self.HdrFramebuffer.SetRenderTargets([self.HdrColor])

            self.LdrFramebuffer = pyd.FramebufferFactory(device)
            self.LdrFramebuffer.SetRenderTargets([self.LdrColor])

            self.ResolvedFramebuffer = pyd.FramebufferFactory(device)
            self.ResolvedFramebuffer.SetRenderTargets([self.ResolvedColor])

        def IsUpdateRequired(
            self: RenderTargets, width: int, height: int, sampleCount: int
        ) -> bool:
            """Not a GBufferRenderTargets method -- the C++ sample defines this on its own
            derived class (FeatureDemo.cpp:213), so it lives in Python here."""
            return (
                self.width != width
                or self.height != height
                or self.sampleCount != sampleCount
            )

        def Clear(self: RenderTargets, commandList: pyd.CommandList) -> None:
            self.gbuffer.Clear(commandList)
            commandList.clearTextureFloat(self.HdrColor, pyd.Color(0.0))
```

- [ ] **Step 4: Add the `FeatureDemo` application class (deferred path only, no post-processing)**

```python
    class FeatureDemo(pyd.ApplicationBase):
        def __init__(self: FeatureDemo, deviceManager: pyd.DeviceManager, ui: UIData) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            self.rootFS = pyd.RootFileSystem()
            self.nativeFS = pyd.NativeFileSystem()
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.scene: pyd.Scene | None = None
            self.sunLight: pyd.DirectionalLight | None = None
            self.renderTargets: RenderTargets | None = None
            self.view: pyd.PlanarView | None = None
            self.viewPrevious: pyd.PlanarView | None = None
            self.camera = pyd.FirstPersonCamera()
            self.commandList: pyd.CommandList | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.gbufferPass: pyd.GBufferFillPass | None = None
            self.deferredLightingPass: pyd.DeferredLightingPass | None = None
            self.opaqueDrawStrategy = pyd.InstancedOpaqueDrawStrategy()
            self.transparentDrawStrategy = pyd.TransparentDrawStrategy()
            self.descriptorTable: pyd.DescriptorTableManager | None = None
            self.bindlessLayout: pyd.BindingLayout | None = None
            self.previousViewsValid = False

        def Init(self: FeatureDemo) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            frameworkShaderPath = (
                folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            )
            self.rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.shaderFactory = pyd.ShaderFactory(device, self.rootFS, Path("/shaders"))

            self.commandList = device.createCommandList()
            self.bindingCache = pyd.BindingCache(device)

            # DescriptorTableManager takes (device, layout) -- it needs a bindless layout, not
            # just a device. Same construction as bindless_rendering.py:116-124.
            bindlessLayoutDesc = pyd.BindlessLayoutDesc()
            bindlessLayoutDesc.visibility = pyd.ShaderType.All
            bindlessLayoutDesc.firstSlot = 0
            bindlessLayoutDesc.maxCapacity = 1024
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.RawBuffer_SRV(1))
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.Texture_SRV(2))
            self.bindlessLayout = device.createBindlessLayout(bindlessLayoutDesc)
            self.descriptorTable = pyd.DescriptorTableManager(device, self.bindlessLayout)

            self.m_CommonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.m_TextureCache = pyd.TextureCache(device, self.nativeFS, self.descriptorTable)

            # Synchronous load: the async path is not exercised by any existing example.
            self.SetAsynchronousLoadingEnabled(False)

            scenePath = folder / "media" / "sponza-plus.scene.json"
            self.scene = pyd.Scene(
                device,
                self.shaderFactory,
                self.nativeFS,
                self.m_TextureCache,
                self.descriptorTable,
            )
            if not self.scene.Load(scenePath):
                pyd.log.fatal(f"Failed to load {scenePath}")
                return False

            self.CreateSunLight()
            self.scene.FinishedLoading(self.GetFrameIndex())

            self.camera.LookAt(0.0, 1.8, 0.0, 1.0, 1.8, 0.0)
            self.camera.SetMoveSpeed(3.0)

            self.gbufferPass = pyd.GBufferFillPass(device, self.m_CommonPasses)
            self.gbufferPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())

            self.deferredLightingPass = pyd.DeferredLightingPass(device, self.m_CommonPasses)
            self.deferredLightingPass.Init(self.shaderFactory)

            return True

        def CreateSunLight(self: FeatureDemo) -> None:
            """sponza-plus.scene.json declares no lights, so the sun is always synthesised
            here -- this mirrors FeatureDemo.cpp:619-627, which treats it as a fallback."""
            assert self.scene is not None
            graph = self.scene.GetSceneGraph()

            for light in graph.GetLights():
                if isinstance(light, pyd.DirectionalLight):
                    self.sunLight = light
                    if self.sunLight.irradiance <= 0.0:
                        self.sunLight.irradiance = 1.0
                    return

            self.sunLight = pyd.DirectionalLight()
            self.sunLight.angularSize = 0.53
            self.sunLight.irradiance = 1.0

            node = pyd.SceneGraphNode()
            node.SetName("Sun")
            node.SetLeaf(self.sunLight)
            graph.AttachLeafNode(graph.GetRootNode(), node)
            self.sunLight.SetDirection(0.1, -0.9, 0.1)

            graph.Refresh(0)
```

- [ ] **Step 5: Add `SetupView`, `BackBufferResizing`, `Animate` and a minimal `Render`**

```python
        def BackBufferResizing(self: FeatureDemo) -> None:
            self.renderTargets = None
            self.bindingCache.Clear()

        def Animate(self: FeatureDemo, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def SetupView(self: FeatureDemo, width: int, height: int) -> None:
            if self.view is None:
                self.view = pyd.PlanarView()
                self.viewPrevious = pyd.PlanarView()

            viewport = pyd.Viewport(float(width), float(height))
            self.view.SetViewport(viewport)
            self.view.SetMatricesFromCamera(self.camera, width / height)
            self.view.UpdateCache()

        def Render(self: FeatureDemo, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            fbInfo = framebuffer.getFramebufferInfo()
            width, height = fbInfo.width, fbInfo.height
            sampleCount = SAMPLE_COUNTS[self.ui.AntiAliasingMode]

            if self.renderTargets is None or self.renderTargets.IsUpdateRequired(
                width, height, sampleCount
            ):
                self.renderTargets = RenderTargets()
                self.renderTargets.Init(device, width, height, sampleCount)
                self.bindingCache.Clear()
                self.gbufferPass.ResetBindingCache()
                self.deferredLightingPass.ResetBindingCache()

            self.SetupView(width, height)

            self.commandList.open()
            self.renderTargets.Clear(self.commandList)

            # RenderCompositeView takes a FramebufferFactory, NOT a Framebuffer
            # (src/cpp/_pydonut.cpp:2473), so pass GBufferFramebuffer -- the factory exposed by
            # Task 6 -- rather than calling GetFramebuffer(view) on it.
            gbufferContext = pyd.GBufferFillPassContext()
            pyd.RenderCompositeView(
                self.commandList,
                self.view,
                self.viewPrevious,
                self.renderTargets.gbuffer.GBufferFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                self.gbufferPass,
                gbufferContext,
                self.ui.EnableMaterialEvents,
            )

            deferredInputs = pyd.DeferredLightingPassInputs()
            deferredInputs.SetGBuffer(self.renderTargets.gbuffer)
            deferredInputs.SetLights(self.scene.GetSceneGraph().GetLights())
            deferredInputs.SetAmbientColors(
                self.ui.AmbientIntensity * 0.2,
                self.ui.AmbientIntensity * 0.2,
                self.ui.AmbientIntensity * 0.2,
                self.ui.AmbientIntensity * 0.1,
                self.ui.AmbientIntensity * 0.1,
                self.ui.AmbientIntensity * 0.1,
            )
            deferredInputs.output = self.renderTargets.HdrColor
            self.deferredLightingPass.Render(self.commandList, self.view, deferredInputs)

            self.m_CommonPasses.BlitTexture(
                self.commandList, framebuffer, self.renderTargets.HdrColor, self.bindingCache
            )

            self.commandList.close()
            device.executeCommandList(self.commandList)
```

The bound signature is `RenderCompositeView(commandList, view, viewPrev, framebufferFactory, rootNode, drawStrategy, pass, passContext, materialEvents=False)` (`src/cpp/_pydonut.cpp:2473-2484`). `threaded_rendering.py:244-247` is the working reference call site.

- [ ] **Step 6: Add the `__main__` bootstrap**

```python
    is_debug = "-debug" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    deviceParams.backBufferWidth = 1920
    deviceParams.backBufferHeight = 1080
    deviceParams.swapChainSampleCount = 1
    deviceParams.swapChainBufferCount = 3
    deviceParams.startFullscreen = False
    deviceParams.vsyncEnabled = True
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    uiData = UIData()
    example = FeatureDemo(deviceManager, uiData)

    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")
```

- [ ] **Step 7: Run it**

Run: `uv run feature_demo.py`
Expected: a 1920x1080 window titled "PyDonut Feature Demo" showing Sponza lit by a single directional light, navigable with WASD + mouse. No sky, no SSAO, no bloom, no tone mapping yet — the image will look flat and over-bright. That is correct for this task.

If it fails: the `RenderCompositeView` signature and all four `pyd.Format` enumerators used above (`RGBA16_FLOAT`, `RGBA16_SNORM`, `SRGBA8_UNORM`, `R8_UNORM`) were verified against the built module while writing this plan, so look first at scene loading (is `media/glTF-Sample-Assets/Models/Sponza/glTF/Sponza.gltf` actually present?) and at whether `Init()` returned `False` before the window ever opened.

- [ ] **Step 8: Commit**

```bash
git add feature_demo.py
git commit -m "Add feature_demo.py: Sponza through the deferred path"
```

---

### Task 9: Sky and SSAO

**Files:**
- Modify: `feature_demo.py`

**Interfaces:**
- Consumes: `RenderTargets`, `FeatureDemo` (Task 8); `pyd.SkyPass`/`pyd.SkyParameters` (Task 2); `pyd.SsaoPass`/`pyd.SsaoParameters` (Task 3)
- Produces: `FeatureDemo.CreateRenderPasses()` — the resize-time pass recreation hook that Tasks 10 and 11 extend

- [ ] **Step 1: Extract pass creation into `CreateRenderPasses`**

Add to `FeatureDemo`, and replace the inline `ResetBindingCache` calls in `Render` with a call to it:

```python
        def CreateRenderPasses(self: FeatureDemo) -> None:
            """Recreates every size-dependent pass. Called whenever RenderTargets is rebuilt."""
            device = self.GetDevice()
            assert self.renderTargets is not None

            self.bindingCache.Clear()
            self.gbufferPass.ResetBindingCache()
            self.deferredLightingPass.ResetBindingCache()

            self.skyPass = pyd.SkyPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.ForwardFramebuffer,
                self.view,
            )

            # SSAO is only available without MSAA: its compute path reads a single-sampled
            # depth buffer (FeatureDemo.cpp:825 guards on GetSampleCount() == 1).
            if self.renderTargets.gbuffer.GetSampleCount() == 1:
                self.ssaoPass = pyd.SsaoPass(
                    device,
                    self.shaderFactory,
                    self.m_CommonPasses,
                    self.renderTargets.gbuffer.Depth,
                    self.renderTargets.gbuffer.GBufferNormals,
                    self.renderTargets.AmbientOcclusion,
                )
            else:
                self.ssaoPass = None
```

Initialise `self.skyPass = None` and `self.ssaoPass = None` in `__init__`.

`CreateRenderPasses` needs `self.view` to exist, so in `Render` call `SetupView(width, height)` **before** `CreateRenderPasses()`.

- [ ] **Step 2: Render SSAO before deferred lighting**

In `Render`, between the G-buffer fill and the deferred lighting call:

```python
            if self.ui.EnableSsao and self.ssaoPass is not None:
                self.ssaoPass.Render(self.commandList, self.ui.SsaoParams, self.view)
```

And feed it into the lighting inputs, replacing the plain `deferredInputs.output` assignment block with:

```python
            deferredInputs.ambientOcclusion = (
                self.renderTargets.AmbientOcclusion
                if (self.ui.EnableSsao and self.ssaoPass is not None)
                else None
            )
            deferredInputs.output = self.renderTargets.HdrColor
```

**`ambientOcclusion` is not yet bound** — the field exists on the C++ `Inputs` struct (`extern/donut/include/donut/render/DeferredLightingPass.h:78`) but `DeferredLightingPassInputs` binds only `SetGBuffer`, `SetAmbientColors`, `SetLights` and `output` (`src/cpp/_pydonut.cpp:2341-2350`). Add it now, immediately after the existing `output` property and following its exact shape:

```cpp
        .def_property("ambientOcclusion",
            [](const PyDeferredLightingInputs &self) -> nvrhi::ITexture* { return self.ambientOcclusion; },
            [](PyDeferredLightingInputs &self, nvrhi::ITexture* tex) { self.ambientOcclusion = tex; },
            py::return_value_policy::reference)
```

And in `src/pydonut/_pydonut.pyi`, add to `class DeferredLightingPassInputs`:

```python
    # None disables the SSAO term. Only ever set when sampleCount == 1 -- SsaoPass does not
    # exist under MSAA.
    ambientOcclusion: Optional[Texture]
```

Rebuild with `uv sync --reinstall-package pydonut` before continuing, and commit this binding change together with this task.

- [ ] **Step 3: Render the sky after deferred lighting**

```python
            if self.ui.EnableProceduralSky and self.sunLight is not None:
                self.skyPass.Render(
                    self.commandList, self.view, self.sunLight, self.ui.SkyParams
                )
```

- [ ] **Step 4: Run and verify sky**

Run: `uv run feature_demo.py`
Expected: Sponza's open arches now show a graded blue procedural sky instead of black. Temporarily set `self.EnableProceduralSky = False` in `UIData.__init__`, re-run, and confirm the sky goes black — then set it back to `True`.

- [ ] **Step 5: Run and verify SSAO**

Temporarily set `self.EnableSsao = False` in `UIData.__init__`, re-run, and compare: with SSAO on, Sponza's arch undersides, column bases and the seams between pillars and floor should be visibly darker. Set it back to `True`.

- [ ] **Step 6: Commit**

```bash
git add feature_demo.py
git commit -m "Add procedural sky and SSAO to feature_demo.py"
```

---

### Task 10: Anti-aliasing, bloom and tone mapping

Completes the render graph. After this task the image is correctly exposed for the first time.

**Files:**
- Modify: `feature_demo.py`

**Interfaces:**
- Consumes: `CreateRenderPasses` (Task 9); `pyd.ToneMappingPass` (Task 4); `pyd.BloomPass` (Task 5); `CommandList.resolveTexture` (Task 6)
- Produces: a fully composed frame — `FeatureDemo.Render` ends by blitting `LdrColor`

- [ ] **Step 1: Create the TAA, tone mapping and bloom passes**

Add to `CreateRenderPasses`, after the SSAO block. Note the exposure-buffer handoff — it is what stops eye adaptation resetting to black on every window resize:

```python
            taaParams = pyd.TemporalAntiAliasingCreateParameters()
            taaParams.sourceDepth = self.renderTargets.gbuffer.Depth
            taaParams.motionVectors = self.renderTargets.gbuffer.MotionVectors
            taaParams.unresolvedColor = self.renderTargets.HdrColor
            taaParams.resolvedColor = self.renderTargets.ResolvedColor
            taaParams.feedback1 = self.renderTargets.TemporalFeedback1
            taaParams.feedback2 = self.renderTargets.TemporalFeedback2
            self.taaPass = pyd.TemporalAntiAliasingPass(
                device, self.shaderFactory, self.m_CommonPasses, self.view, taaParams
            )

            # Carry the outgoing pass's exposure buffer into its replacement, so eye adaptation
            # survives the resize instead of re-adapting from black (FeatureDemo.cpp:831-840).
            toneMappingParams = pyd.ToneMappingPassCreateParameters()
            if self.toneMappingPass is not None:
                toneMappingParams.exposureBufferOverride = self.toneMappingPass.GetExposureBuffer()
                self.exposureResetRequired = False
            else:
                self.exposureResetRequired = True

            self.toneMappingPass = pyd.ToneMappingPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.LdrFramebuffer,
                self.view,
                toneMappingParams,
            )

            self.bloomPass = pyd.BloomPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.ResolvedFramebuffer,
                self.view,
            )
```

Initialise `self.taaPass = None`, `self.toneMappingPass = None`, `self.bloomPass = None` and `self.exposureResetRequired = True` in `__init__`.

- [ ] **Step 1b: Release the new passes before reallocation**

None of the bound passes expose a binding-cache reset — `SkyPass`, `SsaoPass` and `BloomPass` have only `Render`; `TemporalAntiAliasingPass` has only `RenderMotionVectors`/`TemporalResolve`; `ToneMappingPass` has only `AdvanceFrame`/`GetExposureBuffer`/`ResetExposure`/`SimpleRender`. Dropping the Python reference is therefore the ONLY way to release the internal binding sets that reference the old render targets. Any pass left assigned across `RenderTargets.Init()` keeps its old textures resident while the new ones are allocated.

Extend the inline release block in `Render` (the one that sets `self.renderTargets = None` and clears the three binding caches) so it also releases this task's passes:

```python
                self.taaPass = None
                self.bloomPass = None
```

`self.toneMappingPass` needs different handling, because `CreateRenderPasses` reads its exposure buffer to carry eye adaptation across the rebuild — nulling it naively would silently reset adaptation on every resize. Capture the buffer first, then release:

```python
                # GetExposureBuffer is return_value_policy::reference_internal, so holding the
                # buffer keeps the old pass alive until the new one AddRefs it -- capturing
                # before releasing is what makes this safe rather than a dangling handle.
                self.pendingExposureBuffer = (
                    self.toneMappingPass.GetExposureBuffer()
                    if self.toneMappingPass is not None
                    else None
                )
                self.toneMappingPass = None
```

Initialise `self.pendingExposureBuffer = None` in `__init__`, and in `CreateRenderPasses` drive the exposure handoff from it instead of from `self.toneMappingPass`:

```python
            toneMappingParams = pyd.ToneMappingPassCreateParameters()
            if self.pendingExposureBuffer is not None:
                toneMappingParams.exposureBufferOverride = self.pendingExposureBuffer
                self.exposureResetRequired = False
            else:
                self.exposureResetRequired = True
            self.pendingExposureBuffer = None
```

- [ ] **Step 2: Advance the tone mapping frame clock**

In `Animate`, after the camera update:

```python
            if self.toneMappingPass is not None:
                self.toneMappingPass.AdvanceFrame(elapsedTimeSeconds)
```

- [ ] **Step 3: Reset exposure on the first frame after a rebuild**

In `Render`, right after `self.commandList.open()`:

```python
            if self.exposureResetRequired:
                self.toneMappingPass.ResetExposure(self.commandList, 0.5)
```

- [ ] **Step 4: Add the resolve / bloom / tone map tail**

Replace the `BlitTexture` call at the end of `Render` with:

```python
            finalHdrColor = self.renderTargets.HdrColor
            finalHdrFramebuffer = self.renderTargets.HdrFramebuffer

            if self.ui.AntiAliasingMode == AntiAliasingMode.TEMPORAL:
                if self.previousViewsValid:
                    self.taaPass.RenderMotionVectors(
                        self.commandList, self.view, self.viewPrevious
                    )
                self.taaPass.TemporalResolve(
                    self.commandList,
                    self.ui.TemporalAntiAliasingParams,
                    self.previousViewsValid,
                    self.view,
                    self.view,
                )
                finalHdrColor = self.renderTargets.ResolvedColor
                finalHdrFramebuffer = self.renderTargets.ResolvedFramebuffer
                self.previousViewsValid = True
            else:
                if self.renderTargets.gbuffer.GetSampleCount() > 1:
                    self.commandList.resolveTexture(
                        self.renderTargets.ResolvedColor, self.renderTargets.HdrColor
                    )
                    finalHdrColor = self.renderTargets.ResolvedColor
                    finalHdrFramebuffer = self.renderTargets.ResolvedFramebuffer
                self.previousViewsValid = False

            if self.ui.EnableBloom:
                self.bloomPass.Render(
                    self.commandList,
                    finalHdrFramebuffer,
                    self.view,
                    finalHdrColor,
                    self.ui.BloomSigma,
                    self.ui.BloomAlpha,
                )

            toneMappingParams = self.ui.ToneMappingParams
            if self.exposureResetRequired:
                toneMappingParams.eyeAdaptationSpeedUp = 0.0
                toneMappingParams.eyeAdaptationSpeedDown = 0.0
                self.exposureResetRequired = False

            self.toneMappingPass.SimpleRender(
                self.commandList, toneMappingParams, self.view, finalHdrColor
            )

            self.m_CommonPasses.BlitTexture(
                self.commandList, framebuffer, self.renderTargets.LdrColor, self.bindingCache
            )
```

- [ ] **Step 5: Copy the view into `viewPrevious` each frame**

At the very end of `Render`, after `executeCommandList`, TAA needs last frame's matrices:

```python
            self.viewPrevious = pyd.PlanarView(self.view)
```

- [ ] **Step 6: Run and verify tone mapping**

Run: `uv run feature_demo.py`
Expected: the image is now correctly exposed rather than blown out. Look away from the bright arches toward a dark corner and back — the exposure should visibly adapt over roughly a second.

- [ ] **Step 7: Run and verify bloom**

Temporarily set `self.BloomAlpha = 0.5` in `UIData.__init__` and re-run: bright sky visible through the arches should bleed a halo into the surrounding stone. Set it back to `0.05`.

- [ ] **Step 8: Verify each AA mode**

Temporarily set `self.AntiAliasingMode` in `UIData.__init__` to each of `AntiAliasingMode.NONE`, `MSAA_2X`, `MSAA_4X`, `MSAA_8X`, and `TEMPORAL` in turn, running `uv run feature_demo.py -debug` each time.
Expected: all five present without validation-layer errors in the console. `MSAA_*` is the only path that exercises `resolveTexture`; `NONE` and the MSAA modes should show no SSAO (correctly — SSAO requires sampleCount 1, so only `NONE`... note `NONE` *is* sampleCount 1 and does keep SSAO). Restore `TEMPORAL`.

- [ ] **Step 9: Verify the resize exposure handoff**

Run `uv run feature_demo.py`, let the exposure settle, then drag the window edge to resize it.
Expected: the image does **not** flash black and re-adapt. If it does, `exposureBufferOverride` is not being threaded through `CreateRenderPasses` correctly.

- [ ] **Step 10: Commit**

```bash
git add feature_demo.py
git commit -m "Add TAA/MSAA, bloom and tone mapping to feature_demo.py"
```

---

### Task 11: The UI panel

**Files:**
- Modify: `feature_demo.py`

**Interfaces:**
- Consumes: `UIData` (Task 8), the new ImGui widgets (Task 7)
- Produces: `UIRenderer(pyd.ImGui_Renderer)` — added to the device manager after `FeatureDemo`

- [ ] **Step 1: Add the `UIRenderer` class**

```python
    class UIRenderer(pyd.ImGui_Renderer):
        def __init__(
            self: UIRenderer, deviceManager: pyd.DeviceManager, app: FeatureDemo, ui: UIData
        ) -> None:
            super().__init__(deviceManager)
            self.app = app
            self.ui = ui
            pyd.ImGui.DisableIniFile()

        def buildUI(self: UIRenderer) -> None:
            if not self.ui.ShowUI:
                return

            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Settings", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            _, self.ui.UseDeferredShading = pyd.ImGui.Checkbox(
                "Deferred Shading", self.ui.UseDeferredShading
            )

            aaNames = [m.name for m in AntiAliasingMode]
            changed, index = pyd.ImGui.Combo(
                "AA Mode", int(self.ui.AntiAliasingMode), aaNames
            )
            if changed:
                self.ui.AntiAliasingMode = AntiAliasingMode(index)

            _, self.ui.AmbientIntensity = pyd.ImGui.SliderFloat(
                "Ambient Intensity", self.ui.AmbientIntensity, 0.0, 2.0
            )

            if pyd.ImGui.CollapsingHeader("Sky"):
                _, self.ui.EnableProceduralSky = pyd.ImGui.Checkbox(
                    "Procedural Sky", self.ui.EnableProceduralSky
                )
                _, self.ui.SkyParams.brightness = pyd.ImGui.SliderFloat(
                    "Brightness", self.ui.SkyParams.brightness, 0.0, 1.0
                )
                _, self.ui.SkyParams.glowSize = pyd.ImGui.SliderFloat(
                    "Glow Size", self.ui.SkyParams.glowSize, 0.0, 90.0
                )
                _, self.ui.SkyParams.glowIntensity = pyd.ImGui.SliderFloat(
                    "Glow Intensity", self.ui.SkyParams.glowIntensity, 0.0, 1.0
                )

            if pyd.ImGui.CollapsingHeader("SSAO"):
                _, self.ui.EnableSsao = pyd.ImGui.Checkbox("Enabled", self.ui.EnableSsao)
                if self.app.ssaoPass is None:
                    pyd.ImGui.SameLine()
                    pyd.ImGui.Text("(unavailable under MSAA)")
                _, self.ui.SsaoParams.amount = pyd.ImGui.SliderFloat(
                    "Amount", self.ui.SsaoParams.amount, 0.0, 8.0
                )
                _, self.ui.SsaoParams.radiusWorld = pyd.ImGui.SliderFloat(
                    "Radius", self.ui.SsaoParams.radiusWorld, 0.01, 2.0
                )
                _, self.ui.SsaoParams.surfaceBias = pyd.ImGui.SliderFloat(
                    "Surface Bias", self.ui.SsaoParams.surfaceBias, 0.0, 1.0
                )
                _, self.ui.SsaoParams.powerExponent = pyd.ImGui.SliderFloat(
                    "Power Exponent", self.ui.SsaoParams.powerExponent, 1.0, 4.0
                )

            if pyd.ImGui.CollapsingHeader("Bloom"):
                _, self.ui.EnableBloom = pyd.ImGui.Checkbox("Enabled", self.ui.EnableBloom)
                _, self.ui.BloomSigma = pyd.ImGui.SliderFloat(
                    "Sigma", self.ui.BloomSigma, 1.0, 100.0
                )
                _, self.ui.BloomAlpha = pyd.ImGui.SliderFloat(
                    "Alpha", self.ui.BloomAlpha, 0.0, 1.0
                )

            if pyd.ImGui.CollapsingHeader("Tone Mapping"):
                _, self.ui.ToneMappingParams.exposureBias = pyd.ImGui.SliderFloat(
                    "Exposure Bias", self.ui.ToneMappingParams.exposureBias, -4.0, 4.0
                )
                _, self.ui.ToneMappingParams.whitePoint = pyd.ImGui.SliderFloat(
                    "White Point", self.ui.ToneMappingParams.whitePoint, 0.1, 10.0
                )
                _, self.ui.ToneMappingParams.eyeAdaptationSpeedUp = pyd.ImGui.SliderFloat(
                    "Adaptation Up", self.ui.ToneMappingParams.eyeAdaptationSpeedUp, 0.0, 4.0
                )
                _, self.ui.ToneMappingParams.eyeAdaptationSpeedDown = pyd.ImGui.SliderFloat(
                    "Adaptation Down", self.ui.ToneMappingParams.eyeAdaptationSpeedDown, 0.0, 4.0
                )

            pyd.ImGui.End()
```

- [ ] **Step 2: Add the forward-shading path**

The UI now exposes a "Deferred Shading" toggle, so `Render` must honour it. Create a `ForwardShadingPass` in `Init` alongside the G-buffer pass:

```python
            self.forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
            self.forwardPass.Init(
                self.shaderFactory, pyd.ForwardShadingPassCreateParameters()
            )
```

Add `self.forwardPass = None` to `__init__` and `self.forwardPass.ResetBindingCache()` to `CreateRenderPasses`.

Then in `Render`, wrap the G-buffer fill + deferred lighting block in a branch. `threaded_rendering.py:235-247` is the working reference for the forward call shape:

```python
            ambient = self.ui.AmbientIntensity
            if self.ui.UseDeferredShading:
                gbufferContext = pyd.GBufferFillPassContext()
                pyd.RenderCompositeView(
                    self.commandList,
                    self.view,
                    self.viewPrevious,
                    self.renderTargets.gbuffer.GBufferFramebuffer,
                    self.scene.GetSceneGraph().GetRootNode(),
                    self.opaqueDrawStrategy,
                    self.gbufferPass,
                    gbufferContext,
                    self.ui.EnableMaterialEvents,
                )

                if self.ui.EnableSsao and self.ssaoPass is not None:
                    self.ssaoPass.Render(self.commandList, self.ui.SsaoParams, self.view)

                deferredInputs = pyd.DeferredLightingPassInputs()
                deferredInputs.SetGBuffer(self.renderTargets.gbuffer)
                deferredInputs.SetLights(self.scene.GetSceneGraph().GetLights())
                deferredInputs.SetAmbientColors(
                    ambient * 0.2, ambient * 0.2, ambient * 0.2,
                    ambient * 0.1, ambient * 0.1, ambient * 0.1,
                )
                deferredInputs.ambientOcclusion = (
                    self.renderTargets.AmbientOcclusion
                    if (self.ui.EnableSsao and self.ssaoPass is not None)
                    else None
                )
                deferredInputs.output = self.renderTargets.HdrColor
                self.deferredLightingPass.Render(self.commandList, self.view, deferredInputs)
            else:
                # Forward opaque. PrepareLights takes the light list plus the same ambient
                # top/bottom colours the deferred path passes to SetAmbientColors.
                forwardContext = pyd.ForwardShadingPassContext()
                self.forwardPass.PrepareLights(
                    forwardContext,
                    self.commandList,
                    self.scene.GetSceneGraph().GetLights(),
                    ambient * 0.2, ambient * 0.2, ambient * 0.2,
                    ambient * 0.1, ambient * 0.1, ambient * 0.1,
                )
                pyd.RenderCompositeView(
                    self.commandList,
                    self.view,
                    self.viewPrevious,
                    self.renderTargets.ForwardFramebuffer,
                    self.scene.GetSceneGraph().GetRootNode(),
                    self.opaqueDrawStrategy,
                    self.forwardPass,
                    forwardContext,
                    self.ui.EnableMaterialEvents,
                )

                if self.ui.EnableTranslucency:
                    pyd.RenderCompositeView(
                        self.commandList,
                        self.view,
                        self.viewPrevious,
                        self.renderTargets.ForwardFramebuffer,
                        self.scene.GetSceneGraph().GetRootNode(),
                        self.transparentDrawStrategy,
                        self.forwardPass,
                        forwardContext,
                        self.ui.EnableMaterialEvents,
                    )
```

The standalone SSAO call and `deferredInputs` block added in Task 9 are now inside the deferred branch — delete the old top-level copies rather than leaving them duplicated.

- [ ] **Step 3: Wire the UI renderer into the bootstrap**

Replace the render-pass registration block in `__main__` with:

```python
    uiData = UIData()
    example = FeatureDemo(deviceManager, uiData)
    gui = UIRenderer(deviceManager, example, uiData)

    if example.Init() and gui.Init(example.shaderFactory):
        deviceManager.AddRenderPassToBack(example)
        deviceManager.AddRenderPassToBack(gui)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(gui)
        deviceManager.RemoveRenderPass(example)
```

- [ ] **Step 4: Run and exercise every control**

Run: `uv run feature_demo.py`
Expected, each verified by hand:
- The "Settings" window appears top-left with four collapsing sections.
- "Deferred Shading" unchecked switches to the forward path; the image stays recognisable (translucent geometry appears).
- The AA Mode combo switches between all five modes live, rebuilding render targets each time.
- Under MSAA modes, the SSAO section shows "(unavailable under MSAA)" next to its checkbox.
- Every slider moves its effect in real time: sky brightness, SSAO amount/radius, bloom sigma/alpha, exposure bias.

- [ ] **Step 5: Run once under the debug layers**

Run: `uv run feature_demo.py -debug`
Expected: no D3D debug-layer or NVRHI validation errors in the console while cycling every AA mode and toggling every checkbox.

- [ ] **Step 6: Confirm the binding tests still pass**

Run: `uv run pytest -v`
Expected: 21 passed.

- [ ] **Step 7: Commit**

```bash
git add feature_demo.py
git commit -m "Add the settings UI and forward-shading path to feature_demo.py"
```

---

## Stage 1 Done

At this point `feature_demo.py` renders Sponza through both shading paths with sky, SSAO, TAA/MSAA, bloom and tone mapping, driven by a live settings panel, and `uv run pytest` covers the binding surface. Stage 2 (shadows, scene cameras, material/light editors) gets its own spec and plan.
