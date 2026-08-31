# FeatureDemo port, Stage 1: the post-processing chain — design

## Goal

Begin porting `E:\Gits\Donut-Samples\feature_demo\FeatureDemo.cpp` (1846 lines — Donut's
kitchen-sink sample) to `feature_demo.py`, by binding the four post-processing passes it needs
and building the example up to the point where it renders `media/sponza-plus.scene.json` through
the full HDR pipeline *minus shadows*.

This is stage 1 of 3. The staging decision, and the contents of each stage, are recorded in
[Staging](#staging) below.

## Staging

`FeatureDemo.cpp` needs roughly fifteen new binding groups. Landing them in one change would
mean a single large plan with no runnable checkpoint until the very end, so the port is split
into three sub-projects, each with its own spec, plan, and implementation cycle, and each
ending in a `feature_demo.py` that actually runs:

| Stage | Adds | Example state at end of stage |
| --- | --- | --- |
| **1 (this spec)** | `SkyPass`, `SsaoPass`, `ToneMappingPass`, `BloomPass`, the `IView`/`ICompositeView` bases, `GBufferRenderTargets` accessors | Sponza, deferred + forward paths, sky, SSAO, TAA/MSAA, bloom, tone mapping |
| **2** | `CascadedShadowMap`, `IShadowMap`, `DepthPass`, `SceneCamera`/`PerspectiveCamera`, `SpotLight`/`PointLight`, `UserInterfaceUtils` editors | + shadows, scene-camera dropdown, material/light editing |
| **3** | `LightProbeProcessingPass` + `LightProbe`, `PixelReadbackPass`, `MipMapGenPass`, `MaterialIDPass`, `StereoPlanarView`, screenshots | The complete port |

`feature_demo.py` is created in stage 1 and **grown** by stages 2 and 3, rather than each stage
producing a throwaway example that stage 3 replaces.

Permanently out of scope, in every stage:

- ~~**DLSS** (18 references in the original) — needs the NGX SDK, which this repo does not
  vendor. The AA dropdown therefore ships as `NONE / TEMPORAL / MSAA_2X / MSAA_4X / MSAA_8X`,
  with no `DLSS` entry at all rather than a permanently-greyed one.~~

  > **Superseded 2026-08-31 — DLSS is now ported.** The premise above no longer holds: the
  > NGX SDK is vendored on demand by donut's own `DONUT_WITH_DLSS=ON` option, which clones it
  > at configure time, so nothing had to be committed to this repo. `pyd.DLSS` and its two
  > parameter structs are bound, and `feature_demo.py` offers DLSS as an AA mode.
  >
  > The dropdown reasoning above survived intact and is the shape actually implemented: the
  > entry is *omitted*, never greyed — it appears only when the SDK is compiled in **and**
  > NGX initialises on the running machine (`UIData.DlssAvailable`). A default build still
  > ships exactly the five modes listed above.
  >
  > It is configured for DLAA (input size == output size), matching the C++ sample; it is not
  > used as an upscaler. See the "Optional: DLSS" section of `README.md` for the build flag,
  > and `test/test_dlss_bindings.py` for the optional-name contract.
- **taskflow** — the original's `#ifdef DONUT_WITH_TASKFLOW` parallel scene load.
- **`ImGui_Console` / `ConsoleInterpreter` / `ConsoleObjects`** — a whole second UI subsystem
  that demonstrates nothing about rendering.

## What stage 1 does *not* have to build

Two things that looked like stage-1 blockers during brainstorming turned out to be already
solved, and this design deliberately does not touch either:

**No `GBufferRenderTargets` trampoline is needed.** The C++ `RenderTargets` derives from
`GBufferRenderTargets` and overrides `Init` (`FeatureDemo.cpp:77-103`), which would normally
imply a pybind11 trampoline so Python can subclass it. It does not, because the only place the
derived object is used *polymorphically* is `deferredInputs.SetGBuffer(*m_RenderTargets)`
(`FeatureDemo.cpp:1016`) — and the existing `DeferredLightingPassInputs.SetGBuffer` binding
(`_pydonut.cpp:2343`) already accepts a plain `GBufferRenderTargets`. `deferred_shading.py:294`
establishes the pattern: hold a `pyd.GBufferRenderTargets()` by **composition** and add the
extra textures alongside it. Stage 1 follows that.

**The shaders are already built.** All four passes load framework shaders from
`/shaders/donut/passes/`, and those binaries are already present in the repo:
`bin/shaders/framework/{dxil,dxbc,spirv}/passes/` contains `sky_ps.bin`,
`ssao_deinterleave_cs.bin`, `ssao_compute_cs.bin`, `ssao_blur_cs.bin`, `tonemapping_ps.bin`, and
`bloom_ps.bin`. No shader build work is in scope.

## The view hierarchy

All four new passes take `const engine::ICompositeView&`, and the original holds its view as
`std::shared_ptr<IView>` (`FeatureDemo.cpp:314`) precisely so it can swap in a
`StereoPlanarView` (`FeatureDemo.cpp:724`). The real hierarchy is:

```text
ICompositeView                (View.h:46)
└── IView                     (View.h:55)
    ├── PlanarView            (View.h:87)
    └── CubemapView           (View.h:339)
```

The current binding knows `PlanarView` and `CubemapView` only as unrelated concrete types, and
every pass signature hardcodes `PlanarView&`.

**Decision: register the bases.** Add `py::class_<ICompositeView>` and
`py::class_<IView, ICompositeView>`, and re-declare `PlanarView` and `CubemapView` as deriving
from `IView`. The four new passes then take `IView&`.

This costs about ten lines and breaks nothing — `PlanarView` still converts everywhere it did
before. The alternative (binding the new passes concretely against `PlanarView&`, matching the
current convention) would force all four signatures to be reworked or overloaded in stage 3,
where `StereoPlanarView` and the `CubemapView`-based `LightProbeProcessingPass` both arrive.
This mirrors the reasoning already recorded at `_pydonut.cpp:2282-2290` for registering
`IDrawStrategy`/`IGeometryPass` as real polymorphic bases once a second concrete implementation
of each appeared.

**Existing signatures are left alone.** `RenderView`, `RenderCompositeView`,
`FramebufferFactory.GetFramebuffer` and `GBufferRenderTargets.GetFramebuffer` keep taking
`PlanarView&`. Widening them buys nothing until stage 3 and would be churn for its own sake.

## New native bindings (`src/cpp/_pydonut.cpp`)

Each pass is bound to exactly the surface `FeatureDemo.cpp` calls. Unused constructors and
methods are listed below as explicitly skipped, so a later stage that needs one knows it was a
decision rather than an oversight.

### `SkyParameters` + `SkyPass`

`SkyParameters` (`SkyPass.h`) has four `dm::float3` fields and six floats. Donut math types are
deliberately not exposed to Python anywhere in this binding, so the `float3`s follow the
existing flat-scalar convention set by `DeferredLightingPassInputs.SetAmbientColors`
(`_pydonut.cpp:2344`):

- `SetSkyColor(r, g, b)`, `SetHorizonColor(r, g, b)`, `SetGroundColor(r, g, b)`,
  `SetDirectionUp(x, y, z)`
- `brightness`, `horizonSize`, `glowSize`, `glowIntensity`, `glowSharpness`,
  `maxLightRadiance` as plain `def_readwrite`

`SkyPass`:

- ctor `(device, shaderFactory, commonPasses, framebufferFactory, view)`
- `Render(commandList, view, light, params)` — `light` is a `DirectionalLight`, already bound
- **Skipped:** `FillShaderParameters` (a static helper the sample never calls)

### `SsaoParameters` + `SsaoPass`

`SsaoParameters` is seven plain scalar/bool fields — bound directly with `def_readwrite`, no
flattening needed.

`SsaoPass` has two constructors. Only the texture-taking one is bound:

- ctor `(device, shaderFactory, commonPasses, gbufferDepth, gbufferNormals, destinationTexture)`
  — this is what `FeatureDemo.cpp:827` uses
- `Render(commandList, params, view)` — `bindingSetIndex` stays at its default of 0
- **Skipped:** the `CreateParameters`-taking constructor, the `CreateParameters` struct itself
  (which contains a `dm::int2` that would need flattening), and `CreateBindingSet`. These exist
  for callers that manage several binding sets across views; the sample uses none of it.

### `ToneMappingParameters` + `ToneMappingPassCreateParameters` + `ToneMappingPass`

`ToneMappingParameters` is nine plain fields — bound directly.

`ToneMappingPassCreateParameters` binds `isTextureArray`, `histogramBins`,
`numConstantBufferVersions`, and `exposureBufferOverride`. **Skipped:** `colorLUT`, which the
sample never sets.

`exposureBufferOverride` is not optional detail — it is the mechanism by which eye adaptation
survives a window resize. `FeatureDemo.cpp:831-840` reads the old pass's exposure buffer before
destroying it and threads it into the new pass's create parameters; without that, every resize
would visibly re-adapt from scratch. `feature_demo.py` reproduces this.

`ToneMappingPass`:

- ctor `(device, shaderFactory, commonPasses, framebufferFactory, view, params)`
- `SimpleRender(commandList, params, view, sourceTexture)`
- `AdvanceFrame(frameTime)`, `ResetExposure(commandList, initialExposure)`, `GetExposureBuffer()`
- **Skipped:** `Render`, `ResetHistogram`, `AddFrameToHistogram`, `ComputeExposure`. The sample
  drives tone mapping exclusively through `SimpleRender` (`FeatureDemo.cpp:1158`), which
  performs the histogram/exposure steps internally.

### `BloomPass`

- ctor `(device, shaderFactory, commonPasses, framebufferFactory, view)`
- `Render(commandList, framebufferFactory, view, sourceDestTexture, sigmaInPixels, blendFactor)`

The framebuffer factory is passed **both** at construction and at each `Render` call, because
the sample renders bloom into different targets depending on the AA mode — the resolved
framebuffer on the TAA path (`FeatureDemo.cpp:1128`) and the HDR-or-resolved framebuffer on the
MSAA path (`FeatureDemo.cpp:1146`). Both parameters are bound.

### `GBufferRenderTargets` accessors

The existing binding (`_pydonut.cpp:2298-2314`) exposes only `Init`, `Clear`, `width`, `height`
and `GetFramebuffer`. Stage 1 adds read-only properties for the public members declared in
`GBuffer.h`, which the new passes and the render graph consume by name:

- `Depth`, `GBufferDiffuse`, `GBufferSpecular`, `GBufferNormals`, `GBufferEmissive`,
  `MotionVectors` — textures, `return_value_policy::reference`
- `GBufferFramebuffer` — the `FramebufferFactory`
- `GetSampleCount()`, `GetUseReverseProjection()`

`IsUpdateRequired` is **not** added: it is not a `GBufferRenderTargets` method at all, but one
the sample's own derived class defines. `feature_demo.py` implements it in Python.

### `CommandList.resolveTexture`

Not currently bound, and the MSAA anti-aliasing modes need it to resolve the multisampled HDR
target before bloom (`FeatureDemo.cpp:1139`). Bound as a thin wrapper alongside the existing
command-list methods, taking `(dest, destSubresources, src, srcSubresources)`.

### ImGui additions

The sample's `UIRenderer` uses five ImGui functions that the binding does not yet have:
`SliderFloat`, `DragFloat`, `CollapsingHeader`, `SameLine`, and `SetItemDefaultFocus`. These
join the existing `def_static` set on the `ImGui` class.

The original's sixth, `ImGui::TextUnformatted`, needs nothing: the existing `ImGui.Text` binding
(`_pydonut.cpp:2753-2755`) already calls `TextUnformatted` internally, deliberately, so that
Python string content can never be interpreted as a printf format string.

`PushFont`/`PopFont`/`GetFontSize`/`GetIO` are used by the original's console and its
scaled-font handling; since the console is out of scope, they are not bound.

## `feature_demo.py`

The file mirrors the C++ layout so that stages 2 and 3 slot in by accretion rather than
restructuring.

### `RenderTargets`

A plain Python class — not a `pyd.GBufferRenderTargets` subclass — owning:

- a `pyd.GBufferRenderTargets` instance (the base's targets)
- `HdrColor`, `LdrColor`, `ResolvedColor`, `TemporalFeedback1`, `TemporalFeedback2`,
  `AmbientOcclusion`
- four `FramebufferFactory` instances: `ForwardFramebuffer`, `HdrFramebuffer`, `LdrFramebuffer`,
  `ResolvedFramebuffer`. The original's fifth, `MaterialIDFramebuffer`, arrives in stage 3 with
  `MaterialIDPass`.
- `IsUpdateRequired(width, height, sampleCount)` and `Clear(commandList)`

Omitted this stage: `MaterialIDs` (stage 3, with `MaterialIDPass`) and the `nvrhi::HeapHandle`
virtual-resource path (`FeatureDemo.cpp:110`), which needs `createHeap`/`bindTextureMemory`
bindings that nothing else in this repo uses. Textures are created non-virtual.

### `UIData`

The stage-1 subset of the C++ struct (`FeatureDemo.cpp:241-278`): the pass toggles and
parameter blocks for sky, SSAO, tone mapping, TAA and bloom, plus `UseDeferredShading`,
`AntiAliasingMode`, `EnableVsync`, `EnableTranslucency`, `EnableMaterialEvents`,
`AmbientIntensity`, `EnableAnimations`, and `ShaderReloadRequested`. Shared by reference between
the app and the UI renderer, matching how `work_graphs.py`, `rt_particles.py` and
`aftermath.py` already share their `UIData`.

Shadow, light-probe, material-selection, scene-camera and screenshot fields are added by later
stages.

### `FeatureDemo(pyd.ApplicationBase)`

The `ApplicationBase` trampoline already exposes everything the sample's scene loading needs —
`BeginLoadingScene`, `LoadScene`, `SceneUnloading`, `SceneLoaded`,
`SetAsynchronousLoadingEnabled`, `IsSceneLoading`, `IsSceneLoaded`, `m_TextureCache`,
`m_CommonPasses` (`_pydonut.cpp:2684-2721`).

Key methods:

- `SetupView` — builds the `PlanarView` / previous-`PlanarView` pair and applies the TAA jitter.
  Stereo is stage 3, so only the planar branch of `FeatureDemo.cpp:696-780` is ported.
- `CreateRenderPasses` — recreates the four new passes plus the existing GBuffer/deferred/
  forward/TAA passes on resize, threading the old exposure buffer through
  `exposureBufferOverride` as described above.
- `Render` — the original's order exactly: clear → GBuffer fill *or* forward opaque → SSAO →
  deferred lighting → sky → TAA resolve *or* MSAA `resolveTexture` → bloom → tone-map
  `SimpleRender` → `BlitTexture` the LDR result to the swap chain.

### The sun light

`media/sponza-plus.scene.json` declares **no lights whatsoever** — it is two glTF models and a
transform graph. So the synthesised-sun branch of `FeatureDemo.cpp:619-627` is not a fallback
here, it is the only path that ever runs.

Everything it needs is already bound: `DirectionalLight` has `py::init<>()`, `irradiance` and
`angularSize` (`_pydonut.cpp:2231-2234`), `SetDirection(x, y, z)` is inherited from `Light`
(`_pydonut.cpp:2219`), and `SceneGraphNode.SetName`/`SetLeaf` (`_pydonut.cpp:2247-2248`) plus
`SceneGraph.AttachLeafNode` (`_pydonut.cpp:2259`) attach it. No new binding is required.

### `UIRenderer(pyd.ImGui_Renderer)`

The stage-1 subset of `FeatureDemo.cpp:1436-1730`: the AA mode combo, the deferred/forward
toggle, and collapsing sections for sky, SSAO, tone mapping and bloom, each driving its
parameter block in `UIData`.

## Testing

These are visual render passes with no meaningful unit-test surface, and no example in this
repo has automated tests. Verification is therefore by running the example, consistent with
existing practice:

1. `_pydonut` builds clean with the new bindings.
2. `feature_demo.py` loads `media/sponza-plus.scene.json` and presents a lit frame.
3. Each of the four new passes visibly changes output when toggled: sky on/off, SSAO on/off,
   bloom on/off, and tone-mapping exposure responding to its sliders.
4. Both shading paths render (deferred and forward).
5. Each AA mode runs without validation errors — in particular the MSAA path, which is the only
   consumer of the new `resolveTexture` binding.
6. Window resize preserves eye adaptation rather than re-adapting from black.

Type stubs in `src/pydonut/_pydonut.pyi` and re-exports in `src/pydonut/__init__.py` are kept in
sync with every new binding, matching the existing convention.

## Risks

**Async scene loading.** `ApplicationBase::SetAsynchronousLoadingEnabled` is bound, but no
existing example exercises the async path from a Python subclass with a scene this large. If
the loading-screen path misbehaves under Python, stage 1 falls back to synchronous loading
(`SetAsynchronousLoadingEnabled(False)`) and the async path becomes its own investigation
rather than blocking the example.

**MSAA and SSAO are mutually exclusive.** `FeatureDemo.cpp:825` only creates `SsaoPass` when
`GetSampleCount() == 1`. The UI must reflect that rather than offering a toggle that silently
does nothing when an MSAA mode is selected.
