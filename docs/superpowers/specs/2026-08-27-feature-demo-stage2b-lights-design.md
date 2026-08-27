# FeatureDemo port, Stage 2b: spot and point lights — design

## Goal

Give `feature_demo.py` a spot light and a point light in Sponza, and a Lights UI section that
edits any light in the scene — including the sun — through Donut's own light editor.

This is stage 2b. Stage 2a (sun shadows) is complete and landed; see
[`2026-08-26-feature-demo-stage2a-shadows-design.md`](2026-08-26-feature-demo-stage2a-shadows-design.md),
whose [Re-staging](2026-08-26-feature-demo-stage2a-shadows-design.md#re-staging) table this spec
amends.

## Re-staging, again

Stage 2a's table put scene cameras, the material/light editors and the spot/point lights in one
stage 2b. The same argument that split 2a off applies once more: those are independent features
that share no code, and bundling them means a plan with no runnable checkpoint until near the
end. Lights are also the natural next step after 2a — they are the first real exercise of the
"all shadow-casting lights share one texture" constraint that stage's design flagged.

| Stage | Adds | Example state at end of stage |
| --- | --- | --- |
| **2b (this spec)** | `SpotLight`, `PointLight`, `Light.SetColor`/`SetPosition`, `SceneGraphLeaf.GetName`, `app::LightEditor` | + two added lights and a live light editor |
| **2c** | `SceneCamera`/`PerspectiveCamera`, `app::MaterialEditor` | + scene-camera dropdown, material editing |
| **3** | unchanged from stage 1's table | The complete port |

`SceneCamera` moves to 2c on its own merits: `ThirdPersonCamera` is already bound, so the camera
dropdown is a smaller job than the table implied, and `extern/donut` has since grown a
`SwitchableCamera` (`Camera.h:249`) that the reference `FeatureDemo.cpp` predates — whether to
bind that instead of hand-rolling the switch logic is a 2c decision, not one to prejudge here.

`app::MaterialEditor` moves to 2c with it. In the original, the material editor is driven by
MaterialID picking (`FeatureDemo.cpp:1684-1692`, reading `m_ui.SelectedMaterial`), and picking is
stage 3. Without it, material selection needs a dropdown the original does not have — a design
question of its own, and not one lights should wait behind.

## How the new lights reach the shading passes

They already do. Both shading paths submit the whole light list rather than a curated one —
`deferredInputs.SetLights(...GetLights())` at `feature_demo.py:927` and the same list passed to
`forwardPass.PrepareLights` at `feature_demo.py:946` — and both build their per-light constants
through the virtual `Light::FillLightConstants`, which `SpotLight` and `PointLight` override
(`SceneTypes.cpp:185-198` and `:266-276`).

So attaching a light to the scene graph is the entire wiring. **Stage 2b changes no render code
at all**: `Render()` is untouched, no pass is recreated, and no binding cache is cleared. The new
lights light Sponza on the deferred and the forward path from the frame they are attached.

## Why neither new light casts a shadow

`DeferredLightingPass` collects one shadow texture across all submitted lights, and when a second
light presents a *different* texture it logs an error and **returns without rendering**
(`DeferredLightingPass.cpp:172-175`) — the whole frame is lost, not merely the shadow. Giving the
spot or point light its own `CascadedShadowMap` would trip exactly that.

Sharing the sun's map is not an option either: a `CascadedShadowMap`'s cascades are fitted to a
directional light and a view frustum, and the per-object slices a local light needs are
`SetupForCubemapView`/`SetupPerObjectShadow`, both of which stage 2a listed as unbound.

So both new lights keep `shadowMap = None`, and `EnableShadows` continues to gate the sun's map
alone (`feature_demo.py:891-893` is unchanged). Local-light shadows need the shared-atlas work
stage 2a's design flagged, and belong to a later stage.

## New native bindings (`src/cpp/_pydonut.cpp`)

As in stages 1 and 2a: bound to exactly the surface the example calls, with every skipped member
listed so a later stage can tell a decision from an oversight.

### `SceneGraphLeaf.GetName() -> str`

The light dropdown labels come from it, mirroring `FeatureDemo.cpp:1637-1643`. Only `SetName` is
bound today, which was enough while nothing read a name back.

### `Light.SetColor(r, g, b)` and `Light.SetPosition(x, y, z)`

`Light::color` is a `dm::float3`, so it follows this codebase's flat-scalar convention rather
than crossing a math type into Python — the same shape as `SkyParameters`' four float3 fields
(`_pydonut.cpp:2579-2595`). Like those, it is a setter only: nothing in the example reads a
colour back, and the editor writes the field directly from C++.

`SetPosition` mirrors the already-bound `SetDirection`. It is how Donut writes a light's
position: `Light::SetPosition` converts world to parent-local space and calls
`SceneGraphNode::SetTranslation` itself (`SceneTypes.cpp:77-93`), which is why
`SceneGraphNode.SetTranslation` stays unbound.

**Both assert when the light has no node** (`SceneTypes.cpp:82` and `:100`), so a light must be
attached before it is placed. `CreateSunLight` already attaches then calls `SetDirection`
(`feature_demo.py:625-626`); the new code follows that order for the same reason. The two are
independent of each other: `SetDirection` writes rotation and scaling through
`SetTransform(nullptr, &rotation, &scaling)` and leaves the translation alone
(`SceneGraph.cpp:282-291`), so neither call clobbers the other.

### `SpotLight(Light)` and `PointLight(Light)`

Constructible, deriving from the already-bound `Light`. All public fields bound, since the point
of the stage is editing them:

- `SpotLight` (`SceneGraph.h:218-233`): `intensity`, `radius`, `range`, `innerAngle`, `outerAngle`
- `PointLight` (`SceneGraph.h:235-248`): `intensity`, `radius`, `range`

`range = 0` means infinite range, which both `FillLightConstants` overrides encode as an inverse
range of zero — not a degenerate value to guard against.

### `LightEditor(light) -> bool`

A free function `pyd.LightEditor` over `donut::app::LightEditor(engine::Light&)`. It dispatches
on `GetLightType()` in C++ (`UserInterfaceUtils.cpp:364-377`) and draws into whatever ImGui
window is current, so it is called from inside `UIRenderer.buildUI` between `Begin`/`End`. It
returns whether anything changed.

Binding the editor rather than porting its body is the same choice every other stage made: this
repo calls Donut's passes and helpers, it does not reimplement their internals. The alternative
would also need three new ImGui entry points that nothing else wants — `ColorEdit3`, a
logarithmic `SliderFloat` flag, and a double-typed `SliderScalar`.

### Skipped

- `Light.shadowChannel`, `Light.GetPosition`, `Light.GetDirection`, `Light.GetColor` — nothing
  reads them back.
- `DirectionalLight.perObjectShadows` — needs `SetupPerObjectShadow`; a later stage.
- `LightEditor_Directional`, `LightEditor_Point`, `LightEditor_Spot` — the dispatcher covers all
  three, and the example never needs to force a type.
- `AzimuthElevationSliders` — an implementation detail of the editors above.
- `MaterialEditor`, `FileDialog`, `FolderDialog` — 2c and stage 3.
- `OrthographicCamera`, `SceneCamera`, `PerspectiveCamera` — 2c.
- `Light.Store`, `SetProperty`, `Clone` — the JSON and animation paths, which the example does
  not drive.

## `feature_demo.py` changes

### `CreateSceneLights()`

Called from `Init` immediately after `CreateSunLight()`, and shaped like it: construct, name,
`graph.AttachLeafNode(graph.GetRootNode(), light)`, *then* place, and one `graph.Refresh(0)` at
the end covering both.

Unlike `CreateSunLight` there is no "reuse what the scene declared" branch. That branch exists
because the sun is the light the renderer needs and a different scene might supply one; these two
are the example's own demonstration objects and are always synthesised.

Starting values, chosen against Sponza's metre scale (the camera starts at `(0, 1.8, 0)` with a
move speed of 3.0) and to be tuned by eye at the plan's run step:

| | Point light | Spot light |
| --- | --- | --- |
| name | `"Point"` | `"Spot"` |
| position | `(-4.0, 2.0, 0.0)` | `(4.0, 5.0, 0.0)` |
| direction | — | `(-0.2, -1.0, 0.0)` |
| `intensity` | `20.0` | `60.0` |
| `radius` | `0.05` | `0.05` |
| `range` | `0.0` (infinite) | `0.0` (infinite) |
| `innerAngle` / `outerAngle` | — | `20.0` / `35.0` |

Both are left at the default white `color`; the editor is how the demo shows colour changing.

### The Lights UI section

A `CollapsingHeader("Lights")` in `UIRenderer.buildUI`, placed after the existing Shadows
section, mirroring `FeatureDemo.cpp:1633-1656`:

- a `BeginCombo("Select Light", ...)` previewing the selected light's `GetName()` or `"(None)"`,
  with one `Selectable` per entry of `GetSceneGraph().GetLights()`,
- the selection stored as `self.selectedLight` on `UIRenderer` — the same place the original
  keeps `m_SelectedLight`, and deliberately not on `UIData`, since nothing outside the UI reads it,
- `pyd.LightEditor(self.selectedLight)` beneath, when something is selected.

One departure from the original. The C++ combo calls `ImGui::Selectable(label, &selected)` and
then tests `selected`, which re-selects whatever the mouse passes over. The bound
`Selectable(label, selected) -> bool` returns the click instead, which is the correct ImGui
idiom, so the Python code selects on click and passes the current selection as the `selected`
argument for highlighting.

The sun is in this list, so the editor drives its direction, colour and irradiance live. The
cascades follow on the next frame with no extra code, because `RenderShadowMap` re-fits them from
`self.sunLight` every frame (`feature_demo.py:557-580`).

## Testing

`test/test_light_bindings.py`, following `test_shadow_bindings.py`: per class, construction, a
field round-trip, and the inheritance chain up to `Light` and `SceneGraphLeaf`.

`SetPosition`, `SetDirection` and `GetName` need a light attached to a scene graph, which needs no
device — a bare `SceneGraph` with a root node is enough — so those get a real round-trip through
the node `AttachLeafNode` returns, read back with `SceneGraphNode.GetWorldPosition()`. That read
needs a `graph.Refresh(0)` first: `SetTranslation` only marks the node dirty, and the world
transform `GetWorldPosition` returns is the one `Refresh` recomputes.

`LightEditor` needs a live ImGui frame and cannot be called from a test. It gets a presence check
only, the same treatment the ImGui surface gets at `test_postprocess_bindings.py:227`.

## Out of scope

Shadows for the new lights (see above), adding or removing lights at runtime, light gizmos,
`OrthographicCamera`, and everything already deferred to 2c and stage 3.
