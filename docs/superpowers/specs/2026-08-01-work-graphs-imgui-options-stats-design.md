# Work Graphs example: ImGui "Options/Stats" window — design

## Goal

Port `work_graphs_d3d12.cpp`'s `UIRenderer`/`UIData` (the "Options/Stats" ImGui window) into
`work_graphs.py`, replacing the SPACE-key toggle and `--work-graph` CLI flag that stood in for
it since sub-project 1's design doc deferred this piece. This is sub-project 2's remaining
piece: `work_graphs.py` already has both the dispatch and work-graph-broadcasting-launch
techniques implemented (see `2026-07-31-work-graphs-scene-dispatch-design.md` and the
`128d083` commit); only the UI to switch/inspect them is missing.

Reference: `E:\Gits\Donut-Samples\examples\work_graphs\work_graphs_d3d12.cpp` (`UIData` struct,
`UIRenderer::buildUI`, `WorkGraphs::Animate`/`Render`'s timer-query bookkeping).

## New native bindings (`src/cpp/_pydonut.cpp`)

- `ImGui.Button(label: str) -> bool` — `ImGui::Button`, same static-method-under-`ImGuiNS`
  pattern as the existing `ImGui.*` bindings.
- `CommandList.beginTimerQuery(query: TimerQuery) -> None` / `CommandList.endTimerQuery(query:
  TimerQuery) -> None` — thin wrappers over `nvrhi::ICommandList::beginTimerQuery`/
  `endTimerQuery`. `TimerQuery` and `Device.createTimerQuery`/`pollTimerQuery`/
  `getTimerQueryTime`/`resetTimerQuery` are already bound (`_pydonut.cpp:807,1401-1407`); only
  the command-list-side begin/end calls are missing.

Exported from `src/pydonut/__init__.py` (nothing new needed for `ImGui`/`CommandList`, they're
already exported as classes) and documented in `_pydonut.pyi`.

## `work_graphs.py` changes

- **`UIData`** (plain class, same shape as `rt_particles.py`'s): `currentTechnique: int` (0 =
  Work Graph (Broadcast Launch), 1 = Compute Dispatches — same order/index as the C++
  `techniqueNames` combo), `paused: bool`, `resetAnim: bool`, `gpuFrameTime: float`,
  `gpuShadingTime: float`. Shared by reference between `WorkGraphs` and `UIRenderer`, exactly
  like `rt_particles.py`'s `UIData`/`RayTracedParticles`/`UserInterface` three-way share.
- **`WorkGraphs.__init__`** takes `ui: UIData` and stores `self.ui = ui`. Existing
  `want_work_graph`/`work_graph_pipeline`/`toggle_technique()`/`use_work_graph_now()` machinery
  is kept as-is (it already handles the work-graph backing-memory reinit-on-switch correctly);
  `animate()` calls `toggle_technique()` whenever `ui.currentTechnique == 0` disagrees with
  `want_work_graph`, mirroring `work_graphs_d3d12.cpp:811-815`'s
  `if ((int)m_CurrentTechnique != m_UI.CurrentTechnique)` check.
- **`animate(elapsed)`**: honor `ui.paused` (when paused, `time_diff_this_frame = 0` and
  `time_in_seconds` doesn't advance) and `ui.resetAnim` (OR'd with the existing
  `force_reset_animation` flag to zero both time values), matching
  `work_graphs_d3d12.cpp:798-809` exactly. `ui.resetAnim` is transient — read fresh from the
  `ImGui::Button` return value each frame, same as the C++ original; no explicit clear needed.
- **GPU timer queries**: port `QueuedFramesCount = 10`, `m_FrameTimers`/`m_ShadingTimers` ring
  buffers (`self.frame_timers`/`self.shading_timers`, created once via
  `device.createTimerQuery()` in `__init__`/`init_scene`), `m_NextTimerToUse`, and
  `GetLastValidQueryTimer`'s backward-then-wraparound polling loop, verbatim. In `render()`:
  `resetTimerQuery` both ring-buffer slots at frame start, `beginTimerQuery(frame_timers[i])`
  right after `commandList.open()`, `beginTimerQuery`/`endTimerQuery(shading_timers[i])`
  bracketing whichever shading path ran (dispatch light-culling+shading, or the work-graph
  dispatch), `endTimerQuery(frame_timers[i])` right before `commandList.close()`, then advance
  `self.next_timer_to_use = (self.next_timer_to_use + 1) % 10`. `ui.gpuFrameTime`/
  `gpuShadingTime` are updated from `GetLastValidQueryTimer` in `animate()`, matching
  `work_graphs_d3d12.cpp:818-819`.
- **`UIRenderer(pyd.ImGui_Renderer)`**: `__init__(deviceManager, ui)` stores `self.ui = ui` and
  calls `pyd.ImGui.DisableIniFile()`. `buildUI()` builds the "Options/Stats" window at (10, 10),
  auto-resize, containing (in order): `Combo("Current Technique", ...,
  ["Work Graph (Broadcast Launch)", "Compute Dispatches"])`, `Checkbox("Pause Animation",
  ui.paused)`, `Button("Reset Animation")` (its return value becomes `ui.resetAnim` for this
  frame), `Text(f"Frame Time (GPU): {ui.gpuFrameTime:.3f} ms")`, `Text(f"Shading Time (GPU):
  {ui.gpuShadingTime:.3f} ms")`. No `ShowUI` toggle — the C++ original declares the field but
  never actually wires a key to flip it, so the window is unconditionally always shown, same as
  every other example's ImGui window in this codebase.
- **Bootstrap** (bottom of the file, mirroring `rt_particles.py`'s `RayTracedParticles`/
  `UserInterface`/`deviceManager.AddRenderPassToBack` pair):
  - Remove `wg.want_work_graph = "--work-graph" in sys.argv` and the `KeyboardUpdate`
    SPACE-toggle handler entirely.
  - Revert `SetInformativeWindowTitle` to a static `"PyDonut Work Graphs"` (both the window
    title passed to `CreateWindowDeviceAndSwapChain` and any per-frame title update) — the C++
    original's title is a static `g_WindowTitle` constant; technique/timing now live in the
    ImGui window instead of the title bar.
  - Build a `RootFileSystem` mounting `folder / "bin" / "shaders" / "framework" /
    pyd.GetShaderTypeName(api)` at `/shaders/donut`, and a `ShaderFactory(device, rootFS,
    Path("/shaders"))` — needed only so `UIRenderer.Init(shaderFactory)` can load ImGui's own
    vertex/pixel shaders, same mount convention `rt_particles.py` already uses.
  - Construct `uiData = UIData()`, `gui = UIRenderer(deviceManager, uiData)`, pass `uiData` into
    `WorkGraphs(device, uiData)`; `gui.Init(shaderFactory)` must succeed before
    `deviceManager.AddRenderPassToBack(gui)` (added after the main `RenderPass`, so ImGui draws
    on top); removed via `RemoveRenderPass` after the message loop, same teardown order as
    `rt_particles.py`.

## Verification

- `uv sync --reinstall-package pydonut` to rebuild the native module after the new
  `ImGui.Button`/`CommandList.beginTimerQuery`/`endTimerQuery` bindings are added.
- Run `work_graphs.py` (and `-vk`) unbuffered under a bounded timeout: confirm it reaches
  "DeviceManager created successfully", renders several frames with no exception, and shows the
  "Options/Stats" window in the top-left with a working technique combo, pause checkbox, reset
  button, and two GPU-timing lines that update — visual check, same as every other example.
- Switch technique via the combo mid-run and confirm the image stays visually equivalent
  between Dispatch and Work Graph (the same invariant sub-project 1's SPACE toggle validated).
- Regression check: run `headless.py` once after the rebuild to confirm the new bindings didn't
  break anything else.
