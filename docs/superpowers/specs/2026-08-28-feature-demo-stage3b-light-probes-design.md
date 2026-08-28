# FeatureDemo port, Stage 3b: light probes — design

## Goal

Port the last remaining FeatureDemo feature: **light probes**. Four probes, captured on
demand from the active camera's position into a cube-map array, processed into diffuse
irradiance and roughness-filtered specular maps, and fed to both the forward and the
deferred shading path as image-based ambient light.

Reference sample: `E:\Gits\Donut-Samples\feature_demo\FeatureDemo.cpp`.

This completes the port. After 3b, the only unported FeatureDemo features are the three
that are permanently out of scope: DLSS (no NGX SDK vendored), taskflow parallel scene
load, and the ImGui console subsystem.

## Position in the staging

Stage 3 was split in the 3a spec:

| Stage | Scope | State |
|---|---|---|
| 3a | MaterialID picking, screenshots, MipMapGen, stereo | done |
| 3b (this spec) | Light probes | this spec |

The two are mutually independent; 3b happens to run second, not because it depends on 3a.
One incidental benefit of that order: `SceneGraphNode.GetGlobalBoundingBox()` and
`SceneGraphLeaf.GetNodeSharedPtr()` were bound by 3a Task 2 for picking, and 3b reuses the
first of them for the shadow-cascade z-range.

## Prerequisites that already exist

The 3a spec predicted 3b would need `CubemapView`, `dm::frustum`, and various supporting
bindings. An audit of the current tree shows the prerequisite list is much shorter than
that prediction:

Already bound, no work needed — `CubemapView` (including `SetArrayViewports`,
`GetFaceView`, `UpdateCache`), `Device.queryFeatureSupport(Feature.FastGeometryShader)`,
`TextureDimension.TextureCube` / `TextureCubeArray`, `TextureDesc.arraySize` /
`mipLevels` / `isTypeless`, `FramebufferFactory`, `SkyPass`, `ForwardShadingPass`,
`DepthPass`, `CascadedShadowMap.Clear` / `GetView`, `RenderCompositeView`, and
`SceneGraphNode.GetGlobalBoundingBox()`.

Critically, `CommandList.clearTextureFloat(texture, clearColor)` and
`clearDepthStencilTexture(texture, ...)` **already pass `nvrhi::AllSubresources`**
internally (`src/cpp/_pydonut.cpp:1699-1701`), which is exactly what the sample's probe
path passes at both of its clear call sites. No new clear overload is needed.

`dm::frustum` turns out not to be needed at all — see below.

## `LightProbe` and the no-math-types rule

`engine::LightProbe` (`SceneTypes.h:356-371`) is a plain struct: a name, three texture
handles, two array indices, two scales, an `enabled` flag, and a `dm::frustum bounds`.
Everything but `bounds` binds directly as `def_readwrite` / `def_property`.

`bounds` is the interesting field, and the reason the 3a spec expected 3b to introduce
"the first bound Donut math type". It does not, because of how the sample actually uses
it. There are exactly two writes and zero reads:

- `probe->bounds = frustum::empty()` at creation (`FeatureDemo.cpp:1294`)
- `probe->bounds = frustum::fromBox(box3(p, p).grow(10.f))` after a capture (`:1430-1431`)

Both are constructions, never inspections. So `bounds` is exposed as three methods rather
than a property, and no frustum type crosses into Python:

```python
probe.SetBoundsEmpty()
probe.SetBoundsInfinite()
probe.SetBoundsFromBox(minX, minY, minZ, maxX, maxY, maxZ)
```

`SetBoundsFromBox` builds `dm::frustum::fromBox(dm::box3(mins, maxs))` internally. This
keeps intact the rule stated at `src/pydonut/_pydonut.pyi:1676` and applied by every prior
stage: donut math types never cross into Python. Binding a `Frustum` class would have
added a type that nothing else in the repo uses, in exchange for line-for-line similarity
to two lines of C++.

The struct binds as `py::class_<LightProbe, std::shared_ptr<LightProbe>>` — both consumers
take `const std::vector<std::shared_ptr<engine::LightProbe>>&`, so a shared-pointer holder
is mandatory, not stylistic.

## The two consumers

