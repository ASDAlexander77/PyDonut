# Work Graphs ImGui Options/Stats Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `work_graphs_d3d12.cpp`'s "Options/Stats" ImGui window (technique combo, pause/reset animation, GPU frame/shading timing) into `work_graphs.py`, replacing the CLI-flag-plus-SPACE-toggle placeholder.

**Architecture:** Add three small native bindings (`ImGui.Button`, `CommandList.beginTimerQuery`/`endTimerQuery`) and fill two pre-existing stub gaps (`TimerQuery` was bound in C++ but never exposed through `__init__.py`/`_pydonut.pyi`, and `Device`'s timer-query methods were missing from the `.pyi`). Then add a `UIData` class shared by reference between `WorkGraphs` and a new `UIRenderer(pyd.ImGui_Renderer)`, port the 10-deep GPU timer-query ring buffer verbatim, and wire the new render pass into the bootstrap in place of the CLI flag/SPACE handler.

**Tech Stack:** pybind11 (C++/nvrhi bindings), Python, HLSL (unchanged by this plan), Dear ImGui via donut's `ImGui_Renderer`.

## Global Constraints

- Match `E:\Gits\Donut-Samples\examples\work_graphs\work_graphs_d3d12.cpp` behavior exactly (per user directive) — this is a straight port, not a reinterpretation.
- No new dependencies. Reuse `pyd.RootFileSystem`/`pyd.ShaderFactory` exactly as `rt_particles.py` already does for its own `UserInterface`.
- This codebase has no pytest suite for example scripts (confirmed: no `tests/` directory exists despite the README mentioning `uv run pytest`). Verification for GPU-rendering code in this repo is always a manual run + visual/log check (see every existing design doc's own Verification section) — do not invent unit tests for rendering code that has none elsewhere in the codebase. `work_graphs.py`'s existing `_scene_smoke_test()` (pure-Python scene generation, no GPU) is the only kind of automated check that exists here, and this plan touches no code it covers.
- Rebuild command after any C++ change: `uv sync --reinstall-package pydonut` (cached on `src/**/*.{h,c,hpp,cpp}` per `pyproject.toml`).

---

## File Structure

- Modify: `src/cpp/_pydonut.cpp` — add `ImGui.Button`, `CommandList.beginTimerQuery`/`endTimerQuery`.
- Modify: `src/pydonut/_pydonut.pyi` — add `TimerQuery` class stub, `Device.createTimerQuery`/`pollTimerQuery`/`getTimerQueryTime`/`resetTimerQuery`, `CommandList.beginTimerQuery`/`endTimerQuery`, `ImGui.Button`.
- Modify: `src/pydonut/__init__.py` — export `TimerQuery`.
- Modify: `work_graphs.py` — add `UIData`, wire `WorkGraphs` to it, add `UIRenderer`, rewrite the bootstrap tail.

---

### Task 1: Native bindings — `ImGui.Button`, `CommandList` timer queries, and the pre-existing `TimerQuery`/.pyi gaps

**Files:**
- Modify: `src/cpp/_pydonut.cpp:1639` (add `CommandList.beginTimerQuery`/`endTimerQuery`)
- Modify: `src/cpp/_pydonut.cpp:2656` (add `ImGui.Button`)
- Modify: `src/pydonut/_pydonut.pyi:740` (add `class TimerQuery(): ...`)
- Modify: `src/pydonut/_pydonut.pyi:852` (add `Device` timer-query method stubs)
- Modify: `src/pydonut/_pydonut.pyi:812` (add `CommandList.beginTimerQuery`/`endTimerQuery` stubs)
- Modify: `src/pydonut/_pydonut.pyi:1399` (add `ImGui.Button` stub)
- Modify: `src/pydonut/__init__.py:61` (export `TimerQuery`)
- Modify: `src/pydonut/__init__.py:226` (add `'TimerQuery'` to `__all__`)

**Interfaces:**
- Produces: `pyd.TimerQuery` (opaque handle class); `device.createTimerQuery() -> TimerQuery` and `device.pollTimerQuery(query: TimerQuery) -> bool` / `device.getTimerQueryTime(query: TimerQuery) -> float` / `device.resetTimerQuery(query: TimerQuery) -> None` (already bound in C++, only now documented/exported); `commandList.beginTimerQuery(query: TimerQuery) -> None`; `commandList.endTimerQuery(query: TimerQuery) -> None`; `pyd.ImGui.Button(label: str) -> bool`. Task 2 consumes all of these.

- [ ] **Step 1: Add `CommandList.beginTimerQuery`/`endTimerQuery` to `_pydonut.cpp`**

In `src/cpp/_pydonut.cpp`, find this exact line (currently line 1639):

```cpp
    commandList.def("commitBarriers", &nvrhi::ICommandList::commitBarriers, py::call_guard<py::gil_scoped_release>());
```

Add these two lines immediately after it:

```cpp
    commandList.def("beginTimerQuery", &nvrhi::ICommandList::beginTimerQuery, py::arg("query"));
    commandList.def("endTimerQuery", &nvrhi::ICommandList::endTimerQuery, py::arg("query"));
```

- [ ] **Step 2: Add `ImGui.Button` to `_pydonut.cpp`**

Find the end of the `ImGui` binding block (currently ending at line 2656):

```cpp
        .def_static("DragFloat3", [](const std::string &label, float x, float y, float z, float speed) {
            float v[3] = { x, y, z };
            bool changed = ImGui::DragFloat3(label.c_str(), v, speed);
            return py::make_tuple(changed, v[0], v[1], v[2]);
        }, py::arg("label"), py::arg("x"), py::arg("y"), py::arg("z"), py::arg("speed") = 1.0f);
```

Replace it with (changes the trailing `;` to `,` and appends `Button`):

```cpp
        .def_static("DragFloat3", [](const std::string &label, float x, float y, float z, float speed) {
            float v[3] = { x, y, z };
            bool changed = ImGui::DragFloat3(label.c_str(), v, speed);
            return py::make_tuple(changed, v[0], v[1], v[2]);
        }, py::arg("label"), py::arg("x"), py::arg("y"), py::arg("z"), py::arg("speed") = 1.0f)
        .def_static("Button", [](const std::string &label) {
            return ImGui::Button(label.c_str());
        }, py::arg("label"));
```

- [ ] **Step 3: Rebuild the native module**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds with no errors (this is a mechanical addition of two already-existing nvrhi/ImGui calls, no new headers needed — `imgui.h` and `nvrhi.h` are already included in this file).

- [ ] **Step 4: Add `TimerQuery` class stub to `_pydonut.pyi`**

Find this exact line (currently line 740):

```python
class Shader(): ...
```

Add immediately after it:

```python
class TimerQuery(): ...
```

- [ ] **Step 5: Add `Device` timer-query method stubs to `_pydonut.pyi`**

Find this exact line (currently line 852):

```python
    def waitForIdle(self: Device) -> None: ...
```

Replace it with:

```python
    def waitForIdle(self: Device) -> None: ...
    def createTimerQuery(self: Device) -> TimerQuery: ...
    # Non-blocking: true once the query's result is ready to read.
    def pollTimerQuery(self: Device, query: TimerQuery) -> bool: ...
    # Elapsed time in seconds. Only valid after pollTimerQuery(query) returns True.
    def getTimerQueryTime(self: Device, query: TimerQuery) -> float: ...
    def resetTimerQuery(self: Device, query: TimerQuery) -> None: ...
```

- [ ] **Step 6: Add `CommandList.beginTimerQuery`/`endTimerQuery` stubs to `_pydonut.pyi`**

Find this exact line (currently line 812):

```python
    def commitBarriers(self: CommandList) -> None: ...
```

Replace it with:

```python
    def commitBarriers(self: CommandList) -> None: ...
    def beginTimerQuery(self: CommandList, query: TimerQuery) -> None: ...
    def endTimerQuery(self: CommandList, query: TimerQuery) -> None: ...
```

- [ ] **Step 7: Add `ImGui.Button` stub to `_pydonut.pyi`**

Find this exact line (currently line 1399):

```python
    def DragFloat3(label: str, x: float, y: float, z: float, speed: float = 1.0) -> tuple[bool, float, float, float]: ...
```

Add immediately after it:

```python
    @staticmethod
    def Button(label: str) -> bool: ...
```

- [ ] **Step 8: Export `TimerQuery` from `src/pydonut/__init__.py`**

Find this exact line (currently line 61):

```python
from pydonut._pydonut import Shader
```

Add immediately after it:

```python
from pydonut._pydonut import TimerQuery
```

Then find this exact line in the `__all__` list (currently line 226):

```python
    'Shader',
```

Add immediately after it:

```python
    'TimerQuery',
```

- [ ] **Step 9: Verify the new bindings are importable**

Run: `uv run python -c "from src import pydonut as pyd; print(pyd.TimerQuery, pyd.ImGui.Button)"`
Expected: prints the two class/function objects with no `ImportError`/`AttributeError`.

- [ ] **Step 10: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py
git commit -m "Add ImGui.Button and CommandList timer-query bindings

Also expose the pre-existing TimerQuery/Device timer-query C++
bindings through __init__.py and the .pyi stubs -- needed for
work_graphs.py's upcoming Options/Stats window."
```

---

### Task 2: `WorkGraphs` — `UIData`, technique sync, pause/reset, GPU timer ring buffer

**Files:**
- Modify: `work_graphs.py:501-523` (`WorkGraphs.__init__`, remove `toggle_technique` call-site assumptions)
- Modify: `work_graphs.py:796-817` (`populate_animation_pass`)
- Modify: `work_graphs.py:905-940` (`render`)
- Modify: `work_graphs.py:942-944` (`animate`)
- Insert new `UIData` class immediately before `class WorkGraphs:` (currently line 501)

**Interfaces:**
- Consumes: `pyd.TimerQuery`, `device.createTimerQuery()`, `device.pollTimerQuery(query)`, `device.getTimerQueryTime(query)`, `device.resetTimerQuery(query)`, `commandList.beginTimerQuery(query)`, `commandList.endTimerQuery(query)` (Task 1).
- Produces: `UIData` (fields: `currentTechnique: int` default `0`, `paused: bool` default `False`, `resetAnim: bool` default `False`, `gpuFrameTime: float` default `0.0`, `gpuShadingTime: float` default `0.0`). `WorkGraphs.__init__(self, device, ui: UIData)`. Task 3's `UIRenderer` and the bootstrap consume `UIData` and construct `WorkGraphs(device, uiData)`.

- [ ] **Step 1: Add the `UIData` class**

In `work_graphs.py`, find this exact line (currently line 501):

```python
    class WorkGraphs:
```

Insert immediately before it:

```python
    class UIData:
        def __init__(self) -> None:
            # 0 = Work Graph (Broadcast Launch), 1 = Compute Dispatches -- same order/index as
            # the combo built in UIRenderer.buildUI, matching work_graphs_d3d12.cpp's
            # techniqueNames array and UIData::CurrentTechnique's default of 0.
            self.currentTechnique = 0
            self.paused = False
            self.resetAnim = False
            self.gpuFrameTime = 0.0
            self.gpuShadingTime = 0.0

    class WorkGraphs:
```

- [ ] **Step 2: Wire `UIData` into `WorkGraphs.__init__`, default to the Work Graph technique, and create the timer-query ring buffers**

Find this exact block (currently lines 502-516):

```python
        def __init__(self, device) -> None:
            self.device = device
            self.scene = Scene()
            self.render_targets = None
            self.time_in_seconds = 0.0
            self.time_diff_this_frame = 0.0
            self.force_reset_animation = True
            # Which shading technique to use. Set from the command line, toggled with SPACE.
            # Only honoured once load_scene_pipelines has actually built a work graph -- see
            # use_work_graph_now().
            self.want_work_graph = False
            self.work_graph_pipeline = None
            self.work_graph_backing = None
            self.init_work_graph_backing = True
```

Replace it with:

```python
        _TIMER_RING_SIZE = 10  # matches work_graphs_d3d12.cpp's QueuedFramesCount

        def __init__(self, device, ui) -> None:
            self.device = device
            self.ui = ui
            self.scene = Scene()
            self.render_targets = None
            self.time_in_seconds = 0.0
            self.time_diff_this_frame = 0.0
            self.force_reset_animation = True
            # Which shading technique to use, synchronized from ui.currentTechnique each
            # Animate() call (see animate() below). Only honoured once load_scene_pipelines has
            # actually built a work graph -- see use_work_graph_now(). Starts True to match
            # work_graphs_d3d12.cpp's m_CurrentTechnique default of
            # Techniques::WorkGraphBroadcastingLaunch (== ui.currentTechnique's default of 0).
            self.want_work_graph = ui.currentTechnique == 0
            self.work_graph_pipeline = None
            self.work_graph_backing = None
            self.init_work_graph_backing = True

            self.next_timer_to_use = 0
            self.frame_timers = [device.createTimerQuery() for _ in range(self._TIMER_RING_SIZE)]
            self.shading_timers = [device.createTimerQuery() for _ in range(self._TIMER_RING_SIZE)]

        def _get_last_valid_query_timer(self, timers) -> float:
            # Ports work_graphs_d3d12.cpp's GetLastValidQueryTimer: search backward from just
            # before the ring-buffer slot about to be reused, then wrap around to the end --
            # this always finds the most recently completed query without stalling on one still
            # in flight. Returns milliseconds, or -1.0 if nothing has completed yet.
            device = self.device
            for i in range(self.next_timer_to_use - 1, -1, -1):
                if device.pollTimerQuery(timers[i]):
                    return device.getTimerQueryTime(timers[i]) * 1000.0
            for i in range(self._TIMER_RING_SIZE - 1, self.next_timer_to_use, -1):
                if device.pollTimerQuery(timers[i]):
                    return device.getTimerQueryTime(timers[i]) * 1000.0
            return -1.0
```

- [ ] **Step 3: Honor `ui.resetAnim` in `populate_animation_pass`**

Find this exact line (currently line 797):

```python
            resetAnim = self.force_reset_animation
```

Replace it with:

```python
            resetAnim = self.force_reset_animation or self.ui.resetAnim
```

- [ ] **Step 4: Wrap `render()` with the GPU frame/shading timer queries**

Find this exact block (currently lines 923-931):

```python
            self.update_scene_constants(commandList, view)
            self.populate_animation_pass(commandList)
            self.populate_gbuffer_pass(commandList, self.render_targets.framebuffer_gb.GetFramebuffer(view))
            if self.use_work_graph_now():
                # One launch replaces both the light-culling and deferred-shading dispatches.
                self.populate_deferred_shading_work_graph(commandList)
            else:
                self.populate_light_culling_pass(commandList)
                self.populate_deferred_shading_pass(commandList)
```

Replace it with:

```python
            timerIndex = self.next_timer_to_use
            self.device.resetTimerQuery(self.frame_timers[timerIndex])
            self.device.resetTimerQuery(self.shading_timers[timerIndex])
            commandList.beginTimerQuery(self.frame_timers[timerIndex])

            self.update_scene_constants(commandList, view)
            self.populate_animation_pass(commandList)
            self.populate_gbuffer_pass(commandList, self.render_targets.framebuffer_gb.GetFramebuffer(view))
            commandList.beginTimerQuery(self.shading_timers[timerIndex])
            if self.use_work_graph_now():
                # One launch replaces both the light-culling and deferred-shading dispatches.
                self.populate_deferred_shading_work_graph(commandList)
            else:
                self.populate_light_culling_pass(commandList)
                self.populate_deferred_shading_pass(commandList)
            commandList.endTimerQuery(self.shading_timers[timerIndex])
```

Then find this exact block (currently lines 933-940, immediately following the block just replaced):

```python
            # Plain GPU bit copy, matching work_graphs_d3d12.cpp:880's own
            # commandList->copyTexture(...) exactly. Deliberately NOT
            # CommonRenderPasses.BlitTexture: the swap chain is SRGBA8_UNORM while the LDR
            # buffer is RGBA8_UNORM, so a shader blit would resolve through an sRGB render
            # target and re-encode pixels this shader already wrote in final display form.
            # copyTexture moves the bits untouched, which is what the original sample does.
            backbufferTexture = backbuffer.getDesc().getColorAttachment(0).texture
            commandList.copyTexture(backbufferTexture, self.render_targets.ldr_buffer)
```

Replace it with:

```python
            # Plain GPU bit copy, matching work_graphs_d3d12.cpp:880's own
            # commandList->copyTexture(...) exactly. Deliberately NOT
            # CommonRenderPasses.BlitTexture: the swap chain is SRGBA8_UNORM while the LDR
            # buffer is RGBA8_UNORM, so a shader blit would resolve through an sRGB render
            # target and re-encode pixels this shader already wrote in final display form.
            # copyTexture moves the bits untouched, which is what the original sample does.
            backbufferTexture = backbuffer.getDesc().getColorAttachment(0).texture
            commandList.copyTexture(backbufferTexture, self.render_targets.ldr_buffer)

            commandList.endTimerQuery(self.frame_timers[timerIndex])
            self.next_timer_to_use = (self.next_timer_to_use + 1) % self._TIMER_RING_SIZE
```

- [ ] **Step 5: Honor pause/reset/technique-switch and update GPU timing stats in `animate()`**

Find this exact block (currently lines 942-944):

```python
        def animate(self, elapsed: float) -> None:
            self.time_diff_this_frame = elapsed
            self.time_in_seconds += elapsed
```

Replace it with:

```python
        def animate(self, elapsed: float) -> None:
            if not self.ui.paused:
                self.time_diff_this_frame = elapsed
                self.time_in_seconds += elapsed
            else:
                self.time_diff_this_frame = 0.0

            if self.force_reset_animation or self.ui.resetAnim:
                self.time_in_seconds = 0.0
                self.time_diff_this_frame = 0.0

            wantWorkGraph = self.ui.currentTechnique == 0
            if wantWorkGraph != self.want_work_graph:
                self.toggle_technique()
                if self.want_work_graph and self.work_graph_pipeline is None:
                    pyd.log.warning("Work graph technique is unavailable on this device/driver.")

            self.ui.gpuFrameTime = self._get_last_valid_query_timer(self.frame_timers)
            self.ui.gpuShadingTime = self._get_last_valid_query_timer(self.shading_timers)
```

- [ ] **Step 6: Confirm the file still parses and imports cleanly**

Run: `uv run python -c "import ast; ast.parse(open('work_graphs.py', encoding='utf-8').read())"`
Expected: no output, exit code 0 (Task 3 still needs to update the bootstrap's `WorkGraphs(device)` call site and remove the CLI flag, so `work_graphs.py` will not run correctly end-to-end until Task 3 is done — this step only confirms no syntax errors).

- [ ] **Step 7: Commit**

```bash
git add work_graphs.py
git commit -m "Add UIData, GPU timer-query ring buffer, pause/reset to WorkGraphs

Ports work_graphs_d3d12.cpp's UIData-driven Animate()/Render() timer
bookkeeping verbatim. WorkGraphs now requires a UIData instance and
defaults to the Work Graph technique, matching the C++ original's
m_CurrentTechnique default. The bootstrap wiring (UIRenderer, render
pass registration) lands in the next commit."
```

---

### Task 3: `UIRenderer` and bootstrap wiring

**Files:**
- Modify: `work_graphs.py:946-1020` (bootstrap tail: `is_debug` through `print("Done.")`)
- Insert new `UIRenderer` class immediately before the bootstrap tail (after `class WorkGraphs:` closes, i.e. immediately before the current `if "--scene-smoke-test" in sys.argv:` line, currently line 946)

**Interfaces:**
- Consumes: `UIData`, `WorkGraphs(device, ui)` (Task 2); `pyd.ImGui_Renderer`, `pyd.ImGui.*` (Task 1 + pre-existing); `pyd.RootFileSystem`, `pyd.ShaderFactory`, `pyd.GetShaderTypeName` (pre-existing, same pattern as `rt_particles.py`).
- Produces: a fully working `work_graphs.py` — no later task depends on this one.

- [ ] **Step 1: Add the `UIRenderer` class**

Find this exact line (currently line 946):

```python
    if "--scene-smoke-test" in sys.argv:
```

Insert immediately before it:

```python
    class UIRenderer(pyd.ImGui_Renderer):
        def __init__(self, deviceManager, ui) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            pyd.ImGui.DisableIniFile()

        def buildUI(self) -> None:
            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Options/Stats", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            _, self.ui.currentTechnique = pyd.ImGui.Combo(
                "Current Technique", self.ui.currentTechnique,
                ["Work Graph (Broadcast Launch)", "Compute Dispatches"],
            )
            _, self.ui.paused = pyd.ImGui.Checkbox("Pause Animation", self.ui.paused)
            self.ui.resetAnim = pyd.ImGui.Button("Reset Animation")
            pyd.ImGui.Text(f"Frame Time (GPU): {self.ui.gpuFrameTime:.3f} ms")
            pyd.ImGui.Text(f"Shading Time (GPU): {self.ui.gpuShadingTime:.3f} ms")

            pyd.ImGui.End()

    if "--scene-smoke-test" in sys.argv:
```

- [ ] **Step 2: Add the `_IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE` module-level constant**

Find this exact line (currently line 10, immediately after `folder = Path(__file__).resolve().parent`):

```python
    folder = Path(__file__).resolve().parent
```

Add immediately after it:

```python

    # ImGuiWindowFlags_AlwaysAutoResize -- same constant rt_particles.py already defines for
    # the same purpose.
    _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE = 64
```

- [ ] **Step 3: Rewrite the bootstrap tail**

Find this exact block (currently lines 954-1019, from `api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)` through the line before `print("Done.")`):

```python
    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True
    deviceParams.backBufferWidth = 1920
    deviceParams.backBufferHeight = 1080

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Work Graphs (Dispatch)"):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    device = deviceManager.GetDevice()
    wg = WorkGraphs(device)
    commandList = device.createCommandList()
    commandList.open()
    wg.init_scene(commandList)
    commandList.close()
    device.executeCommandList(commandList)
    device.waitForIdle()

    # Technique selection. The C++ sample exposes this as an ImGui combo; this port has no
    # ImGui, so it is a command line flag plus a SPACE toggle. Both techniques must produce
    # the same image -- that equivalence is the whole point of the sample.
    wg.want_work_graph = "--work-graph" in sys.argv

    view = pyd.PlanarView()

    GLFW_KEY_SPACE = 32
    GLFW_PRESS = 1

    class RenderPass(pyd.IRenderPass):
        def __init__(self, deviceManager) -> None:
            super().__init__(deviceManager)

        def Render(self, framebuffer) -> None:
            commandList.open()
            wg.render(commandList, view, framebuffer)
            commandList.close()
            device.executeCommandList(commandList)
            technique = "Work Graph (Broadcasting Launch)" if wg.use_work_graph_now() else "Dispatch"
            deviceManager.SetInformativeWindowTitle(f"PyDonut Work Graphs [{technique}] - SPACE to switch")

        def Animate(self, elapsedTimeSeconds: float) -> None:
            wg.animate(elapsedTimeSeconds)

        def KeyboardUpdate(self, key: int, scancode: int, action: int, mods: int) -> bool:
            if key == GLFW_KEY_SPACE and action == GLFW_PRESS:
                wg.toggle_technique()
                if wg.want_work_graph and wg.work_graph_pipeline is None:
                    pyd.log.warning("Work graph technique is unavailable on this device/driver.")
            return True

    renderPass = RenderPass(deviceManager)
    deviceManager.AddRenderPassToBack(renderPass)
    deviceManager.RunMessageLoop()
    deviceManager.RemoveRenderPass(renderPass)
    deviceManager.Shutdown()
