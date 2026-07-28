if __name__ == "__main__":
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Meshlets"
    folder = Path(__file__).resolve().parent

    class Meshlets(pyd.IRenderPass):
        def __init__(self: Meshlets, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.amplificationShader: pyd.Shader | None = None
            self.meshShader: pyd.Shader | None = None
            self.pixelShader: pyd.Shader | None = None
            self.pipeline: pyd.MeshletPipeline | None = None
            self.commandList: pyd.CommandList | None = None

        def Init(self: Meshlets) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "meshlets" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                asBytecode = pyd.CompileShader(
                    source,
                    "main_as",
                    pyd.ShaderType.Amplification,
                    api,
                    sourceName=shaderPath.name,
                )
                msBytecode = pyd.CompileShader(
                    source,
                    "main_ms",
                    pyd.ShaderType.Mesh,
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

            self.amplificationShader = device.createShader(
                asBytecode, "main_as", pyd.ShaderType.Amplification
            )
            self.meshShader = device.createShader(
                msBytecode, "main_ms", pyd.ShaderType.Mesh
            )
            self.pixelShader = device.createShader(
                psBytecode, "main_ps", pyd.ShaderType.Pixel
            )

            if not self.amplificationShader or not self.meshShader or not self.pixelShader:
                return False

            self.commandList = device.createCommandList()

            return True

        def Animate(self: Meshlets, elapsedTimeSeconds: float):
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: Meshlets):
            self.pipeline = None

        def Render(self: Meshlets, framebuffer: pyd.Framebuffer):
            device = self.GetDevice()
            assert self.commandList is not None

            if not self.pipeline:
                psoDesc = pyd.MeshletPipelineDesc()
                psoDesc.AS = self.amplificationShader
                psoDesc.MS = self.meshShader
                psoDesc.PS = self.pixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.renderState.depthStencilState.depthTestEnable = False

                self.pipeline = device.createMeshletPipeline(
                    psoDesc, framebuffer.getFramebufferInfo()
                )

            self.commandList.open()

            pyd.ClearColorAttachment(self.commandList, framebuffer, 0, pyd.Color(0.0))

            state = pyd.MeshletState()
            state.pipeline = self.pipeline
            state.framebuffer = framebuffer
            state.viewport.addViewportAndScissorRect(
                framebuffer.getFramebufferInfo().getViewport()
            )

            self.commandList.setMeshletState(state)

            self.commandList.dispatchMesh(1)

            self.commandList.close()
            device.executeCommandList(self.commandList)

    is_debug = "-debug" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        pyd.log.fatal(
            "Cannot initialize a graphics device with the requested parameters"
        )
        sys.exit(1)

    if not deviceManager.GetDevice().queryFeatureSupport(
        pyd.Feature.Meshlets
    ):
        pyd.log.fatal("The graphics device does not support Meshlets")
        sys.exit(1)

    example = Meshlets(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
