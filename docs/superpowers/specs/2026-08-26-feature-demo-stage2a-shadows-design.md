# FeatureDemo port, Stage 2a: sun shadows — design

## Goal

Give `feature_demo.py` cascaded shadow maps from its synthesised sun, on both the deferred and
forward shading paths, with a live toggle between the two cascade fits Donut offers.

This is stage 2a. Stage 1 (the post-processing chain) is complete and landed; see
[`2026-08-25-feature-demo-stage1-design.md`](2026-08-25-feature-demo-stage1-design.md), whose
[Staging](2026-08-25-feature-demo-stage1-design.md#staging) table this spec amends.

## Re-staging

Stage 1's table put shadows, scene cameras and the material/light editors in one stage 2. They
are three independent features, and shadows alone are comparable in size to all of stage 1 — a
new pass type, a render target the back-buffer resize path must *not* own, per-light wiring,
both shading paths, and its own UI section. Bundling them means a large plan with no runnable
checkpoint until near the end, which is the failure mode the original staging section exists to
avoid. So stage 2 splits:

| Stage | Adds | Example state at end of stage |
| --- | --- | --- |
| **2a (this spec)** | `IShadowMap`, `CascadedShadowMap`, `DepthPass`, `Light.shadowMap`, widened `RenderCompositeView` | + sun shadows on both shading paths |
| **2b** | `SceneCamera`/`PerspectiveCamera`, `SpotLight`/`PointLight`, `UserInterfaceUtils` editors | + scene-camera dropdown, material/light editing, added lights |
| **3** | unchanged from stage 1's table | The complete port |

`SpotLight` and `PointLight` move to 2b deliberately. `media/sponza-plus.scene.json` declares no
lights at all, so nothing loads into them; the feature that makes them reachable is 2b's "add a
light to the scene", and the light editor is what drives them. Binding two classes that nothing
constructs is not worth a stage.

## How shadows attach

The whole consumption path is one assignment. `engine::Light` owns a
`std::shared_ptr<IShadowMap> shadowMap` (`SceneGraph.h:185`), and both lighting passes read it
themselves — `DeferredLightingPass.cpp:163-192` pulls the texture, the texture size and the
per-cascade constants straight off each light. There is no shadow input on
`DeferredLightingPassInputs` to plumb, and `ForwardShadingPass::PrepareLights` behaves the same
way.

Two consequences shape the rest of this design:

- **`Light.shadowMap = None` is the shadow toggle.** No pass needs recreating, no binding cache
  needs clearing, and the passes take the no-shadow path on the very next frame.
- **All shadow-casting lights must share one shadow map texture.** `DeferredLightingPass.cpp:172`
  asserts on the second distinct texture. One sun makes this moot here, but 2b's added lights
  will have to reuse this map's per-object slices rather than allocate their own.

## New native bindings (`src/cpp/_pydonut.cpp`)

As in stage 1: bound to exactly the surface the example calls, with every skipped member listed
so a later stage can tell a decision from an oversight.

### `IShadowMap`

Registered as a polymorphic base with **no methods bound**, exactly as `ICompositeView` was in
stage 1. It exists so `Light.shadowMap` has a type to accept and so `CascadedShadowMap` can
derive from it on the Python side. Everything the interface declares
(`GetWorldToUvzwMatrix`, `FillShadowConstants`, `GetUVRange`, `GetFadeRangeInTexels`,
`IsLitOutOfBounds`, `GetCascade`, `GetPerObjectShadow`) is called by the lighting passes in C++,
never from Python.

### `CascadedShadowMap`

Constructor `(device, resolution, numCascades, numPerObjectShadows, format, isUAV=False)`.

The example builds it as `numPerObjectShadows=0`, `format=Format.D32`, `isUAV=False`. D32 over
D16 for precision: at 2048² × 4 cascades the difference is 64 MB against 32 MB, which is not
worth trading shadow acne for. The constructor asserts `0 < numCascades <= 4`
(`CascadedShadowMap.cpp:40-41`), so the UI's cascade slider is clamped to that range.

Bound methods:

- `SetupForPlanarView(light, view, maxShadowDistance, lightSpaceZUp, lightSpaceZDown, exponent=4.0)`
- `SetupForPlanarViewStable(light, view, maxShadowDistance, lightSpaceZUp, lightSpaceZDown, exponent=4.0)`
- `Clear(commandList)`
- `GetView()` → `ICompositeView`
- `GetCascadeView(cascade)` → `PlanarView`
- `GetTexture()` → `Texture`
- `GetNumberOfCascades()` → `int`
- `SetLitOutOfBounds(bool)`, `SetFalloffDistance(float)`

Both setup calls take the **`PlanarView`** where C++ takes a `dm::frustum` (and, for the stable
variant, a `dm::affine3 inverseViewMatrix`). The binding pulls those off the view itself, and
the two fits want different frustums: the tight fit takes the view frustum
(`view.GetViewFrustum()`), the stable fit takes the *projection* frustum
(`view.GetProjectionFrustum()`) plus `view.GetInverseViewMatrix()` — that split is the whole
mechanism by which the stable fit stops depending on camera orientation
(`CascadedShadowMap.h:64-76`). All three accessors are on `IView` (`View.h:71-74`). This is the
same rule stage 1 followed for
`SetAmbientColors` and `GetCurrentPixelOffset`: Donut math types never cross into Python, and
the view already holds everything both fits need, so passing it is strictly less error-prone
than decomposing a frustum into 24 floats.

`preViewTranslation` is left at its `0.f` default and not exposed — it belongs to renderers that
translate the world to keep the camera near the origin, which this example does not do.
`numberOfCascades` is likewise not exposed on the setup calls; see
[Cascade count](#cascade-count) for why the count is a construction parameter here.

**Skipped:** `SetupForCubemapView` and `SetupPerObjectShadow` (both stage 2b/3 — omnidirectional
and per-object shadows need light types this stage does not bind), `SetupProxyViews`,
`GetPerObjectView`, and `SetNumberOfCascadesUnsafe` (see below).

### Cascade count

`SetNumberOfCascadesUnsafe` looked like the right way to drive a cascade-count slider without
reallocating. It is not. The constructor builds `m_CompositeView` once, adding a view for every
allocated cascade (`CascadedShadowMap.cpp:67`), and nothing ever rebuilds it — the setter only
moves `m_NumberOfCascades`, which is what the *shaders* read. Lowering the count that way would
leave `GetView()` still rendering every allocated slice, burning a full scene depth pass per
unused cascade and writing into slices whose view matrices were never set up.

So the cascade count is a **construction** parameter: the shadow map is allocated with exactly
the number of cascades the UI asks for, and changing the slider recreates it. Recreation is one
texture allocation on a discrete UI change, and it keeps `GetView()` and the shader's cascade
count incapable of disagreeing.

### `Light.shadowMap`

An assignable property on the existing `Light` binding, accepting an `IShadowMap` or `None`.
Read access returns the current shadow map or `None`. `Light.shadowChannel` stays unbound: it
selects a channel in the `shadowChannels` texture, a screen-space shadow-mask path this example
does not render.

### `DepthPass`

Three types mirroring the existing `GBufferFillPass` trio exactly:

- `DepthPass(device, commonPasses)`, `Init(shaderFactory, params)`, `ResetBindingCache()`
- `DepthPassContext()` — the `GeometryPassContext` subclass `RenderCompositeView` threads through
- `DepthPassCreateParameters()` — `depthBias`, `depthBiasClamp`, `slopeScaledDepthBias`,
  `useInputAssembler`, `numConstantBufferVersions`, `trackLiveness` as plain fields

**Skipped:** `materialBindings` (a `MaterialBindingCache` the pass creates for itself when null,
and which nothing in this repo constructs), and `PipelineKey` (an internal detail of the pass's
pipeline cache).

### Widened `RenderCompositeView` / `RenderView`

Three changes to the existing free-function bindings:

1. `view` and `viewPrev` typed **`ICompositeView`** — not `IView` — instead of `PlanarView`.
   The C++ already takes `const ICompositeView*` (`GeometryPasses.h:82-83`); the narrow binding
   was stage 1 binding only what stage 1 called. `ICompositeView` is the necessary width, not
   merely the honest one: `CascadedShadowMap::GetView()` returns a `CompositeView`, which
   derives from `ICompositeView` and is *not* an `IView` (`View.h:55,150`), so an `IView`
   parameter would reject the very argument this widening exists to accept. `PlanarView` still
   converts, through `IView`.
2. `viewPrev` accepts `None`. The C++ allows null, and shadow rendering has no previous view.
3. The dropped `passEvent` marker name is added as an optional argument, so the shadow pass shows
   up as `"ShadowMap"` in a graphics capture instead of an unnamed run of draws.

All three are backward compatible: every existing caller passes a `PlanarView`, which still
converts to `IView`, and both new arguments default to their current behaviour. The five
examples that call these functions are re-run as part of verification rather than trusted to the
argument-conversion rules.

## `feature_demo.py`

### New state

`FeatureDemo` gains `shadowMap`, `shadowFramebuffer`, `depthPass`, and the UI gains the fields in
[UI](#ui) below.

### `CreateShadowMap()` — deliberately not part of `CreateRenderPasses`

The shadow map is the first render target in this example whose size does **not** come from the
back buffer. Folding it into `CreateRenderPasses` — which `Render` drives from
`RenderTargets.IsUpdateRequired(width, height, sampleCount)` — would destroy and reallocate a
64 MB texture array on every window resize and every AA-mode change, for no reason.

So `CreateShadowMap()` stands alone, called from `Init` and again whenever `(resolution,
cascadeCount)` changes. It:

1. builds the `CascadedShadowMap`,
2. builds one `FramebufferFactory` whose `depthTarget` is `shadowMap.GetTexture()` — a single
   factory serves every cascade, because it caches framebuffers per subresource set
   (`FramebufferFactory.cpp:30`) and each cascade view carries its own array slice,
3. calls `depthPass.ResetBindingCache()`, since the outgoing texture's binding sets cannot be
   reused,
4. re-points `sunLight.shadowMap` at the new map if shadows are enabled.

`depthPass` itself is created once in `Init` alongside the other geometry passes; it depends on
neither size.

### Render order

Before the G-buffer fill or forward opaque pass, when `ui.EnableShadows`:

1. `SetupForPlanarView[Stable](sunLight, self.view, ui.MaxShadowDistance, zUp, zDown, ui.ShadowExponent)`
   — picked by `ui.UseStableCascades`
2. `shadowMap.Clear(commandList)`
3. `RenderCompositeView(commandList, shadowMap.GetView(), None, shadowFramebuffer, rootNode,
   opaqueDrawStrategy, depthPass, depthContext, "ShadowMap")`

`sunLight.shadowMap` is set to the map or to `None` at the top of `Render`, from
`ui.EnableShadows`, so a disabled toggle costs nothing but a null check inside the lighting
passes.

`lightSpaceZUp`/`lightSpaceZDown` are the near/far extents of the shadow projection along the
light direction. They are fixed constants sized to Sponza's bounds with headroom, not UI
controls — they exist to bound the depth range, and exposing them would be a control whose only
correct setting is "big enough". The concrete values are picked during implementation from the
scene graph's root bounding box rather than guessed here.

### Existing code the new pass joins

`depthPass.ResetBindingCache()` is added to two existing lists: the release block in `Render`
that clears every cached binding set before render targets are reallocated, and `ReloadShaders`.
`depthPass` is also recreated in `ReloadShaders` alongside the other geometry passes, since it
holds pipelines compiled from the cleared bytecode.

The render-target release block does **not** become a pass registry this stage. It exists to
sequence *back-buffer-sized* resources, and the shadow map is precisely the resource that does
not belong to it.

## UI

A "Shadows" collapsing section in the settings panel:

| Control | Drives |
| --- | --- |
| Enabled | `sunLight.shadowMap = map or None` |
| Cascade Fit (combo: Tight / Stable) | which setup call runs |
| Cascades (slider, 1–4) | recreates the shadow map |
| Max Shadow Distance (slider) | `maxShadowDistance` |
| Distribution Exponent (slider) | `exponent` |
| Falloff Distance (slider) | `SetFalloffDistance` |
| Lit Out Of Bounds (checkbox) | `SetLitOutOfBounds` |

Resolution is a module constant at 2048, not a slider: changing it means the same recreate path
as the cascade count, and a demo gains nothing from a resolution slider that a cascade-count
slider does not already demonstrate. Depth bias lives in `DepthPassCreateParameters` and is
therefore fixed at pass creation; a bias slider would mean recreating the depth pass per drag,
which is a worse trade than picking a value that works.

## Testing

`test/test_shadow_bindings.py` — a new file rather than extending
`test_postprocess_bindings.py`, which is named for stage 1's subject. Same GPU-free surface style
as stage 1: no device, no rendering, catching re-export gaps, typo'd method names and defaults
drifting from the headers they mirror. Coverage:

- `IShadowMap` exported; `CascadedShadowMap` a subclass of it
- `Light.shadowMap` accepts `None` and round-trips
- `DepthPass`, `DepthPassContext`, `DepthPassCreateParameters` exported, with the create
  parameters' defaults matching `DepthPass.h:75-88`
- `RenderCompositeView` still accepting a `PlanarView` (the widening's backward compatibility)
- the flat-scalar rule: the setup calls reject a tuple where they take a view

Runtime verification, by running the example:

1. Shadows visible under both shading paths.
2. All five AA modes clean, in particular MSAA — the shadow map is single-sampled while the
   G-buffer is not.
3. The cascade-fit toggle changing shadow-edge shimmer under a turning camera.
4. The cascade slider taking effect live, with no validation error on the recreate.
5. A window resize *not* reallocating the shadow map (the point of `CreateShadowMap` standing
   apart).
6. A clean run under the D3D debug runtime and the NVRHI validation layer.
7. The five existing examples that call `RenderCompositeView`/`RenderView` still running after
   the widening.

## Risks

**The widened signature is the only change that reaches outside this example.** It is
source-compatible by construction, but pybind11 overload resolution and implicit conversions are
exactly where "obviously compatible" goes wrong, so every caller is re-run rather than reasoned
about.

**Shadow acne is a tuning problem, not a binding problem.** If the fixed depth bias turns out
wrong for Sponza at 2048², the fix is a different constant, not a new binding — but it is the
most likely reason the first shadowed frame looks wrong, and it should not be mistaken for a
broken cascade setup.

**`GetCascadeView` is bound but unused by the example**, which renders all cascades through
`GetView()`. It is bound because per-cascade debugging (rendering one cascade to inspect its
fit) is the first thing anyone will want when the cascades look wrong, and it costs one line.