```

Replace it with:

```python
    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True
    deviceParams.backBufferWidth = 1920
    deviceParams.backBufferHeight = 1080

    WINDOW_TITLE = "PyDonut Work Graphs"

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    device = deviceManager.GetDevice()

    uiData = UIData()
    wg = WorkGraphs(device, uiData)
    commandList = device.createCommandList()
    commandList.open()
    wg.init_scene(commandList)
    commandList.close()
    device.executeCommandList(commandList)
    device.waitForIdle()

    view = pyd.PlanarView()

    class RenderPass(pyd.IRenderPass):
        def __init__(self, deviceManager) -> None:
            super().__init__(deviceManager)

        def Render(self, framebuffer) -> None:
            commandList.open()
            wg.render(commandList, view, framebuffer)
            commandList.close()
            device.executeCommandList(commandList)
            deviceManager.SetInformativeWindowTitle(WINDOW_TITLE)

        def Animate(self, elapsedTimeSeconds: float) -> None:
            wg.animate(elapsedTimeSeconds)

    # Framework shaders (needed only so UIRenderer.Init() can load ImGui's own vertex/pixel
    # shaders) -- same RootFileSystem/ShaderFactory mount convention rt_particles.py uses.
    rootFS = pyd.RootFileSystem()
    frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
    rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
    uiShaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))

    renderPass = RenderPass(deviceManager)
    gui = UIRenderer(deviceManager, uiData)

    if not gui.Init(uiShaderFactory):
        pyd.log.fatal("Failed to initialize the ImGui renderer")
        sys.exit(1)

    deviceManager.AddRenderPassToBack(renderPass)
    deviceManager.AddRenderPassToBack(gui)
    deviceManager.RunMessageLoop()
    deviceManager.RemoveRenderPass(gui)
    deviceManager.RemoveRenderPass(renderPass)
    deviceManager.Shutdown()
