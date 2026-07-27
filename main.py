if __name__ == "__main__":
    import sys
    from typing import Optional
    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Basic Triangle"

    class BasicTriangle(pyd.IRenderPass):
        def __init__(self: BasicTriangle, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.m_VertexShader: Optional[pyd.Shader] = None
            self.m_PixelShader: Optional[pyd.Shader] = None
            self.m_Pipeline: Optional[pyd.GraphicsPipeline] = None
            self.m_CommandList: Optional[pyd.CommandList] = None

        def Init(self: BasicTriangle) -> bool:
            device = self.GetDevice()
            appShaderPath = pyd.GetDirectoryWithExecutable() / "shaders" / "basic_triangle" / pyd.GetShaderTypeName(device.getGraphicsAPI())

            nativeFS = pyd.NativeFileSystem()
            shaderFactory = pyd.ShaderFactory(device, nativeFS, appShaderPath)

            self.m_VertexShader = shaderFactory.CreateShader("shaders.hlsl", "main_vs", pyd.ShaderType.Vertex)
            self.m_PixelShader = shaderFactory.CreateShader("shaders.hlsl", "main_ps", pyd.ShaderType.Pixel)

            if not self.m_VertexShader or not self.m_PixelShader:
                return False

            self.m_CommandList = device.createCommandList()

            return True

        def BackBufferResizing(self: BasicTriangle):
            self.m_Pipeline = None

        def Animate(self: BasicTriangle, elapsedTimeSeconds: float):
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def Render(self: BasicTriangle, framebuffer: pyd.Framebuffer):
            device = self.GetDevice()
            assert self.m_CommandList is not None

            if not self.m_Pipeline:
                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.m_VertexShader
                psoDesc.PS = self.m_PixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.renderState.depthStencilState.depthTestEnable = False

                self.m_Pipeline = device.createGraphicsPipeline(psoDesc, framebuffer.getFramebufferInfo())

            self.m_CommandList.open()

            pyd.ClearColorAttachment(self.m_CommandList, framebuffer, 0, pyd.Color(0.0))

            state = pyd.GraphicsState()
            state.pipeline = self.m_Pipeline
            state.framebuffer = framebuffer
            state.viewport.addViewportAndScissorRect(framebuffer.getFramebufferInfo().getViewport())

            self.m_CommandList.setGraphicsState(state)

            args = pyd.DrawArguments()
            args.vertexCount = 3
            self.m_CommandList.draw(args)

            self.m_CommandList.close()
            device.executeCommandList(self.m_CommandList)


    is_debug = "--debug" in sys.argv or "-d" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        print("Failed to create DeviceManager.", file=sys.stderr)
        exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        print("Cannot initialize a graphics device with the requested parameters", file=sys.stderr)
        exit(1)

    example = BasicTriangle(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")