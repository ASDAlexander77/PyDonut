if __name__ == "__main__":
    import sys
    from pathlib import Path
    from typing import Optional
    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Basic Triangle"
    folder = Path(__file__).resolve().parent

    class BasicTriangle(pyd.IRenderPass):
        def __init__(self: BasicTriangle, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.vertexShader: Optional[pyd.Shader] = None
            self.pixelShader: Optional[pyd.Shader] = None
            self.pipeline: Optional[pyd.GraphicsPipeline] = None
            self.commandList: Optional[pyd.CommandList] = None

        def Init(self: BasicTriangle) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "basic_triangle" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                vsBytecode = pyd.CompileShader(source, "main_vs", pyd.ShaderType.Vertex, api, sourceName=shaderPath.name)
                psBytecode = pyd.CompileShader(source, "main_ps", pyd.ShaderType.Pixel, api, sourceName=shaderPath.name)
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.vertexShader = device.createShader(vsBytecode, "main_vs", pyd.ShaderType.Vertex)
            self.pixelShader = device.createShader(psBytecode, "main_ps", pyd.ShaderType.Pixel)

            if not self.vertexShader or not self.pixelShader:
                return False

            self.commandList = device.createCommandList()

            return True

        def BackBufferResizing(self: BasicTriangle):
            self.pipeline = None

        def Animate(self: BasicTriangle, elapsedTimeSeconds: float):
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def Render(self: BasicTriangle, framebuffer: pyd.Framebuffer):
            device = self.GetDevice()
            assert self.commandList is not None

            if not self.pipeline:
                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.vertexShader
                psoDesc.PS = self.pixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.renderState.depthStencilState.depthTestEnable = False

                self.pipeline = device.createGraphicsPipeline(psoDesc, framebuffer.getFramebufferInfo())

            self.commandList.open()

            pyd.ClearColorAttachment(self.commandList, framebuffer, 0, pyd.Color(0.0))

            state = pyd.GraphicsState()
            state.pipeline = self.pipeline
            state.framebuffer = framebuffer
            state.viewport.addViewportAndScissorRect(framebuffer.getFramebufferInfo().getViewport())

            self.commandList.setGraphicsState(state)

            args = pyd.DrawArguments()
            args.vertexCount = 3
            self.commandList.draw(args)

            self.commandList.close()
            device.executeCommandList(self.commandList)

    is_debug = "-debug" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        exit(1)

    example = BasicTriangle(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")