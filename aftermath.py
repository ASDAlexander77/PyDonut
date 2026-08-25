# /******************************************************************************
# * Copyright (C) 1991-2026 ASDAlexander77.
# *
# * Permission is hereby granted, free of charge, to any person obtaining
# * a copy of this software and associated documentation files (the
# * "Software"), to deal in the Software without restriction, including
# * without limitation the rights to use, copy, modify, merge, publish,
# * distribute, sublicense, and/or sell copies of the Software, and to
# * permit persons to whom the Software is furnished to do so, subject to
# * the following conditions:
# *
# * The above copyright notice and this permission notice shall be
# * included in all copies or substantial portions of the Software.
# *
# * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# * IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# * CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# * TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ******************************************************************************/

"""NSight Aftermath GPU crash dump example (port of Donut's aftermath.cpp).

Draws one triangle and offers two buttons that deliberately crash the GPU:

  * "Trigger timeout"    -- the vertex shader spins forever, tripping Windows' TDR
                            watchdog (2s by default), which resets the display driver.
  * "Trigger page fault" -- the buffer's native API memory is destroyed while a shader
                            is reading it.

Either one resets the display driver: the screen blanks, this process dies, and other
GPU applications may die with it. Nothing here is recoverable by design.

Crash dumps are only written when the module was built with -DPYDONUT_WITH_AFTERMATH=ON
(check pyd.AFTERMATH_AVAILABLE). Without it the crashes still happen, just uncaptured.

WHERE THE DUMPS GO: donut writes them to GetDirectoryWithExecutable() / "crash_<timestamp>"
(AftermathCrashDump.cpp:206), containing crash.nv-gpudmp plus a .nvdbg per shader. NOT to
"Documents/NVIDIA Corporation/CrashDump" -- that is the NSight Aftermath Monitor's folder,
and once an app calls GFSDK_Aftermath_EnableGpuCrashDumps it owns the dump itself.

GetDirectoryWithExecutable() is GetModuleFileNameA(nullptr, ...), which reports the REAL
running image, not sys.executable. A uv-created venv's Scripts/python.exe is only a
trampoline, so dumps land beside the BASE interpreter, e.g.

    %APPDATA%/uv/python/cpython-3.14.0-windows-x86_64-none/crash_<timestamp>/

The absolute path is logged ("Aftermath crash dump written: ...") when the dump is written;
it scrolls by as the display driver resets, so check the folder above if you miss it.
"""

from __future__ import annotations

