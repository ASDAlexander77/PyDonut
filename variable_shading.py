if __name__ == "__main__":
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Variable Rate Shading"
    folder = Path(__file__).resolve().parent

    def FindSponzaGltf() -> Path | None:
        # The C++ sample resolves this via GetDirectoryWithExecutable().parent_path() /
        # "media/...", i.e. a media/ folder that ships alongside the built samples.
        candidate = folder / "media" / "glTF-Sample-Assets" / "Models" / "Sponza" / "glTF" / "Sponza.gltf"
        return candidate if candidate.is_file() else None

    # Mirrors the C++ sample's RenderTargets class: one depth buffer, the forward-pass HDR
    # color target plus its resolved/history-feedback/motion-vector siblings for TAA, and
    # (unused by ForwardShadingPass, but present in the original for parity) a G-buffer trio.
    # Two FramebufferFactory instances wrap m_HdrColor -- with and without a depth attachment --
    # matching the two draw passes below (forward opaque+transparent needs depth; nothing here
    # needs the depth-less one, but it's kept for fidelity with the C++ source).
    class RenderTargets:
        def __init__(self: RenderTargets, device: pyd.Device, size: tuple[int, int]) -> None:
            self.size = size
            width, height = size

            depthDesc = pyd.TextureDesc()
            depthDesc.width = width
            depthDesc.height = height
            depthDesc.isRenderTarget = True
            depthDesc.useClearValue = True
            depthDesc.clearValue = pyd.Color(0.0)
            depthDesc.keepInitialState = True
            depthDesc.isTypeless = True
            depthDesc.format = pyd.Format.D24S8
            depthDesc.initialState = pyd.ResourceStates.DepthWrite
            depthDesc.debugName = "DepthBuffer"
            self.depth = device.createTexture(depthDesc)

            def makeColorTexture(fmt: pyd.Format, name: str, isUAV: bool = True) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = width
                desc.height = height
                desc.isRenderTarget = True
                desc.useClearValue = True
                desc.clearValue = pyd.Color(0.0)
                desc.keepInitialState = True
                desc.format = fmt
                desc.initialState = pyd.ResourceStates.RenderTarget
                desc.isUAV = isUAV
                desc.debugName = name
                return device.createTexture(desc)

            self.hdrColor = makeColorTexture(pyd.Format.RGBA16_FLOAT, "HdrColor")
            self.resolvedColor = makeColorTexture(pyd.Format.RGBA16_FLOAT, "ResolvedColor")
            self.temporalFeedback1 = makeColorTexture(pyd.Format.RGBA16_SNORM, "TemporalFeedback1")
            self.temporalFeedback2 = makeColorTexture(pyd.Format.RGBA16_SNORM, "TemporalFeedback2")
            self.motionVectors = makeColorTexture(pyd.Format.RG16_FLOAT, "MotionVectors")
            self.gbufferDiffuse = makeColorTexture(pyd.Format.SRGBA8_UNORM, "GBufferDiffuse", isUAV=False)
            self.gbufferSpecular = makeColorTexture(pyd.Format.SRGBA8_UNORM, "GBufferSpecular", isUAV=False)
            self.gbufferNormals = makeColorTexture(pyd.Format.RGBA16_SNORM, "GBufferNormals", isUAV=False)

            self.hdrFramebuffer = pyd.FramebufferFactory(device)
            self.hdrFramebuffer.SetRenderTargets([self.hdrColor])

            self.hdrFramebufferDepth = pyd.FramebufferFactory(device)
            self.hdrFramebufferDepth.SetRenderTargets([self.hdrColor])
            self.hdrFramebufferDepth.depthTarget = self.depth

        def Clear(self: RenderTargets, commandList: pyd.CommandList) -> None:
            commandList.clearDepthStencilTexture(self.depth, True, 0.0, True, 0)
            commandList.clearTextureFloat(self.hdrColor, pyd.Color(0.0))
            commandList.clearTextureFloat(self.gbufferDiffuse, pyd.Color(0.0))
            commandList.clearTextureFloat(self.gbufferSpecular, pyd.Color(0.0))
            commandList.clearTextureFloat(self.gbufferNormals, pyd.Color(0.0))

    class VariableShading(pyd.ApplicationBase):
        def __init__(self: VariableShading, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.textureCache: pyd.TextureCache | None = None
            self.commandList: pyd.CommandList | None = None
            self.scene: pyd.Scene | None = None
            self.sunLight: pyd.DirectionalLight | None = None
            self.opaqueDrawStrategy = pyd.InstancedOpaqueDrawStrategy()
            self.transparentDrawStrategy = pyd.TransparentDrawStrategy()
            self.forwardPass: pyd.ForwardShadingPass | None = None
            self.temporalPass: pyd.TemporalAntiAliasingPass | None = None
            self.renderTargets: RenderTargets | None = None
            self.camera = pyd.FirstPersonCamera()
            self.view = pyd.PlanarView()
            self.viewPrevious = pyd.PlanarView()
            self.previousViewsValid = False

            self.shadingRateSurfaceShader: pyd.Shader | None = None
            self.pipeline: pyd.ComputePipeline | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.shadingRateSurface: pyd.Texture | None = None
            self.vrsTileSize = 16

        def Init(self: VariableShading) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            sceneFileName = FindSponzaGltf()
            if sceneFileName is None:
                pyd.log.fatal("Could not find Sponza.gltf under media/glTF-Sample-Assets/")
                return False

            # CommonRenderPasses/ForwardShadingPass/TemporalAntiAliasingPass's own shaders are
            # only statically linked in when Donut is built with DONUT_WITH_STATIC_SHADERS,
            # which this project's CMake leaves off -- so read them as precompiled .bin files
            # via the filesystem instead, same as the other examples. The VRS compute shader
            # below is this example's own, compiled at runtime instead (also matching the other
            # examples' pattern) -- no ShaderMake-built .bin for it exists here.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.shaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.bindingCache = pyd.BindingCache(device)

            shaderPath = folder / "shaders" / "variable_shading" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")
            try:
                assert pyd.CompileShader is not None
                csBytecode = pyd.CompileShader(source, "main_cs", pyd.ShaderType.Compute, api, sourceName=shaderPath.name)
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False
            self.shadingRateSurfaceShader = device.createShader(csBytecode, "main_cs", pyd.ShaderType.Compute)
            if not self.shadingRateSurfaceShader:
                return False

            nativeFS = pyd.NativeFileSystem()
            self.textureCache = pyd.TextureCache(device, nativeFS, None)

            # Runs LoadScene() (below) synchronously, followed by SceneLoaded() (below).
            self.SetAsynchronousLoadingEnabled(False)
            self.BeginLoadingScene(nativeFS, sceneFileName)
            if not self.IsSceneLoaded():
                return False

            # The C++ sample's (0, 1.8, 0) -> (1, 1.8, 0) is tuned for a different Sponza
            # distribution; this glTF-Sample-Assets version applies a 0.008 root-node scale,
            # putting its world-space bounds at roughly x:[-15,14] y:[-1,11] z:[-9,9] (an
            # elongated hall along X) -- same asset/scale adjustment as bindless_rendering.py.
            self.camera.LookAt(0.0, 15.0, 40.0, 0.0, 3.0, 0.0)
            self.camera.SetMoveSpeed(6.0)

            info = device.queryVariableRateShadingInfo()
            self.vrsTileSize = info.shadingRateImageTileSize

            self.commandList = device.createCommandList()

            device.waitForIdle()

            return True

        def LoadScene(self: VariableShading, fs: pyd.IFileSystem, sceneFileName: Path) -> bool:
            assert self.shaderFactory is not None
            assert self.textureCache is not None
            device = self.GetDevice()
            self.scene = pyd.Scene(device, self.shaderFactory, fs, self.textureCache, None)
            if not self.scene.Load(sceneFileName):
                return False

            sceneGraph = self.scene.GetSceneGraph()
            self.sunLight = pyd.DirectionalLight()
            sceneGraph.AttachLeafNode(sceneGraph.GetRootNode(), self.sunLight)
            self.sunLight.SetDirection(0.1, -1.0, 0.15)
            self.sunLight.SetName("Sun")
            self.sunLight.angularSize = 0.53
            self.sunLight.irradiance = 2.0

            return True

        def SceneLoaded(self: VariableShading) -> None:
            assert self.textureCache is not None
            assert self.commonPasses is not None
            assert self.scene is not None
            pyd.SceneLoaded(self.textureCache, self.commonPasses)
            self.scene.FinishedLoading(self.GetFrameIndex())

        def KeyboardUpdate(self: VariableShading, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            return True

        def MousePosUpdate(self: VariableShading, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: VariableShading, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def Animate(self: VariableShading, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: VariableShading) -> None:
            self.renderTargets = None
            assert self.bindingCache is not None
            self.bindingCache.Clear()
            self.forwardPass = None
            self.shadingRateSurface = None
            self.temporalPass = None
            self.pipeline = None

        def Render(self: VariableShading, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.shaderFactory is not None
            assert self.commonPasses is not None
            assert self.scene is not None
            assert self.shadingRateSurfaceShader is not None

            fbinfo = framebuffer.getFramebufferInfo()
            size = (fbinfo.width, fbinfo.height)

            if self.renderTargets is None or self.renderTargets.size != size:
                self.renderTargets = RenderTargets(device, size)

            windowViewport = pyd.Viewport(float(fbinfo.width), float(fbinfo.height))
            self.view.SetViewport(windowViewport)
            self.view.SetMatricesFromCamera(self.camera, windowViewport.width() / windowViewport.height())
            self.view.UpdateCache()

            # VRS-specific code starts here.
            # Use the queried tile size to determine the size of the VRS surface; it will be
            # approximately 1/tileSize in both dimensions (with some rounding).
            surfaceWidth = (fbinfo.width + self.vrsTileSize - 1) // self.vrsTileSize
            surfaceHeight = (fbinfo.height + self.vrsTileSize - 1) // self.vrsTileSize

            if not self.shadingRateSurface:
                desc = pyd.TextureDesc()
                desc.debugName = "ShadingRateTexture"
                desc.width = surfaceWidth
                desc.height = surfaceHeight
                desc.isRenderTarget = False
                desc.useClearValue = False
                desc.sampleCount = 1
                desc.dimension = pyd.TextureDimension.Texture2D
                desc.keepInitialState = True
                desc.arraySize = 1
                desc.isUAV = True
                desc.isShadingRateSurface = True
                desc.initialState = pyd.ResourceStates.UnorderedAccess
                # Important! VRS surface should be R8_UINT format.
                desc.format = pyd.Format.R8_UINT
                self.shadingRateSurface = device.createTexture(desc)

            if not self.forwardPass:
                self.forwardPass = pyd.ForwardShadingPass(device, self.commonPasses)
                self.renderTargets.hdrFramebufferDepth.shadingRateSurface = self.shadingRateSurface
                forwardParams = pyd.ForwardShadingPassCreateParameters()
                self.forwardPass.Init(self.shaderFactory, forwardParams)

            if not self.temporalPass:
                taaParams = pyd.TemporalAntiAliasingCreateParameters()
                taaParams.sourceDepth = self.renderTargets.depth
                taaParams.motionVectors = self.renderTargets.motionVectors
                taaParams.unresolvedColor = self.renderTargets.hdrColor
                taaParams.resolvedColor = self.renderTargets.resolvedColor
                taaParams.feedback1 = self.renderTargets.temporalFeedback1
                taaParams.feedback2 = self.renderTargets.temporalFeedback2
                taaParams.motionVectorStencilMask = 0x01
                taaParams.useCatmullRomFilter = True
                self.temporalPass = pyd.TemporalAntiAliasingPass(
                    device, self.shaderFactory, self.commonPasses, self.view, taaParams
                )

            # A pipeline state for the compute shader which will generate the VRS surface.
            if not self.pipeline:
                layoutDesc = pyd.BindingLayoutDesc()
                layoutDesc.visibility = pyd.ShaderType.Compute
                layoutDesc.bindings = [
                    pyd.BindingLayoutItem.Texture_UAV(0),
                    pyd.BindingLayoutItem.Texture_SRV(0),
                    pyd.BindingLayoutItem.Texture_SRV(1),
                ]
                self.bindingLayout = device.createBindingLayout(layoutDesc)

                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.Texture_UAV(0, self.shadingRateSurface, pyd.Format.R8_UINT),
                    pyd.BindingSetItem.Texture_SRV(0, self.renderTargets.motionVectors, pyd.Format.RG16_FLOAT),
                    pyd.BindingSetItem.Texture_SRV(1, self.renderTargets.hdrColor, pyd.Format.RGBA16_FLOAT),
                ]
                self.bindingSet = device.createBindingSet(bindingSetDesc, self.bindingLayout)

                psoDesc = pyd.ComputePipelineDesc()
                psoDesc.CS = self.shadingRateSurfaceShader
                psoDesc.addBindingLayout(self.bindingLayout)
                self.pipeline = device.createComputePipeline(psoDesc)

            self.commandList.open()

            if self.previousViewsValid:
                self.temporalPass.RenderMotionVectors(self.commandList, self.view, self.viewPrevious)

            computeState = pyd.ComputeState()
            computeState.pipeline = self.pipeline
            assert self.bindingSet is not None
            computeState.addBindingSet(self.bindingSet)
            self.commandList.setComputeState(computeState)

            # Dispatch call to generate the VRS surface.
            self.commandList.dispatch(surfaceWidth, surfaceHeight, 1)

            self.renderTargets.Clear(self.commandList)

            ambient = 0.2

            # Enable VRS, with a per-drawcall shading rate of 1x1, and make the shading-rate
            # image result always override all others. (The C++ sample also offers a raw-D3D12
            # ID3D12GraphicsCommandList5 path here behind a -raw flag; this port only uses the
            # cross-platform nvrhi path, which is what actually varies the shading rate.)
            vrsState = pyd.VariableRateShadingState()
            vrsState.enabled = True
            vrsState.shadingRate = pyd.VariableShadingRate.e1x1
            vrsState.imageCombiner = pyd.ShadingRateCombiner.Override
            self.view.SetVariableRateShadingState(vrsState)

            sceneGraph = self.scene.GetSceneGraph()

            # Forward pass to draw the scene with the VRS surface set above.
            forwardContext = pyd.ForwardShadingPassContext()
            self.forwardPass.PrepareLights(
                forwardContext, self.commandList, sceneGraph.GetLights(),
                ambient, ambient, ambient, ambient, ambient, ambient,
            )
            pyd.RenderCompositeView(
                self.commandList, self.view, self.view, self.renderTargets.hdrFramebufferDepth,
                sceneGraph.GetRootNode(), self.opaqueDrawStrategy, self.forwardPass, forwardContext,
            )
            pyd.RenderCompositeView(
                self.commandList, self.view, self.view, self.renderTargets.hdrFramebufferDepth,
                sceneGraph.GetRootNode(), self.transparentDrawStrategy, self.forwardPass, forwardContext,
            )

            self.view.SetVariableRateShadingState(pyd.VariableRateShadingState())
            # VRS-specific code ends here.

            # TAA pass (runs at full rate).
            taaResolveParams = pyd.TemporalAntiAliasingParameters()
            self.temporalPass.TemporalResolve(
                self.commandList, taaResolveParams, self.previousViewsValid, self.view, self.view
            )
            self.viewPrevious = pyd.PlanarView(self.view)
            self.previousViewsValid = True

            self.commonPasses.BlitTexture(self.commandList, framebuffer, self.renderTargets.resolvedColor, self.bindingCache)

            self.commandList.close()
            device.executeCommandList(self.commandList)

    is_debug = "-debug" in sys.argv

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures are actually visible here.
    pyd.log.ConsoleApplicationMode()

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")
    if api == pyd.GraphicsAPI.D3D11:
        pyd.log.fatal("The Variable Rate Shading example does not support D3D11.")
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

    if not deviceManager.GetDevice().queryFeatureSupport(pyd.Feature.VariableRateShading):
        pyd.log.fatal("The device does not support Variable Rate Shading")
        sys.exit(1)

    example = VariableShading(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
