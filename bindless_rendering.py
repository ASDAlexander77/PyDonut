if __name__ == "__main__":
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Bindless Rendering"
    folder = Path(__file__).resolve().parent
    donutIncludeDir = folder / "extern" / "donut" / "include"

    def FindSponzaGltf() -> Path | None:
        # The C++ sample resolves this via GetDirectoryWithExecutable().parent_path() /
        # "media/...", i.e. a media/ folder that ships alongside the built samples.
        candidate = folder / "media" / "glTF-Sample-Assets" / "Models" / "Sponza" / "glTF" / "Sponza.gltf"
        return candidate if candidate.is_file() else None

    class BindlessRendering(pyd.IRenderPass):
        def __init__(self: BindlessRendering, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.vertexShader: pyd.Shader | None = None
            self.pixelShader: pyd.Shader | None = None
            self.pipeline: pyd.GraphicsPipeline | None = None
            self.commandList: pyd.CommandList | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindlessLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.viewConstantsBuffer: pyd.Buffer | None = None
            self.descriptorTableManager: pyd.DescriptorTableManager | None = None
            self.scene: pyd.Scene | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.camera = pyd.FirstPersonCamera()
            self.view = pyd.PlanarView()
            self.depthBuffer: pyd.Texture | None = None
            self.framebuffers: list[pyd.Framebuffer | None] = []

        def Init(self: BindlessRendering) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            sceneFileName = FindSponzaGltf()
            if sceneFileName is None:
                pyd.log.fatal("Could not find Sponza.gltf under media/glTF-Sample-Assets/")
                return False

            shaderPath = folder / "shaders" / "bindless_rendering" / "bindless_rendering.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                includePaths = [str(donutIncludeDir)]
                vsBytecode = pyd.CompileShader(
                    source,
                    "vs_main",
                    pyd.ShaderType.Vertex,
                    api,
                    sourceName=shaderPath.name,
                    includePaths=includePaths,
                )
                psBytecode = pyd.CompileShader(
                    source,
                    "ps_main",
                    pyd.ShaderType.Pixel,
                    api,
                    sourceName=shaderPath.name,
                    includePaths=includePaths,
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.vertexShader = device.createShader(vsBytecode, "vs_main", pyd.ShaderType.Vertex)
            self.pixelShader = device.createShader(psBytecode, "ps_main", pyd.ShaderType.Pixel)

            if not self.vertexShader or not self.pixelShader:
                return False

            # CommonRenderPasses' own shaders (used by TextureCache for mip generation) are
            # only statically linked in when Donut is built with DONUT_WITH_STATIC_SHADERS,
            # which this project's CMake leaves off -- so read them as precompiled .bin
            # files via the filesystem instead, same as rt_triangle.py does.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            shaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))

            self.bindingCache = pyd.BindingCache(device)
            self.commonPasses = pyd.CommonRenderPasses(device, shaderFactory)

            bindlessLayoutDesc = pyd.BindlessLayoutDesc()
            bindlessLayoutDesc.visibility = pyd.ShaderType.All
            bindlessLayoutDesc.firstSlot = 0
            bindlessLayoutDesc.maxCapacity = 1024
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.RawBuffer_SRV(1))
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.Texture_SRV(2))
            self.bindlessLayout = device.createBindlessLayout(bindlessLayoutDesc)

            self.descriptorTableManager = pyd.DescriptorTableManager(device, self.bindlessLayout)

            nativeFS = pyd.NativeFileSystem()
            textureCache = pyd.TextureCache(device, nativeFS, self.descriptorTableManager)

            self.commandList = device.createCommandList()

            self.scene = pyd.Scene(device, shaderFactory, nativeFS, textureCache, self.descriptorTableManager)
            if not self.scene.Load(sceneFileName):
                return False

            # Mirrors the C++ sample's SetAsynchronousLoadingEnabled(false) +
            # BeginLoadingScene(): this must run BEFORE Scene.FinishedLoading() -- it
            # finalizes each texture's bindless descriptor index, which FinishedLoading()
            # then bakes into the material buffer. Getting this backwards leaves every
            # material's texture index unset (-1).
            pyd.SceneLoaded(textureCache, self.commonPasses)

            self.scene.FinishedLoading(self.GetFrameIndex())

            # The C++ sample's (0, 1.8, 0) -> (1, 1.8, 0) is tuned for a different Sponza
            # distribution; this glTF-Sample-Assets version applies a 0.008 root-node scale,
            # putting its world-space bounds at roughly x:[-15,14] y:[-1,11] z:[-9,9] (an
            # elongated hall along X). An eye-height start point inside those bounds risks
            # landing inside a wall/column, so start well above and outside the building
            # looking down and in -- guaranteed clear of geometry -- and fly the rest of the
            # way in with WASD + mouse look (wired up via KeyboardUpdate/MousePosUpdate below).
            self.camera.LookAt(0.0, 15.0, 40.0, 0.0, 3.0, 0.0)
            self.camera.SetMoveSpeed(6.0)

            viewConstantsSize = len(self.view.FillPlanarViewConstants())
            viewConstantsBufferDesc = pyd.CreateVolatileConstantBufferDesc(viewConstantsSize, "ViewConstants", 16)
            self.viewConstantsBuffer = device.createBuffer(viewConstantsBufferDesc)

            device.waitForIdle()

            bindingSetDesc = pyd.BindingSetDesc()
            bindingSetDesc.bindings = [
                pyd.BindingSetItem.ConstantBuffer(0, self.viewConstantsBuffer),
                pyd.BindingSetItem.PushConstants(1, struct.calcsize("<2I")),
                pyd.BindingSetItem.StructuredBuffer_SRV(0, self.scene.GetInstanceBuffer()),
                pyd.BindingSetItem.StructuredBuffer_SRV(1, self.scene.GetGeometryBuffer()),
                pyd.BindingSetItem.StructuredBuffer_SRV(2, self.scene.GetMaterialBuffer()),
                pyd.BindingSetItem.Sampler(0, self.commonPasses.m_AnisotropicWrapSampler),
            ]
            self.bindingLayout, self.bindingSet = pyd.CreateBindingSetAndLayout(
                device, pyd.ShaderType.All, 0, bindingSetDesc
            )

            return True

        def KeyboardUpdate(self: BindlessRendering, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            return True

        def MousePosUpdate(self: BindlessRendering, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: BindlessRendering, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def BackBufferResizing(self: BindlessRendering):
            self.depthBuffer = None
            self.framebuffers = []
            self.pipeline = None
            assert self.bindingCache is not None
            self.bindingCache.Clear()

        def Animate(self: BindlessRendering, elapsedTimeSeconds: float):
            self.camera.Animate(elapsedTimeSeconds)
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def Render(self: BindlessRendering, framebuffer: pyd.Framebuffer):
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.scene is not None
            assert self.descriptorTableManager is not None
            assert self.bindingLayout is not None
            assert self.bindlessLayout is not None
            assert self.bindingSet is not None
            assert self.viewConstantsBuffer is not None

            fbinfo = framebuffer.getFramebufferInfo()

            if not self.depthBuffer:
                textureDesc = pyd.TextureDesc()
                textureDesc.format = pyd.Format.D24S8
                textureDesc.isRenderTarget = True
                textureDesc.initialState = pyd.ResourceStates.DepthWrite
                textureDesc.keepInitialState = True
                textureDesc.clearValue = pyd.Color(0.0)
                textureDesc.useClearValue = True
                textureDesc.debugName = "DepthBuffer"
                textureDesc.width = fbinfo.width
                textureDesc.height = fbinfo.height

                self.depthBuffer = device.createTexture(textureDesc)

            backBufferCount = self.GetDeviceManager().GetBackBufferCount()
            if len(self.framebuffers) != backBufferCount:
                self.framebuffers = [None] * backBufferCount

            fbindex = self.GetDeviceManager().GetCurrentBackBufferIndex()
            if not self.framebuffers[fbindex]:
                framebufferDesc = pyd.FramebufferDesc()
                framebufferDesc.addColorAttachment(framebuffer.getDesc().getColorAttachment(0))
                framebufferDesc.setDepthAttachment(self.depthBuffer)
                self.framebuffers[fbindex] = device.createFramebuffer(framebufferDesc)

            renderFramebuffer = self.framebuffers[fbindex]
            assert renderFramebuffer is not None

            if not self.pipeline:
                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.vertexShader
                psoDesc.PS = self.pixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.addBindingLayout(self.bindingLayout)
                psoDesc.addBindingLayout(self.bindlessLayout)
                psoDesc.renderState.depthStencilState.depthTestEnable = True
                psoDesc.renderState.depthStencilState.depthFunc = pyd.ComparisonFunc.GreaterOrEqual
                psoDesc.renderState.rasterState.frontCounterClockwise = True

                self.pipeline = device.createGraphicsPipeline(
                    psoDesc, renderFramebuffer.getFramebufferInfo()
                )

            windowViewport = pyd.Viewport(float(fbinfo.width), float(fbinfo.height))
            self.view.SetViewport(windowViewport)
            self.view.SetMatricesFromCamera(
                self.camera, windowViewport.width() / windowViewport.height()
            )
            self.view.UpdateCache()

            self.commandList.open()

            colorBuffer = framebuffer.getDesc().getColorAttachment(0).texture
            assert colorBuffer is not None
            self.commandList.clearTextureFloat(colorBuffer, pyd.Color(0.0))
            self.commandList.clearDepthStencilTexture(self.depthBuffer, True, 0.0, True, 0)

            self.commandList.writeBuffer(self.viewConstantsBuffer, self.view.FillPlanarViewConstants())

            state = pyd.GraphicsState()
            state.pipeline = self.pipeline
            state.framebuffer = renderFramebuffer
            state.addBindingSet(self.bindingSet)
            state.addBindingSet(self.descriptorTableManager.GetDescriptorTable())
            state.viewport = self.view.GetViewportState()

            self.commandList.setGraphicsState(state)

            for instanceIndex, geometryIndex, numIndices in self.scene.GetDrawItems():
                self.commandList.setPushConstants(struct.pack("<2I", instanceIndex, geometryIndex))

                args = pyd.DrawArguments()
                args.instanceCount = 1
                args.vertexCount = numIndices
                self.commandList.draw(args)

            self.commandList.close()
            device.executeCommandList(self.commandList)

    is_debug = "-debug" in sys.argv

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures are actually visible here.
    pyd.log.ConsoleApplicationMode()

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")
    if api == pyd.GraphicsAPI.D3D11:
        pyd.log.fatal("The Bindless Rendering example does not support D3D11.")
        sys.exit(1)

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

    example = BindlessRendering(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
