if __name__ == "__main__":
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Bindless Ray Tracing"
    folder = Path(__file__).resolve().parent

    def FindSponzaGltf() -> Path | None:
        # The C++ original loads media/sponza-plus.scene.json, which isn't part of this
        # project's media/ -- same substitution as bindless_rendering.py/rt_shadows.py/
        # rt_reflections.py.
        candidate = folder / "media" / "sponza-plus.scene.json"
        return candidate if candidate.is_file() else None

    # sizeof(LightingConstants) from shaders/rt_bindless/lighting_cb.h: same shape as
    # rt_shadows.py's/rt_reflections.py's -- float4 ambientColor (16 bytes) + LightConstants
    # (112 bytes) + PlanarViewConstants (720 bytes) = 848 bytes, all already 16-byte aligned.
    _LIGHTING_CONSTANTS_SIZE = 848

    # Binding slots from shaders/rt_bindless/rt_bindless.hlsl.
    _BINDING_CONSTANTS = 0
    _BINDING_SCENE_BVH = 0
    _BINDING_INSTANCE_BUFFER = 1
    _BINDING_GEOMETRY_BUFFER = 2
    _BINDING_MATERIAL_BUFFER = 3
    _BINDING_MATERIAL_SAMPLER = 0
    _BINDING_OUTPUT_UAV = 0

    class BindlessRayTracing(pyd.ApplicationBase):
        def __init__(self: BindlessRayTracing, deviceManager: pyd.DeviceManager, useRayQuery: bool) -> None:
            super().__init__(deviceManager)
            self.useRayQuery = useRayQuery

            self.rootFS: pyd.RootFileSystem | None = None
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.descriptorTableManager: pyd.DescriptorTableManager | None = None
            self.textureCache: pyd.TextureCache | None = None
            self.scene: pyd.Scene | None = None
            self.sunLight: pyd.DirectionalLight | None = None
            self.camera = pyd.FirstPersonCamera()
            self.view = pyd.PlanarView()

            self.shaderLibrary: pyd.ShaderLibrary | None = None
            self.rayPipeline: pyd.RayTracingPipeline | None = None
            self.shaderTable: pyd.ShaderTable | None = None
            self.computeShader: pyd.Shader | None = None
            self.computePipeline: pyd.ComputePipeline | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindlessLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.topLevelAS: pyd.AccelStruct | None = None
            self.constantBuffer: pyd.Buffer | None = None
            self.colorBuffer: pyd.Texture | None = None

            self.commandList: pyd.CommandList | None = None

        def Init(self: BindlessRayTracing) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            sceneFileName = FindSponzaGltf()
            if sceneFileName is None:
                pyd.log.fatal("Could not find Sponza.gltf under media/glTF-Sample-Assets/")
                return False

            # CommonRenderPasses' own shaders are only statically linked in when Donut is built
            # with DONUT_WITH_STATIC_SHADERS, which this project's CMake leaves off -- so read
            # them as precompiled .bin files via the mounted filesystem instead, same as the
            # other examples. This example's own rt_bindless.hlsl is compiled at runtime below.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            appShaderPath = folder / "shaders" / "rt_bindless"

            self.rootFS = pyd.RootFileSystem()
            self.rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.rootFS.mount(Path("/shaders/app"), appShaderPath)

            self.shaderFactory = pyd.ShaderFactory(device, self.rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.m_CommonPasses = self.commonPasses
            self.bindingCache = pyd.BindingCache(device)

            bindlessLayoutDesc = pyd.BindlessLayoutDesc()
            bindlessLayoutDesc.visibility = pyd.ShaderType.All
            bindlessLayoutDesc.firstSlot = 0
            bindlessLayoutDesc.maxCapacity = 1024
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.RawBuffer_SRV(1))
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.Texture_SRV(2))
            self.bindlessLayout = device.createBindlessLayout(bindlessLayoutDesc)

            globalBindingLayoutDesc = pyd.BindingLayoutDesc()
            globalBindingLayoutDesc.visibility = pyd.ShaderType.All
            globalBindingLayoutDesc.bindings = [
                pyd.BindingLayoutItem.VolatileConstantBuffer(_BINDING_CONSTANTS),
                pyd.BindingLayoutItem.RayTracingAccelStruct(_BINDING_SCENE_BVH),
                pyd.BindingLayoutItem.StructuredBuffer_SRV(_BINDING_INSTANCE_BUFFER),
                pyd.BindingLayoutItem.StructuredBuffer_SRV(_BINDING_GEOMETRY_BUFFER),
                pyd.BindingLayoutItem.StructuredBuffer_SRV(_BINDING_MATERIAL_BUFFER),
                pyd.BindingLayoutItem.Sampler(_BINDING_MATERIAL_SAMPLER),
                pyd.BindingLayoutItem.Texture_UAV(_BINDING_OUTPUT_UAV),
            ]
            self.bindingLayout = device.createBindingLayout(globalBindingLayoutDesc)

            self.descriptorTableManager = pyd.DescriptorTableManager(device, self.bindlessLayout)

            nativeFS = pyd.NativeFileSystem()
            self.textureCache = pyd.TextureCache(device, nativeFS, self.descriptorTableManager)
            self.m_TextureCache = self.textureCache

            # Runs LoadScene() (below) synchronously, followed by the base ApplicationBase's
            # default SceneLoaded() (texture-cache finalization only -- this class doesn't
            # override SceneLoaded(), matching the C++ original, which calls
            # scene->FinishedLoading() itself below instead of from an override). Wiring the
            # cache/passes into the base above lets that inherited SceneLoaded() finalize
            # queued bindless texture uploads correctly.
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
            self.sunLight.irradiance = 5.0

            self.scene.FinishedLoading(self.GetFrameIndex())

            # Same asset-scale adjustment as bindless_rendering.py/rt_shadows.py/
            # rt_reflections.py: this glTF-Sample-Assets Sponza is not the one the C++
            # original's (0,1.8,0)->(1,1.8,0) camera was tuned for.
            self.camera.LookAt(0.0, 15.0, 40.0, 0.0, 3.0, 0.0)
            self.camera.SetMoveSpeed(6.0)

            self.constantBuffer = device.createBuffer(
                pyd.CreateVolatileConstantBufferDesc(_LIGHTING_CONSTANTS_SIZE, "LightingConstants", 16)
            )

            if self.useRayQuery:
                if not self.CreateComputePipeline(self.shaderFactory):
                    return False
            else:
                if not self.CreateRayTracingPipeline(self.shaderFactory):
                    return False

            self.commandList = device.createCommandList()
            self.commandList.open()

            self.CreateAccelStructs(self.commandList)

            self.commandList.close()
            device.executeCommandList(self.commandList)

            device.waitForIdle()

            return True

        def LoadScene(self: BindlessRayTracing, fs: pyd.IFileSystem, sceneFileName: Path) -> bool:
            assert self.shaderFactory is not None
            assert self.textureCache is not None
            assert self.descriptorTableManager is not None
            device = self.GetDevice()
            scene = pyd.Scene(device, self.shaderFactory, fs, self.textureCache, self.descriptorTableManager)
            if scene.Load(sceneFileName):
                self.scene = scene
                return True
            return False

        def KeyboardUpdate(self: BindlessRayTracing, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            return True

        def MousePosUpdate(self: BindlessRayTracing, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: BindlessRayTracing, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def Animate(self: BindlessRayTracing, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)
            extraInfo = "- using RayQuery" if self.useRayQuery else "- using RayPipeline"
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE, extraInfo=extraInfo)

        def CreateRayTracingPipeline(self: BindlessRayTracing, shaderFactory: pyd.ShaderFactory) -> bool:
            device = self.GetDevice()

            shaderPath = folder / "shaders" / "rt_bindless" / "rt_bindless.hlsl"
            source = "#define USE_RAY_QUERY 0\n" + shaderPath.read_text(encoding="utf-8")

            donutShaderIncludeRoot = folder / "extern" / "donut" / "include"

            try:
                assert pyd.CompileShaderLibrary is not None
                bytecode = pyd.CompileShaderLibrary(
                    source, device.getGraphicsAPI(), sourceName=shaderPath.name,
                    includePaths=[str(shaderPath.parent), str(donutShaderIncludeRoot)],
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.shaderLibrary = device.createShaderLibrary(bytecode)
            if not self.shaderLibrary:
                return False

            pipelineDesc = pyd.RayTracingPipelineDesc()
            assert self.bindingLayout is not None
            assert self.bindlessLayout is not None
            pipelineDesc.addBindingLayout(self.bindingLayout)
            pipelineDesc.addBindingLayout(self.bindlessLayout)

            rayGenShaderExport = self.shaderLibrary.getShader("RayGen", pyd.ShaderType.RayGeneration)
            missShaderExport = self.shaderLibrary.getShader("Miss", pyd.ShaderType.Miss)
            closestHitShaderExport = self.shaderLibrary.getShader("ClosestHit", pyd.ShaderType.ClosestHit)
            if not rayGenShaderExport or not missShaderExport or not closestHitShaderExport:
                return False

            for exportShader in (rayGenShaderExport, missShaderExport):
                shaderDesc = pyd.PipelineShaderDesc()
                shaderDesc.setShader(exportShader)
                pipelineDesc.addShader(shaderDesc)

            # The C++ original also attaches an AnyHit shader here to alpha-test
            # AlphaTested materials (IgnoreHit() on a transparent texel); pydonut's
            # PipelineHitGroupDesc doesn't expose setAnyHitShader, so this port's
            # RayPipeline path always commits the first triangle hit, same as the
            # empty hit group in rt_shadows.py. The RayQuery path below (-rayQuery)
            # does the alpha test in-shader via considerTransparentMaterial() and
            # isn't affected by this gap.
            hitGroup = pyd.PipelineHitGroupDesc()
            hitGroup.setExportName("HitGroup")
            hitGroup.setClosestHitShader(closestHitShaderExport)
            pipelineDesc.addHitGroup(hitGroup)

            pipelineDesc.maxPayloadSize = 4 * 6  # sizeof(RayPayload): float + 3*uint + float2

            self.rayPipeline = device.createRayTracingPipeline(pipelineDesc)
            if not self.rayPipeline:
                return False

            self.shaderTable = self.rayPipeline.createShaderTable()
            self.shaderTable.setRayGenerationShader("RayGen")
            self.shaderTable.addHitGroup("HitGroup")
            self.shaderTable.addMissShader("Miss")

            return True

        def CreateComputePipeline(self: BindlessRayTracing, shaderFactory: pyd.ShaderFactory) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "rt_bindless" / "rt_bindless.hlsl"
            source = "#define USE_RAY_QUERY 1\n" + shaderPath.read_text(encoding="utf-8")

            donutShaderIncludeRoot = folder / "extern" / "donut" / "include"

            try:
                assert pyd.CompileShader is not None
                bytecode = pyd.CompileShader(
                    source, "main", pyd.ShaderType.Compute, api, sourceName=shaderPath.name,
                    includePaths=[str(shaderPath.parent), str(donutShaderIncludeRoot)],
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.computeShader = device.createShader(bytecode, "main", pyd.ShaderType.Compute)
            if not self.computeShader:
                return False

            assert self.bindingLayout is not None
            assert self.bindlessLayout is not None
            pipelineDesc = pyd.ComputePipelineDesc()
            pipelineDesc.CS = self.computeShader
            pipelineDesc.addBindingLayout(self.bindingLayout)
            pipelineDesc.addBindingLayout(self.bindlessLayout)

            self.computePipeline = device.createComputePipeline(pipelineDesc)

            return self.computePipeline is not None

        def GetMeshBlasDesc(self: BindlessRayTracing, mesh: pyd.MeshInfo, blasDesc: pyd.AccelStructDesc) -> None:
            assert mesh.buffers is not None
            blasDesc.isTopLevel = False
            blasDesc.debugName = mesh.name

            geometryDescs = []
            positionRange = mesh.buffers.getVertexBufferRange(pyd.VertexAttribute.Position)
            for geometry in mesh.geometries:
                triangles = pyd.GeometryTriangles()
                triangles.indexBuffer = mesh.buffers.indexBuffer
                triangles.indexOffset = (mesh.indexOffset + geometry.indexOffsetInMesh) * 4  # sizeof(uint32_t)
                triangles.indexFormat = pyd.Format.R32_UINT
                triangles.indexCount = geometry.numIndices
                triangles.vertexBuffer = mesh.buffers.vertexBuffer
                triangles.vertexOffset = (mesh.vertexOffset + geometry.vertexOffsetInMesh) * 12 + positionRange.byteOffset  # sizeof(float3)
                triangles.vertexFormat = pyd.Format.RGB32_FLOAT
                triangles.vertexStride = 12  # sizeof(float3)
                triangles.vertexCount = geometry.numVertices

                geometryDesc = pyd.GeometryDesc()
                geometryDesc.setTriangles(triangles)
                # The C++ original checks geometry.material.domain == MaterialDomain.AlphaTested
                # here to leave alpha-tested geometry non-opaque for the AnyHit alpha test; that
                # domain value isn't exposed to Python (only Opaque/AlphaBlended are), and this
                # port can't wire an AnyHit shader anyway (see CreateRayTracingPipeline), so
                # every geometry is just flagged Opaque.
                geometryDesc.flags = pyd.GeometryFlags.Opaque
                geometryDescs.append(geometryDesc)

            blasDesc.bottomLevelGeometries = geometryDescs
            blasDesc.buildFlags = pyd.AccelStructBuildFlags.PreferFastTrace

        def CreateAccelStructs(self: BindlessRayTracing, commandList: pyd.CommandList) -> None:
            assert self.scene is not None
            sceneGraph = self.scene.GetSceneGraph()

            for mesh in sceneGraph.GetMeshes():
                blasDesc = pyd.AccelStructDesc()
                self.GetMeshBlasDesc(mesh, blasDesc)

                accelStruct = self.GetDevice().createAccelStruct(blasDesc)
                pyd.BuildBottomLevelAccelStruct(commandList, accelStruct, blasDesc)

                mesh.accelStruct = accelStruct

            tlasDesc = pyd.AccelStructDesc()
            tlasDesc.isTopLevel = True
            tlasDesc.topLevelMaxInstances = len(sceneGraph.GetMeshInstances())
            self.topLevelAS = self.GetDevice().createAccelStruct(tlasDesc)

        def BuildTLAS(self: BindlessRayTracing, commandList: pyd.CommandList, frameIndex: int) -> None:
            assert self.scene is not None
            instances: list[pyd.InstanceDesc] = []

            for instance in self.scene.GetSceneGraph().GetMeshInstances():
                mesh = instance.GetMesh()
                assert mesh.accelStruct is not None
                node = instance.GetNode()
                assert node is not None

                instanceDesc = pyd.InstanceDesc()
                instanceDesc.setBLAS(mesh.accelStruct)
                instanceDesc.setInstanceMask(1)
                instanceDesc.setInstanceID(instance.GetInstanceIndex())
                instanceDesc.setTransformFromNode(node)
                instances.append(instanceDesc)

            assert self.topLevelAS is not None
            commandList.buildTopLevelAccelStruct(self.topLevelAS, instances)

        def BackBufferResizing(self: BindlessRayTracing) -> None:
            self.colorBuffer = None
            assert self.bindingCache is not None
            self.bindingCache.Clear()

        def Render(self: BindlessRayTracing, framebuffer: pyd.Framebuffer) -> None:
            assert self.commandList is not None
            assert self.scene is not None
            assert self.commonPasses is not None
            assert self.sunLight is not None
            assert self.constantBuffer is not None
            assert self.bindingLayout is not None
            assert self.descriptorTableManager is not None

            fbinfo = framebuffer.getFramebufferInfo()

            if self.colorBuffer is None:
                desc = pyd.TextureDesc()
                desc.width = fbinfo.width
                desc.height = fbinfo.height
                desc.isUAV = True
                desc.keepInitialState = True
                desc.format = pyd.Format.RGBA16_FLOAT
                desc.initialState = pyd.ResourceStates.UnorderedAccess
                desc.debugName = "ColorBuffer"
                self.colorBuffer = self.GetDevice().createTexture(desc)

                assert self.topLevelAS is not None
                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.ConstantBuffer(_BINDING_CONSTANTS, self.constantBuffer),
                    pyd.BindingSetItem.RayTracingAccelStruct(_BINDING_SCENE_BVH, self.topLevelAS),
                    pyd.BindingSetItem.StructuredBuffer_SRV(_BINDING_INSTANCE_BUFFER, self.scene.GetInstanceBuffer()),
                    pyd.BindingSetItem.StructuredBuffer_SRV(_BINDING_GEOMETRY_BUFFER, self.scene.GetGeometryBuffer()),
                    pyd.BindingSetItem.StructuredBuffer_SRV(_BINDING_MATERIAL_BUFFER, self.scene.GetMaterialBuffer()),
                    pyd.BindingSetItem.Sampler(_BINDING_MATERIAL_SAMPLER, self.commonPasses.m_AnisotropicWrapSampler),
                    pyd.BindingSetItem.Texture_UAV(_BINDING_OUTPUT_UAV, self.colorBuffer),
                ]
                self.bindingSet = self.GetDevice().createBindingSet(bindingSetDesc, self.bindingLayout)

            windowViewport = pyd.Viewport(float(fbinfo.width), float(fbinfo.height))
            self.view.SetViewport(windowViewport)
            self.view.SetMatricesFromCamera(self.camera, windowViewport.width() / windowViewport.height())
            self.view.UpdateCache()

            self.commandList.open()

            self.scene.Refresh(self.commandList, self.GetFrameIndex())
            self.BuildTLAS(self.commandList, self.GetFrameIndex())

            ambientColor = struct.pack("<4f", 0.05, 0.05, 0.05, 0.05)
            constants = ambientColor + self.sunLight.FillLightConstants() + self.view.FillPlanarViewConstants()
            self.commandList.writeBuffer(self.constantBuffer, constants)

            assert self.bindingSet is not None

            if not self.useRayQuery:
                assert self.shaderTable is not None
                state = pyd.RayTracingState()
                state.shaderTable = self.shaderTable
                state.addBindingSet(self.bindingSet)
                state.addBindingSet(self.descriptorTableManager.GetDescriptorTable())
                self.commandList.setRayTracingState(state)

                args = pyd.DispatchRaysArguments()
                args.width = fbinfo.width
                args.height = fbinfo.height
                self.commandList.dispatchRays(args)
            else:
                state = pyd.ComputeState()
                state.pipeline = self.computePipeline
                state.addBindingSet(self.bindingSet)
                state.addBindingSet(self.descriptorTableManager.GetDescriptorTable())
                self.commandList.setComputeState(state)

                self.commandList.dispatch(
                    (fbinfo.width + 15) // 16,
                    (fbinfo.height + 15) // 16,
                )

            self.commonPasses.BlitTexture(self.commandList, framebuffer, self.colorBuffer, self.bindingCache)

            self.commandList.close()
            self.GetDevice().executeCommandList(self.commandList)

    is_debug = "-debug" in sys.argv
    useRayQuery = "-rayQuery" in sys.argv

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

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    if not useRayQuery and not deviceManager.GetDevice().queryFeatureSupport(pyd.Feature.RayTracingPipeline):
        pyd.log.fatal("The graphics device does not support Ray Tracing Pipelines")
        sys.exit(1)

    if useRayQuery and not deviceManager.GetDevice().queryFeatureSupport(pyd.Feature.RayQuery):
        pyd.log.fatal("The graphics device does not support Ray Queries")
        sys.exit(1)

    example = BindlessRayTracing(deviceManager, useRayQuery)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