```

- [ ] **Step 4: Run the example on Vulkan and confirm the Options/Stats window works**

Run: `uv run work_graphs.py -vk` (background it or bound it with a timeout — this opens a window and runs the message loop; a few seconds is enough to confirm no crash and visually check the window)
Expected: reaches "DeviceManager created successfully"-equivalent startup with no exception; the scene renders (multiple floors, moving spot lights, animated cuboids/spheres, procedural sky); an "Options/Stats" window appears at the top-left showing a "Current Technique" combo (starting on "Work Graph (Broadcast Launch)"), a "Pause Animation" checkbox, a "Reset Animation" button, and two `Frame Time (GPU)`/`Shading Time (GPU)` lines whose numbers update every frame (not stuck at 0.000 or -1.000 after the first ~10 frames).

- [ ] **Step 5: Exercise the controls manually**

While the window from Step 4 is open: switch the combo to "Compute Dispatches" and confirm the rendered image stays visually equivalent to the Work Graph technique (same invariant the old SPACE toggle validated); switch back; check "Pause Animation" and confirm the scene freezes; click "Reset Animation" and confirm objects/lights snap back to their start-of-animation state; uncheck pause and confirm animation resumes smoothly (no time jump).
Expected: all five behaviors match, matching `work_graphs_d3d12.cpp`'s own UI.

- [ ] **Step 6: Run the example on D3D12 (Windows only)**

Run: `uv run work_graphs.py` (defaults to D3D12 on Windows per `GetGraphicsAPIFromCommandLine`)
Expected: same as Step 4/5 — confirms the work-graph-broadcasting-launch path (D3D12-only) also drives correctly through the new UI, including a real (not `-1.000`) Shading Time reading while on the Work Graph technique.

- [ ] **Step 7: Regression check — `headless.py`**

Run: `uv run headless.py`
Expected: passes, same as before this change (confirms the new bindings didn't break anything else built against the same native module).

- [ ] **Step 8: Commit**

```bash
git add work_graphs.py
git commit -m "Add ImGui Options/Stats window to work_graphs.py

