if __name__ == "__main__":
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Ray Traced Shadows"
    folder = Path(__file__).resolve().parent

    def FindSponzaGltf() -> Path | None:
        # Same asset location/lookup as variable_shading.py/bindless_rendering.py.
        candidate = folder / "media" / "glTF-Sample-Assets" / "Models" / "Sponza" / "glTF" / "Sponza.gltf"
        return candidate if candidate.is_file() else None

    # sizeof(LightingConstants) from shaders/rt_shadows/lighting_cb.h: float4 ambientColor (16
    # bytes) + LightConstants (112 bytes) + PlanarViewConstants (720 bytes) = 848 bytes. Both
    # sub-struct sizes are already 16-byte aligned, so straight byte concatenation in that same
    # field order matches the real (padding-free) C++/HLSL layout.
    _LIGHTING_CONSTANTS_SIZE = 848

    class RenderTargets:
        def __init__(self: RenderTargets, device: pyd.Device, size: tuple[int, int]) -> None:
            self.size = size
            width, height = size

            def makeTexture(fmt: pyd.Format, name: str, isTypeless: bool, initialState: pyd.ResourceStates, isUAV: bool = False) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = width
                desc.height = height
                desc.isRenderTarget = True
                desc.useClearValue = True
                desc.clearValue = pyd.Color(0.0)
                desc.keepInitialState = True
                desc.isTypeless = isTypeless
                desc.format = fmt
                desc.initialState = initialState
                desc.isUAV = isUAV
                desc.debugName = name
                return device.createTexture(desc)

            self.depth = makeTexture(pyd.Format.D24S8, "DepthBuffer", True, pyd.ResourceStates.DepthWrite)
            self.hdrColor = makeTexture(pyd.Format.RGBA16_FLOAT, "HdrColor", False, pyd.ResourceStates.RenderTarget, isUAV=True)
            self.gbufferDiffuse = makeTexture(pyd.Format.SRGBA8_UNORM, "GBufferDiffuse", False, pyd.ResourceStates.RenderTarget)
            self.gbufferSpecular = makeTexture(pyd.Format.SRGBA8_UNORM, "GBufferSpecular", False, pyd.ResourceStates.RenderTarget)
            self.gbufferNormals = makeTexture(pyd.Format.RGBA16_SNORM, "GBufferNormals", False, pyd.ResourceStates.RenderTarget)
            self.gbufferEmissive = makeTexture(pyd.Format.RGBA16_FLOAT, "GBufferEmissive", False, pyd.ResourceStates.RenderTarget)

            self.gbufferFramebuffer = pyd.FramebufferFactory(device)
            self.gbufferFramebuffer.SetRenderTargets(
                [self.gbufferDiffuse, self.gbufferSpecular, self.gbufferNormals, self.gbufferEmissive]
            )
            self.gbufferFramebuffer.depthTarget = self.depth

            self.hdrFramebuffer = pyd.FramebufferFactory(device)
            self.hdrFramebuffer.SetRenderTargets([self.hdrColor])

        def Clear(self: RenderTargets, commandList: pyd.CommandList) -> None:
            commandList.clearDepthStencilTexture(self.depth, True, 0.0, True, 0)
            commandList.clearTextureFloat(self.hdrColor, pyd.Color(0.0))
            commandList.clearTextureFloat(self.gbufferDiffuse, pyd.Color(0.0))
            commandList.clearTextureFloat(self.gbufferSpecular, pyd.Color(0.0))
            commandList.clearTextureFloat(self.gbufferNormals, pyd.Color(0.0))
            commandList.clearTextureFloat(self.gbufferEmissive, pyd.Color(0.0))

    class RayTracedShadows(pyd.ApplicationBase):
        def __init__(self: RayTracedShadows, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.textureCache: pyd.TextureCache | None = None
            self.scene: pyd.Scene | None = None
            self.sunLight: pyd.DirectionalLight | None = None
            self.opaqueDrawStrategy = pyd.InstancedOpaqueDrawStrategy()
            self.camera = pyd.FirstPersonCamera()
            self.view = pyd.PlanarView()

            self.shaderLibrary: pyd.ShaderLibrary | None = None
            self.pipeline: pyd.RayTracingPipeline | None = None
            self.shaderTable: pyd.ShaderTable | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.topLevelAS: pyd.AccelStruct | None = None
            self.constantBuffer: pyd.Buffer | None = None

            self.commandList: pyd.CommandList | None = None
            self.gbufferPass: pyd.GBufferFillPass | None = None
            self.renderTargets: RenderTargets | None = None

        def Init(self: RayTracedShadows) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            sceneFileName = FindSponzaGltf()
            if sceneFileName is None:
                pyd.log.fatal("Could not find Sponza.gltf under media/glTF-Sample-Assets/")
                return False

            # CommonRenderPasses/GBufferFillPass's own shaders are only statically linked in
            # when Donut is built with DONUT_WITH_STATIC_SHADERS, which this project's CMake
            # leaves off -- so read them as precompiled .bin files via the filesystem instead,
            # same as the other examples. This example's own rt_shadows.hlsl is compiled at
            # runtime below and additionally needs donut's shared donut/shaders/*.hlsli headers
            # (gbuffer.hlsli, lighting.hlsli) on the DXC include path, since it's compiled from
            # an in-memory source string rather than a real file on disk.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            appShaderPath = folder / "shaders" / "rt_shadows"
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.shaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.bindingCache = pyd.BindingCache(device)

            nativeFS = pyd.NativeFileSystem()
            self.textureCache = pyd.TextureCache(device, nativeFS, None)

            # Runs LoadScene() (below) synchronously, followed by the base ApplicationBase's
            # default SceneLoaded() (texture-cache finalization only -- this class doesn't
            # override SceneLoaded(), matching the C++ original, which calls
            # scene->FinishedLoading() itself below instead of from an override).
            self.SetAsynchronousLoadingEnabled(False)
            self.BeginLoadingScene(nativeFS, sceneFileName)
            if not self.IsSceneLoaded():
                return False
            assert self.scene is not None

            sceneGraph = self.scene.GetSceneGraph()
            self.sunLight = pyd.DirectionalLight()
            sceneGraph.AttachLeafNode(sceneGraph.GetRootNode(), self.sunLight)
            self.sunLight.SetDirection(0.1, -1.0, 0.15)
            self.sunLight.angularSize = 0.53
            self.sunLight.irradiance = 1.0

            self.scene.FinishedLoading(self.GetFrameIndex())

            # Same asset-scale adjustment as variable_shading.py/bindless_rendering.py: this
            # glTF-Sample-Assets Sponza is not the one the C++ sample's (0,1.8,0)->(1,1.8,0)
            # camera was tuned for.
            self.camera.LookAt(0.0, 15.0, 40.0, 0.0, 3.0, 0.0)
            self.camera.SetMoveSpeed(6.0)

            self.constantBuffer = device.createBuffer(
                pyd.CreateVolatileConstantBufferDesc(_LIGHTING_CONSTANTS_SIZE, "LightingConstants", 16)
            )

            if not self._create_ray_tracing_pipeline(api, appShaderPath):
                return False

            self.commandList = device.createCommandList()
            self.commandList.open()
            self.topLevelAS = pyd.BuildSceneAccelStructs(device, self.commandList, self.scene)
            self.commandList.close()
            device.executeCommandList(self.commandList)
            device.waitForIdle()

            return True

        def _create_ray_tracing_pipeline(self: RayTracedShadows, api: pyd.GraphicsAPI, appShaderPath: Path) -> bool:
            device = self.GetDevice()

            shaderPath = appShaderPath / "rt_shadows.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            donutShaderIncludeRoot = folder / "extern" / "donut" / "include"

            try:
                assert pyd.CompileShaderLibrary is not None
                bytecode = pyd.CompileShaderLibrary(
                    source, api, sourceName=shaderPath.name,
                    includePaths=[str(appShaderPath), str(donutShaderIncludeRoot)],
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.shaderLibrary = device.createShaderLibrary(bytecode)
            if not self.shaderLibrary:
                return False

            bindingLayoutDesc = pyd.BindingLayoutDesc()
            bindingLayoutDesc.visibility = pyd.ShaderType.All
            bindingLayoutDesc.bindings = [
                pyd.BindingLayoutItem.VolatileConstantBuffer(0),
                pyd.BindingLayoutItem.RayTracingAccelStruct(0),
                pyd.BindingLayoutItem.Texture_SRV(1),
                pyd.BindingLayoutItem.Texture_SRV(2),
                pyd.BindingLayoutItem.Texture_SRV(3),
                pyd.BindingLayoutItem.Texture_SRV(4),
                pyd.BindingLayoutItem.Texture_SRV(5),
                pyd.BindingLayoutItem.Texture_UAV(0),
            ]
            self.bindingLayout = device.createBindingLayout(bindingLayoutDesc)

            pipelineDesc = pyd.RayTracingPipelineDesc()
            pipelineDesc.addBindingLayout(self.bindingLayout)

            rayGenShaderExport = self.shaderLibrary.getShader("RayGen", pyd.ShaderType.RayGeneration)
            missShaderExport = self.shaderLibrary.getShader("Miss", pyd.ShaderType.Miss)
            if not rayGenShaderExport or not missShaderExport:
                return False

            rayGenShader = pyd.PipelineShaderDesc()
            rayGenShader.setShader(rayGenShaderExport)
            pipelineDesc.addShader(rayGenShader)

            missShader = pyd.PipelineShaderDesc()
            missShader.setShader(missShaderExport)
            pipelineDesc.addShader(missShader)

            # Empty hit group (no closest-hit/any-hit/intersection shader): a "hit" just keeps
            # the payload's default (missed=false) untouched -- only the miss shader sets it.
            hitGroup = pyd.PipelineHitGroupDesc()
            hitGroup.setExportName("HitGroup")
            pipelineDesc.addHitGroup(hitGroup)

            pipelineDesc.maxPayloadSize = 4 * 4  # sizeof(float4), same conservative size as rt_triangle.py

            self.pipeline = device.createRayTracingPipeline(pipelineDesc)

            self.shaderTable = self.pipeline.createShaderTable()
            self.shaderTable.setRayGenerationShader("RayGen")
            self.shaderTable.addHitGroup("HitGroup")
            self.shaderTable.addMissShader("Miss")

            return True

        def LoadScene(self: RayTracedShadows, fs: pyd.IFileSystem, sceneFileName: Path) -> bool:
            assert self.shaderFactory is not None
            assert self.textureCache is not None
            device = self.GetDevice()
            self.scene = pyd.Scene(device, self.shaderFactory, fs, self.textureCache, None)
            return self.scene.Load(sceneFileName)

        def KeyboardUpdate(self: RayTracedShadows, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            return True

        def MousePosUpdate(self: RayTracedShadows, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: RayTracedShadows, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def Animate(self: RayTracedShadows, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: RayTracedShadows) -> None:
            self.renderTargets = None
            assert self.bindingCache is not None
            self.bindingCache.Clear()
            self.gbufferPass = None

        def Render(self: RayTracedShadows, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.shaderFactory is not None
            assert self.commonPasses is not None
            assert self.scene is not None
            assert self.sunLight is not None
            assert self.constantBuffer is not None
            assert self.shaderTable is not None
            assert self.bindingLayout is not None
            assert self.topLevelAS is not None

            fbinfo = framebuffer.getFramebufferInfo()
            size = (fbinfo.width, fbinfo.height)

            if self.renderTargets is None or self.renderTargets.size != size:
                self.renderTargets = RenderTargets(device, size)

                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.ConstantBuffer(0, self.constantBuffer),
                    pyd.BindingSetItem.RayTracingAccelStruct(0, self.topLevelAS),
                    pyd.BindingSetItem.Texture_SRV(1, self.renderTargets.depth),
                    pyd.BindingSetItem.Texture_SRV(2, self.renderTargets.gbufferDiffuse),
                    pyd.BindingSetItem.Texture_SRV(3, self.renderTargets.gbufferSpecular),
                    pyd.BindingSetItem.Texture_SRV(4, self.renderTargets.gbufferNormals),
                    pyd.BindingSetItem.Texture_SRV(5, self.renderTargets.gbufferEmissive),
                    pyd.BindingSetItem.Texture_UAV(0, self.renderTargets.hdrColor),
                ]
                self.bindingSet = device.createBindingSet(bindingSetDesc, self.bindingLayout)

            windowViewport = pyd.Viewport(float(fbinfo.width), float(fbinfo.height))
            self.view.SetViewport(windowViewport)
            self.view.SetMatricesFromCamera(self.camera, windowViewport.width() / windowViewport.height())
            self.view.UpdateCache()

            if not self.gbufferPass:
                self.gbufferPass = pyd.GBufferFillPass(device, self.commonPasses)
                gbufferParams = pyd.GBufferFillPassCreateParameters()
                self.gbufferPass.Init(self.shaderFactory, gbufferParams)

            self.commandList.open()

            self.renderTargets.Clear(self.commandList)

            gbufferContext = pyd.GBufferFillPassContext()
            pyd.RenderCompositeView(
                self.commandList, self.view, self.view, self.renderTargets.gbufferFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(), self.opaqueDrawStrategy, self.gbufferPass, gbufferContext,
            )

            ambientColor = struct.pack("<4f", 0.05, 0.05, 0.05, 0.05)
            constants = ambientColor + self.sunLight.FillLightConstants() + self.view.FillPlanarViewConstants()
            self.commandList.writeBuffer(self.constantBuffer, constants)

            state = pyd.RayTracingState()
            state.shaderTable = self.shaderTable
            assert self.bindingSet is not None
            state.addBindingSet(self.bindingSet)
            self.commandList.setRayTracingState(state)

            args = pyd.DispatchRaysArguments()
            args.width = fbinfo.width
            args.height = fbinfo.height
            self.commandList.dispatchRays(args)

            self.commonPasses.BlitTexture(self.commandList, framebuffer, self.renderTargets.hdrColor, self.bindingCache)

            self.commandList.close()
            device.executeCommandList(self.commandList)

    is_debug = "-debug" in sys.argv

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures are actually visible here.
    pyd.log.ConsoleApplicationMode()

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    deviceParams.enableRayTracingExtensions = True
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        pyd.log.fatal(
            "Cannot initialize a graphics device with the requested parameters"
        )
        sys.exit(1)

    if not deviceManager.GetDevice().queryFeatureSupport(pyd.Feature.RayTracingPipeline):
        pyd.log.fatal("The graphics device does not support Ray Tracing Pipelines")
        sys.exit(1)

    example = RayTracedShadows(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