### `ForwardShadingPass.PrepareLights` gains a trailing argument

The C++ signature (`ForwardShadingPass.h:181-187`) has always taken `lightProbes` as its
last parameter; the existing binding hardcodes an empty vector and says so
(`_pydonut.pyi:1537`). Stage 3b replaces that hardcoded empty with a real, **trailing and
defaulted** parameter:

```python
def PrepareLights(self, context, commandList, lights,
                  topR, topG, topB, bottomR, bottomG, bottomB,
                  lightProbes: list[LightProbe] = []) -> None: ...
```

Being trailing and defaulted matters: `deferred_shading.py`, `threaded_rendering.py` and
every other existing caller passes nine arguments and must keep working untouched. A test
pins that nine-argument form explicitly, so a future reordering cannot silently break the
other examples.

### `DeferredLightingPassInputs.SetLightProbes`

`DeferredLightingPass::Inputs::lightProbes` is a **non-owning pointer** to a vector
(`DeferredLightingPass.h:82`), the same shape as `Inputs::lights`. The existing binding
already solves this with a `PyDeferredLightingInputs` wrapper holding an `ownedLights`
vector for the raw pointer to point at (`_pydonut.cpp:341-357`). `SetLightProbes` adds an
`ownedLightProbes` member and follows that pattern exactly:

```cpp
void SetLightProbes(std::vector<std::shared_ptr<engine::LightProbe>> newProbes) {
    ownedLightProbes = std::move(newProbes);
    lightProbes = &ownedLightProbes;
}
```

An empty list therefore yields a non-null pointer to an empty vector rather than the
sample's `nullptr`. Those are equivalent: `DeferredLightingPass::Render` guards with
`if (inputs.lightProbes)` and then iterates
(`extern/donut/src/render/DeferredLightingPass.cpp:221-224`), so a non-null pointer to an
empty vector iterates zero times and leaves `numLightProbes` at 0 — exactly what `nullptr`
produces. `SetLightProbes([])` is the off switch, and no null-pointer path is needed.

### All submitted probes must share one texture set

`DeferredLightingPass::Render` logs an error and **returns without rendering the frame** if
two submitted probes present different `diffuseMap`, `specularMap` or `environmentBrdf`
handles (`DeferredLightingPass.cpp:246-253`). This is the same failure mode already
documented in `feature_demo.py`'s `CreateSceneLights` for two lights with different shadow
maps, and it is why `CreateLightProbes` allocates **two shared cube-map arrays indexed by
slice** rather than a private pair of textures per probe. `environmentBrdf` satisfies it
for free: every probe is assigned the one texture owned by the single
`LightProbeProcessingPass`.

A second cap applies: `DEFERRED_MAX_LIGHT_PROBES` bounds how many active probes reach the
constant buffer, with a warning past it. Four probes is comfortably inside it.

## `LightProbeProcessingPass`

Seven public methods (`LightProbeProcessingPass.h:93-137`), all binding straight through,
with one shape change:

```python
LightProbeProcessingPass(device, shaderFactory, commonPasses,
                         intermediateTextureSize=1024,
                         intermediateTextureFormat=Format.RGBA16_FLOAT)
BlitCubemap(cl, inCubeMap, inBaseArraySlice, inMipLevel, outCubeMap, outBaseArraySlice, outMipLevel)
GenerateCubemapMips(cl, cubeMap, baseArraySlice, sourceMipLevel, levelsToGenerate)
RenderDiffuseMap(cl, inEnvironmentMap, outDiffuseMap, outBaseArraySlice, outMipLevel)
RenderSpecularMap(cl, roughness, inEnvironmentMap, outSpecularMap, outBaseArraySlice, outMipLevel)
RenderEnvironmentBrdfTexture(cl)
GetEnvironmentBrdfTexture() -> Texture
ResetCaches()
```

`RenderDiffuseMap` and `RenderSpecularMap` **drop** their `nvrhi::TextureSubresourceSet
inSubresources` parameter and pass `nvrhi::AllSubresources` internally. `TextureSubresourceSet`
is not exposed to Python anywhere in this project, `AllSubresources` is what the sample
passes at both call sites (`FeatureDemo.cpp:1413`, `:1419`), and `clearTextureFloat` /
`clearDepthStencilTexture` / `resolveTexture` already set the precedent of folding the
subresource argument away (`_pydonut.cpp:1699-1766`). Adding a subresource-set type for two
call sites that both want "all" would be the tail wagging the dog.