Replaces the CLI --work-graph flag and SPACE-key toggle with the
technique combo, pause/reset controls, and GPU timing display from
work_graphs_d3d12.cpp's UIRenderer, wired in as a second render pass
matching rt_particles.py's UserInterface pattern."
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 covers the spec's "New native bindings" section (including the two pre-existing gaps discovered while reading the current binding surface — `TimerQuery`/.pyi — which the spec's "already bound" note implicitly assumed were already exposed to Python; they were not, so this plan closes that gap as part of the same task rather than leaving it half-done). Task 2 covers `UIData`, technique sync, pause/reset, and the timer-query ring buffer. Task 3 covers `UIRenderer.buildUI`, the bootstrap rewrite (CLI flag/SPACE removal, static title, RootFileSystem/ShaderFactory, two render passes), and all spec Verification steps.
- **Type consistency:** `WorkGraphs.__init__(self, device, ui)` (Task 2 Step 2) matches the `WorkGraphs(device, uiData)` call site (Task 3 Step 3). `UIData` field names (`currentTechnique`, `paused`, `resetAnim`, `gpuFrameTime`, `gpuShadingTime`) are identical everywhere they're read/written across Tasks 2 and 3. `_get_last_valid_query_timer`/`frame_timers`/`shading_timers`/`next_timer_to_use`/`_TIMER_RING_SIZE` names introduced in Task 2 Step 2 are the only names Task 2 Steps 4-5 reference.
- **No placeholders:** every step shows the literal before/after code; nothing is left as "add similar logic" or "TBD".