if __name__ == "__main__":
    import struct
    import sys
    from enum import IntEnum
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Aftermath"
    folder = Path(__file__).resolve().parent

    # ImGuiWindowFlags_AlwaysAutoResize -- same constant work_graphs.py and rt_particles.py
    # already define locally rather than binding the whole ImGuiWindowFlags enum.
    _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE = 64

    class CrashType(IntEnum):
        """Values must match the shader's g_constants.crashType comparisons."""

        NONE = 0
        TIMEOUT = 1
        PAGEFAULT = 2

    class UIData:
        """Shared by reference between AftermathSample and UIRenderer.

        Replaces the C++ original's UIRenderer-holds-AftermathSample& plus SetCrashType
        setter, matching how work_graphs.py and rt_particles.py share their UIData.
        """

        def __init__(self: UIData) -> None:
            self.crashType: CrashType = CrashType.NONE

    class AftermathSample(pyd.IRenderPass):
        def __init__(
            self: AftermathSample, deviceManager: pyd.DeviceManager, ui: UIData
        ) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            self.vertexShader: pyd.Shader | None = None
            self.pixelShader: pyd.Shader | None = None
            self.pipeline: pyd.GraphicsPipeline | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.commandList: pyd.CommandList | None = None
            self.buffer: pyd.Buffer | None = None
            self.waitingForCrash = False

        def Init(self: AftermathSample) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "aftermath" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                vsBytecode = pyd.CompileShader(
                    source,
                    "main_vs",
                    pyd.ShaderType.Vertex,
                    api,
                    sourceName=shaderPath.name,
                )
                psBytecode = pyd.CompileShader(
                    source,
                    "main_ps",
                    pyd.ShaderType.Pixel,
                    api,
                    sourceName=shaderPath.name,
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.vertexShader = device.createShader(
                vsBytecode, "main_vs", pyd.ShaderType.Vertex
            )
            self.pixelShader = device.createShader(
                psBytecode, "main_ps", pyd.ShaderType.Pixel
            )

            if not self.vertexShader or not self.pixelShader:
                return False

            self.commandList = device.createCommandList()

            bufDesc = pyd.BufferDesc()
            bufDesc.byteSize = 1024
            bufDesc.canHaveUAVs = True
            bufDesc.debugName = "Aftermath test buffer"
            bufDesc.format = pyd.Format.R32_FLOAT
            bufDesc.initialState = pyd.ResourceStates.UnorderedAccess
            bufDesc.keepInitialState = True
            bufDesc.structStride = 4  # sizeof(float)
            self.buffer = device.createBuffer(bufDesc)

            self.waitingForCrash = False

            return True

        def BackBufferResizing(self: AftermathSample) -> None:
            self.pipeline = None

        def Animate(self: AftermathSample, elapsedTimeSeconds: float) -> None:
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def Render(self: AftermathSample, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.buffer is not None

            if not self.pipeline:
                bindingLayoutDesc = pyd.BindingLayoutDesc()
                bindingLayoutDesc.visibility = pyd.ShaderType.All
                bindingLayoutDesc.bindings = [
                    pyd.BindingLayoutItem.PushConstants(0, 4),
                    pyd.BindingLayoutItem.StructuredBuffer_UAV(0),
                ]
                self.bindingLayout = device.createBindingLayout(bindingLayoutDesc)

                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.PushConstants(0, 4),
                    pyd.BindingSetItem.StructuredBuffer_UAV(0, self.buffer),
                ]
                self.bindingSet = device.createBindingSet(
                    bindingSetDesc, self.bindingLayout
                )

                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.vertexShader
                psoDesc.PS = self.pixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.renderState.depthStencilState.depthTestEnable = False
                # NOT psoDesc.bindingLayouts = [...] -- GraphicsPipelineDesc exposes no such
                # list property in this binding, only addBindingLayout.
                psoDesc.addBindingLayout(self.bindingLayout)

                self.pipeline = device.createGraphicsPipeline(
                    psoDesc, framebuffer.getFramebufferInfo()
                )

            self.commandList.open()
            self.commandList.beginMarker("Frame")

            # One way to cause a page fault is to destroy a resource that is in use. Destroying
            # the nvrhi resource would crash on the CPU before the GPU ever faults, so the
            # native graphics API object is destroyed directly instead.
            if self.ui.crashType == CrashType.PAGEFAULT and not self.waitingForCrash:
                pyd.DestroyBufferMemory_UnsafeForCrashTesting(device, self.buffer)
                self.commandList.setEnableAutomaticBarriers(False)
                self.waitingForCrash = True

            self.commandList.beginMarker("Clear")
            pyd.ClearColorAttachment(self.commandList, framebuffer, 0, pyd.Color(0.0))
            self.commandList.endMarker()

            self.commandList.beginMarker("Draw Triangle")
            state = pyd.GraphicsState()
            state.pipeline = self.pipeline
            state.framebuffer = framebuffer
            state.viewport.addViewportAndScissorRect(
                framebuffer.getFramebufferInfo().getViewport()
            )
            state.addBindingSet(self.bindingSet)

            self.commandList.setGraphicsState(state)

            # The C++ original passes &m_CrashType with sizeof(uint32_t); the binding takes a
            # buffer object, so the enum is packed explicitly as one little-endian uint32.
            self.commandList.setPushConstants(struct.pack("<I", int(self.ui.crashType)))

            args = pyd.DrawArguments()
            args.vertexCount = 3
            self.commandList.draw(args)
            self.commandList.endMarker()

            self.commandList.endMarker()
            self.commandList.close()

            device.executeCommandList(self.commandList)

    class UIRenderer(pyd.ImGui_Renderer):
        def __init__(
            self: UIRenderer,
            deviceManager: pyd.DeviceManager,
            ui: UIData,
            api: pyd.GraphicsAPI,
        ) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            self.api = api
            pyd.ImGui.DisableIniFile()

        def buildUI(self: UIRenderer) -> None:
            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Controls", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            if pyd.ImGui.Button("Trigger timeout"):
                self.ui.crashType = CrashType.TIMEOUT

            # d3d11 does not page fault in these conditions, so short circuit showing the
            # button in d3d11
            if self.api != pyd.GraphicsAPI.D3D11 and pyd.ImGui.Button("Trigger page fault"):
                self.ui.crashType = CrashType.PAGEFAULT

            if not pyd.AFTERMATH_AVAILABLE:
                pyd.ImGui.Separator()
                pyd.ImGui.Text("Crash dumps DISABLED in this build.")
                pyd.ImGui.Text("The crashes will still reset the GPU.")

            pyd.ImGui.End()

    is_debug = "-debug" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        # NOTE: unlike every other example in this repo, enableDebugRuntime is deliberately
        # NOT set here even under -debug -- Aftermath is incompatible with the D3D debug
        # layer (aftermath.cpp:253-254). Only the NVRHI validation layer is enabled.
        print("Debug mode is enabled (D3D debug runtime stays off for Aftermath).")
        deviceParams.enableNvrhiValidationLayer = True

    if pyd.AFTERMATH_AVAILABLE:
        deviceParams.enableAftermath = True
    else:
        print(
            "WARNING: this build has no Aftermath support, so no crash dump will be written.\n"
            "         The crash buttons still reset the GPU. To enable dumps, rebuild with:\n"
            "         SKBUILD_CMAKE_DEFINE=PYDONUT_WITH_AFTERMATH=ON "
            "uv sync --reinstall-package pydonut"
        )

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal(
            "Cannot initialize a graphics device with the requested parameters"
        )
        sys.exit(1)

    device = deviceManager.GetDevice()

    # Framework shaders (needed only so UIRenderer.Init() can load ImGui's own vertex/pixel
    # shaders) -- same RootFileSystem/ShaderFactory mount convention work_graphs.py uses.
    rootFS = pyd.RootFileSystem()
    frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
    rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
    uiShaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))

    uiData = UIData()
    example = AftermathSample(deviceManager, uiData)
    gui = UIRenderer(deviceManager, uiData, api)

    if example.Init() and gui.Init(uiShaderFactory):
        deviceManager.AddRenderPassToBack(example)
        deviceManager.AddRenderPassToBack(gui)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(gui)
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")