The out-parameter names differ from the header, which calls `RenderSpecularMap`'s target
`outDiffuseMap` — a copy-paste slip in donut. The binding names it `outSpecularMap`.

`GetEnvironmentBrdfTexture` returns a raw `ITexture*` owned by the pass, so it binds with
`return_value_policy::reference` and its lifetime is tied to the pass. This is what forces
probes to be disabled when the pass is recreated — see `ReloadShaders` below.

## Supporting bindings

### `CubemapView.SetTransformFromPosition`

The sample calls `view.SetTransform(dm::translation(-probePosition), nearPlane, cullDistance)`
(`FeatureDemo.cpp:1353`). `SetTransform` takes a `dm::affine3` (`View.h:361`), which cannot
cross into Python, and the only affine3 the sample ever builds for it is a pure negated
translation. So the binding takes the position directly and builds the matrix itself:

```python
def SetTransformFromPosition(self, x, y, z, zNear, cullDistance,
                             useReverseInfiniteProjections=True) -> None: ...
```

Named to sit beside the already-bound `SetTransformFromCamera`, which solves the same
problem the same way for the camera case.

### `CascadedShadowMap.SetupForCubemapView`

The C++ takes a `dm::float3 center` (`CascadedShadowMap.h:79-85`), and the sample passes
`view.GetViewOrigin()`. Rather than bind `GetViewOrigin` and pass three floats back in, the
binding takes the **view** and reads the origin off it internally — `GetViewOrigin()` is a
pure virtual on `IView` (`View.h:69`), so this works for any view type:

```python
def SetupForCubemapView(self, light, view: IView, maxShadowDistance,
                        lightSpaceZUp, lightSpaceZDown, exponent=4.0) -> bool: ...
```

This is deliberately the same shape as the already-bound `SetupForPlanarView(light, view,
...)` and `SetupForPlanarViewStable(light, view, ...)`, which likewise take an `IView` and
extract the frustum data internally rather than exposing it. Stage 3a established that
convention; 3b follows it. `numberOfCascades` and `preViewTranslation` stay unbound, as
they already are on the two planar variants.

### `ForwardShadingPassCreateParameters.singlePassCubemap`

One `def_readwrite`. The sample sets it from
`queryFeatureSupport(nvrhi::Feature::FastGeometryShader)` (`FeatureDemo.cpp:1379`), and
both halves of that are already bound.

### Three camera-position accessors

The probe is captured at the active camera's position (`FeatureDemo.cpp:1349-1352`).
Nothing currently bound can report a camera position, so three small accessors are added:

```python
BaseCamera.GetPosition() -> tuple[float, float, float]
SwitchableCamera.GetActiveUserCamera() -> BaseCamera
SceneCamera.GetPosition() -> tuple[float, float, float]
```

`BaseCamera.GetPosition` wraps `Camera.h:62` and returns a flat 3-tuple, matching the
already-bound `GetDir` / `GetUp` on the same class. `GetActiveUserCamera` wraps
`Camera.h:254`, returning a non-owning reference to the camera the `SwitchableCamera` owns.

`SceneCamera.GetPosition` is the one **deliberate correction**. The sample reads
`m_ui.ActiveSceneCamera->GetWorldToViewMatrix().m_translation` (`FeatureDemo.cpp:1351`).
The world-to-view matrix's translation is `-R·p`, not `p`; for any scene camera with a
non-identity rotation that is not the camera's position, and Sponza's Gallery camera is
rotated. The binding reads `GetViewToWorldMatrix().m_translation` (`SceneGraph.h:150`)
instead, which is the true world position. Same class of correction as stage 3a made to the
stable-cascade setup call, and it is called out here so a reviewer diffing against the C++
does not read it as a porting error.

### Skipped

`nvrhi::utils::ChooseFormat` and the `FormatSupport` flag enum. See the depth-format
divergence below.

## `feature_demo.py` changes

### `UIData`

Three new fields, matching `FeatureDemo.cpp:265-267`:

```python
self.EnableLightProbe = True
self.LightProbeDiffuseScale = 1.0
self.LightProbeSpecularScale = 1.0
```

### `CreateLightProbes`

Called from `Init`. Allocates the two shared cube-map arrays and four probes pointing into
them (`FeatureDemo.cpp:1249-1299`):

| Texture | Size | Mips | `arraySize` | Format | Initial state |
|---|---|---|---|---|---|
| diffuse | 256² | 1 | `6 * numProbes` | `RGBA16_FLOAT` | `ShaderResource` |
| specular | 512² | 8 | `6 * numProbes` | `RGBA16_FLOAT` | `ShaderResource` |

Both `TextureCubeArray`, `isRenderTarget = True`, `keepInitialState = True`. The four
probes are named `"1"`–`"4"`, take `diffuseArrayIndex = specularArrayIndex = i`, and start
`enabled = False` with `SetBoundsEmpty()` — a probe holds no captured content until its
button is pressed, and empty bounds mean it contributes nothing if that check is ever
reached first.

`numProbes` is a constant (4) at the one call site, not a UI control: changing it means
reallocating both arrays, and the demo shows nothing at five probes that it does not at
four.

### `RenderLightProbe(probe)`

A port of `FeatureDemo.cpp:1301-1433`, and the largest single addition in this stage. It
stands up its own throwaway render graph, renders one cube-map capture, processes it into
the probe's array slices, and tears the graph down:

1. Create a 1024², 8-mip, 6-slice `TextureCube` colour target (`RGBA16_FLOAT`,
   `useClearValue`, clear to black) and a matching 1-mip depth cube.
2. Build a `FramebufferFactory` over the pair.
3. Build a `CubemapView`: `SetArrayViewports(1024, 0)`, then
   `SetTransformFromPosition(px, py, pz, 0.1, 100.0)`, then `UpdateCache()`.
4. Build a throwaway `SkyPass` over that framebuffer and view, and a throwaway
   `ForwardShadingPass` whose `singlePassCubemap` comes from
   `queryFeatureSupport(Feature.FastGeometryShader)`.
5. Open a fresh command list; clear colour and depth.
6. Refit the cascades: `zRange = length(sceneBounds.diagonal()) * 0.5` from the root node's
   `GetGlobalBoundingBox()`, then `SetupForCubemapView(sunLight, view, 100.0, zRange,
   zRange, ui.ShadowExponent)`, then `Clear` and a `RenderCompositeView` through the
   existing `depthPass` and `shadowFramebuffer`.
7. `PrepareLights` with an **empty** probe list — a probe capture must not light itself
   from other probes — then opaque, sky, transparent.
8. `GenerateCubemapMips`, `RenderDiffuseMap`, then `RenderSpecularMap` once per specular
   mip with `roughness = (mip / (mipCount - 1)) ** 2`, then `RenderEnvironmentBrdfTexture`.
9. Close, execute, `waitForIdle()`, `runGarbageCollection()`.
10. Set `probe.environmentBrdf`, `SetBoundsFromBox(px±10, py±10, pz±10)`, `enabled = True`.

The probe position comes from `camera.GetSceneCamera().GetPosition()` when a scene camera
is active, otherwise `camera.GetActiveUserCamera().GetPosition()`.

Two consequences worth commenting in the code:

- **The cascade refit clobbers the main view's fit.** Step 6 leaves the shared
  `CascadedShadowMap` fitted to the probe's omnidirectional view, not to the camera.
  Harmless: `RenderShadowMap` refits it from scratch at the top of every `Render`, so the
  damage lasts until the next frame begins. The sample has the same behaviour.
- **The throwaway passes are genuinely throwaway.** A new `ForwardShadingPass` and
  `SkyPass` are built per capture rather than reusing the app's. They must be: the app's
  forward pass has `singlePassCubemap = False` and its pipelines are cached against the
  back-buffer framebuffer info, neither of which suits a cube-map target. This is a
  button-press-frequency operation, so the construction cost is irrelevant.

### Trigger: called directly from `buildUI`, not deferred through a flag

The sample calls `m_app->RenderLightProbe(*probe)` straight out of its button handler
(`FeatureDemo.cpp:1665`), and this port does the same. That is safe here for two reasons
that should be stated once in a comment rather than rediscovered:

- `ImGui_Renderer::Render` calls `buildUI()` **before** it opens its own command list
  (`extern/donut/src/app/imgui_renderer.cpp:360-367`), and the `FeatureDemo` render pass
  has already closed and executed its command list by then. No command list is open on the
  immediate context when the button fires.
- `RenderLightProbe` is fully self-contained: it creates, executes and drains its own
  command list.

This is a deliberate contrast with the screenshot, which *does* go through a flag
(`ui.ScreenshotFileName`) — not out of caution, but because it must run at a specific point
inside `Render`, after `executeCommandList`, with the back buffer in hand. A probe capture
has no such constraint, so a flag would buy nothing and add a frame of latency.

### `Render`

Build the probe list once, before the shading branch (`FeatureDemo.cpp:968-978`):

```python
lightProbes = []
if self.ui.EnableLightProbe:
    for probe in self.lightProbes:
        if probe.enabled:
            probe.diffuseScale = self.ui.LightProbeDiffuseScale
            probe.specularScale = self.ui.LightProbeSpecularScale
            lightProbes.append(probe)
```

The scales are pushed onto the probe objects here rather than read at bind time because
`LightProbe::FillLightProbeConstants` reads them off the struct — the UI has no other way
to reach them.

Forward path: pass `lightProbes` as `PrepareLights`' new trailing argument. Deferred path:
`deferredInputs.SetLightProbes(lightProbes)`.

The sample passes the *whole* `m_LightProbes` list to the deferred path
(`FeatureDemo.cpp:1021`) while giving the forward path the filtered enabled list — an
asymmetry that only works because `DeferredLightingPass` skips probes failing `IsActive()`.
This port passes the same filtered list to both. The rendered result is identical (a
disabled probe fails `IsActive()` and is skipped either way), and one list is easier to
reason about than two that must stay in sync.

### `ReloadShaders`

`LightProbeProcessingPass` compiles five shaders in its constructor, so it is **recreated**
alongside the other shader-holding passes, not merely `ResetCaches()`d. Recreating it
invalidates every probe: `probe.environmentBrdf` points at the outgoing pass's
internally-owned BRDF texture, which dies with it. So the reload also sets `enabled = False`
on every probe, mirroring what the sample does in `SceneUnloading`
(`FeatureDemo.cpp:563-573`) — this port has no `SceneUnloading`, and a shader reload is the
analogous "everything built from shaders is now stale" point.

`ResetCaches()` is still bound and still worth having: it is the correct call for a caller
that keeps the pass but invalidates its framebuffer/PSO/binding-set caches.

### `buildUI`

Two additions at the sample's own placements:

- After "Ambient Intensity" (`FeatureDemo.cpp:1605-1610`): an "Enable Light Probe"
  checkbox, and — when enabled — a "Light Probe" collapsing header with "Diffuse Scale" and
  "Specular Scale" `DragFloat`s over 0–10 at 0.01 per pixel. `DragFloat` rather than
  `SliderFloat` because that is what the sample uses and the useful range sits near the
  bottom of the interval; the binding is already exercised by the TAA section's
  "Max Radiance".
- After the Lights section (`FeatureDemo.cpp:1658-1668`): a `Text("Render Light Probe: ")`
  followed by one `SameLine` button per probe, labelled with the probe's name, each
  calling `self.app.RenderLightProbe(probe)`.

The button row is wrapped in `PushID("LightProbes")` / `PopID()`, for the same reason the
Lights and Material Editor sections already are: `CollapsingHeader` pushes no ID scope, so
generically-labelled widgets in sibling sections can collide.

### Module docstring

Update to list light probes and to drop the "Still to come in stage 3b" sentence — after
this stage the only omissions are the three permanent ones.

## Deliberate divergences from the sample, collected

1. **`bounds` via three helper methods, no `dm::frustum` type.** Preserves the
   no-math-types rule; covers every use the sample makes.
2. **`TextureSubresourceSet` stays unbound.** `RenderDiffuseMap` / `RenderSpecularMap`
   fold `AllSubresources` in, matching what the sample passes and the precedent set by the
   existing clear/resolve bindings.
3. **Depth format hardcoded to `Format.D32`.** The sample picks one via
   `nvrhi::utils::ChooseFormat` over `{D24S8, D32, D16, D32S8}` (`FeatureDemo.cpp:1384-1395`).
   D32 is in that candidate list, is universally supported, and is already what
   `CreateShadowMap` uses in this same file. Binding `ChooseFormat` plus the `FormatSupport`
   flag enum to reach a format we can name directly is not worth it. Consequence:
   `hasStencil` is always false, so the probe's `clearDepthStencilTexture` passes
   `clearStencil=False` rather than computing it. `isTypeless` stays `False` — the depth
   cube is never sampled, only rendered into.
4. **Scene-camera probe position corrected** from `GetWorldToViewMatrix().m_translation` to
   `GetViewToWorldMatrix().m_translation`, as described above.
5. **One filtered probe list for both shading paths** instead of the sample's filtered
   list for forward and unfiltered list for deferred. Same rendered result.

## Testing

`test/test_lightprobe_bindings.py` (new), GPU-free, following the shape of the stage-3a
test files:

- `LightProbe` is constructible, is held by `shared_ptr`, and every field round-trips:
  `name`, `diffuseMap`, `specularMap`, `environmentBrdf`, `diffuseArrayIndex`,
  `specularArrayIndex`, `diffuseScale`, `specularScale`, `enabled`.
- Defaults match `SceneTypes.h:362-367`: indices 0, scales 1.0, `enabled = True`.
- `IsActive()` is False on a fresh probe. Note *which* of its three conditions
  (`SceneTypes.cpp:379-389`) fails: not the bounds check — a default-constructed probe's
  bounds are `frustum::infinite()`, not empty — but the map check, since neither
  `diffuseMap` nor `specularMap` is assigned. Assigning a `diffuseMap` therefore flips it
  to True, and `SetBoundsEmpty()` flips it back; the test pins both transitions, which is
  what proves the bounds helpers reach the real field rather than no-oping.
- `LightProbeProcessingPass` exposes all seven methods with the documented arity, and its
  constructor's two trailing parameters default to `1024` and `Format.RGBA16_FLOAT`.
  Construction itself needs a device and shader factory, so it is exercised only where the
  existing pass tests already establish those; the signature checks are static.
- `PrepareLights` accepts a `lightProbes` list as a tenth argument **and** still accepts
  the nine-argument form — the latter is the regression guard for `deferred_shading.py`,
  `threaded_rendering.py` and every other existing caller.
- `DeferredLightingPassInputs.SetLightProbes` accepts a list and an empty list, and the
  probes it is given outlive the call (the `ownedLightProbes` lifetime guarantee).
- `CubemapView.SetTransformFromPosition` runs and leaves the view's six face views
  consistent, with `useReverseInfiniteProjections` defaulting to `True`.
- `CascadedShadowMap.SetupForCubemapView` accepts a `CubemapView`, returns a `bool`, and
  defaults `exponent` to 4.0.
- `ForwardShadingPassCreateParameters.singlePassCubemap` defaults to `False` and
  round-trips.
- `BaseCamera.GetPosition`, `SwitchableCamera.GetActiveUserCamera` and
  `SceneCamera.GetPosition` each return the documented shape;
  `GetActiveUserCamera` returns the *same* object across two calls (proving a reference,
  not a copy) and tracks `SwitchToFirstPerson` / `SwitchToThirdPerson`.

Regression: the full existing suite must pass unchanged. The `PrepareLights` widening is
the only change to an already-shipped signature, and the nine-argument test above plus the
existing forward-shading tests are what prove it stayed source-compatible.

## Out of scope

DLSS, taskflow parallel scene load, the ImGui console — permanently, as in every prior
stage. Per-object shadows and `SetupPerObjectShadow`. Probe placement UI: probes capture at
wherever the camera happens to be, exactly as the sample does, with no way to move a probe
after capture. Probe serialisation. `BlitCubemap` is bound for completeness but the sample
never calls it, so nothing in `feature_demo.py` exercises it.

Visual verification of probe lighting is not reachable from a headless test. A green suite
proves the bindings are callable and the signatures are right; it does not prove the
capture looks correct on screen. Task 7 ends with a manual run for that reason.
