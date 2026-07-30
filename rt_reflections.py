if __name__ == "__main__":
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Ray Traced Reflections"
    folder = Path(__file__).resolve().parent

    def FindSponzaGltf() -> Path | None:
        # Same asset location/lookup as variable_shading.py/bindless_rendering.py.
        candidate = folder / "media" / "glTF-Sample-Assets" / "Models" / "Sponza" / "glTF" / "Sponza.gltf"
        return candidate if candidate.is_file() else None

    # sizeof(LightingConstants) from shaders/rt_reflections/lighting_cb.h: same shape as
    # rt_shadows.py's -- float4 ambientColor (16 bytes) + LightConstants (112 bytes) +
    # PlanarViewConstants (720 bytes) = 848 bytes, all already 16-byte aligned.
    _LIGHTING_CONSTANTS_SIZE = 848

    # Binding slots from shaders/rt_reflections/lighting_cb.h.
    _SPACE_GLOBAL = 0
    _BINDING_MATERIAL_SAMPLER = 0
    _BINDING_LIGHTING_CONSTANTS = 0
    _BINDING_OUTPUT_UAV = 0
    _BINDING_SCENE_BVH = 0
    _BINDING_GBUFFER_DEPTH_TEXTURE = 1
    _BINDING_GBUFFER_0_TEXTURE = 2
    _BINDING_GBUFFER_1_TEXTURE = 3
    _BINDING_GBUFFER_2_TEXTURE = 4
    _BINDING_GBUFFER_3_TEXTURE = 5

    _SPACE_LOCAL = 1
    _BINDING_MATERIAL_CONSTANTS = 0
    _BINDING_INDEX_BUFFER = 0
    _BINDING_TEX_COORD_BUFFER = 1
    _BINDING_NORMAL_BUFFER = 2
    _BINDING_DIFFUSE_TEXTURE = 3
    _BINDING_SPECULAR_TEXTURE = 4
    _BINDING_NORMAL_TEXTURE = 5
    _BINDING_EMISSIVE_TEXTURE = 6
    _BINDING_OCCLUSION_TEXTURE = 7
    _BINDING_TRANSMISSION_TEXTURE = 8
    _BINDING_OPACITY_TEXTURE = 9

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

            # Kept for parity with the C++ original (m_HdrFramebuffer), which isn't actually
            # used in Render() -- only m_HdrFramebufferDepth (below) is.
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
            commandList.clearTextureFloat(self.gbufferEmissive, pyd.Color(0.0))

    class RayTracedReflections(pyd.ApplicationBase):
        def __init__(self: RayTracedReflections, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.textureCache: pyd.TextureCache | None = None
            self.scene: pyd.Scene | None = None
            self.sunLight: pyd.DirectionalLight | None = None
            self.opaqueDrawStrategy = pyd.InstancedOpaqueDrawStrategy()
            self.transparentDrawStrategy = pyd.TransparentDrawStrategy()
            self.camera = pyd.FirstPersonCamera()
            self.view = pyd.PlanarView()

            self.shaderLibrary: pyd.ShaderLibrary | None = None
            self.pipeline: pyd.RayTracingPipeline | None = None
            self.shaderTable: pyd.ShaderTable | None = None
            self.globalBindingLayout: pyd.BindingLayout | None = None
            self.localBindingLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.topLevelAS: pyd.AccelStruct | None = None
            self.constantBuffer: pyd.Buffer | None = None

            self.commandList: pyd.CommandList | None = None
            self.gbufferPass: pyd.GBufferFillPass | None = None
            self.forwardPass: pyd.ForwardShadingPass | None = None
            self.renderTargets: RenderTargets | None = None

        def Init(self: RayTracedReflections) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            sceneFileName = FindSponzaGltf()
            if sceneFileName is None:
                pyd.log.fatal("Could not find Sponza.gltf under media/glTF-Sample-Assets/")
                return False

            # CommonRenderPasses/GBufferFillPass/ForwardShadingPass's own shaders are only
            # statically linked in when Donut is built with DONUT_WITH_STATIC_SHADERS, which
            # this project's CMake leaves off -- so read them as precompiled .bin files via the
            # filesystem instead, same as the other examples. This example's own
            # rt_reflections.hlsl is compiled at runtime below and additionally needs donut's
            # shared donut/shaders/*.hlsli headers on the DXC include path, since it's compiled
            # from an in-memory source string rather than a real file on disk.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            appShaderPath = folder / "shaders" / "rt_reflections"
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.shaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.m_CommonPasses = self.commonPasses
            self.bindingCache = pyd.BindingCache(device)

            nativeFS = pyd.NativeFileSystem()
            self.textureCache = pyd.TextureCache(device, nativeFS, None)
            self.m_TextureCache = self.textureCache

            # Runs LoadScene() (below) synchronously, followed by the base ApplicationBase's
            # default SceneLoaded() (texture-cache finalization only -- this class doesn't
            # override SceneLoaded(), matching the C++ original, which calls
            # scene->FinishedLoading() itself below instead of from an override). Wiring the
            # cache/passes into the base above lets that inherited SceneLoaded() finalize
            # queued texture uploads itself, same as the C++ original.
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
            self._create_accel_structs(self.commandList)
            self.commandList.close()
            device.executeCommandList(self.commandList)
            device.waitForIdle()

            return True

        def _create_ray_tracing_pipeline(self: RayTracedReflections, api: pyd.GraphicsAPI, appShaderPath: Path) -> bool:
            device = self.GetDevice()
            assert self.commonPasses is not None
            assert self.scene is not None

            shaderPath = appShaderPath / "rt_reflections.hlsl"
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

            globalBindingLayoutDesc = pyd.BindingLayoutDesc()
            globalBindingLayoutDesc.visibility = pyd.ShaderType.All
            globalBindingLayoutDesc.registerSpace = _SPACE_GLOBAL
            globalBindingLayoutDesc.bindings = [
                pyd.BindingLayoutItem.VolatileConstantBuffer(_BINDING_LIGHTING_CONSTANTS),
                pyd.BindingLayoutItem.RayTracingAccelStruct(_BINDING_SCENE_BVH),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_GBUFFER_DEPTH_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_GBUFFER_0_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_GBUFFER_1_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_GBUFFER_2_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_GBUFFER_3_TEXTURE),
                pyd.BindingLayoutItem.Texture_UAV(_BINDING_OUTPUT_UAV),
                pyd.BindingLayoutItem.Sampler(_BINDING_MATERIAL_SAMPLER),
            ]
            self.globalBindingLayout = device.createBindingLayout(globalBindingLayoutDesc)

            localBindingLayoutDesc = pyd.BindingLayoutDesc()
            localBindingLayoutDesc.visibility = pyd.ShaderType.All
            localBindingLayoutDesc.registerSpace = _SPACE_LOCAL
            localBindingLayoutDesc.bindings = [
                pyd.BindingLayoutItem.TypedBuffer_SRV(_BINDING_INDEX_BUFFER),
                pyd.BindingLayoutItem.TypedBuffer_SRV(_BINDING_TEX_COORD_BUFFER),
                pyd.BindingLayoutItem.TypedBuffer_SRV(_BINDING_NORMAL_BUFFER),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_DIFFUSE_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_SPECULAR_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_NORMAL_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_EMISSIVE_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_OCCLUSION_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_TRANSMISSION_TEXTURE),
                pyd.BindingLayoutItem.Texture_SRV(_BINDING_OPACITY_TEXTURE),
                pyd.BindingLayoutItem.ConstantBuffer(_BINDING_MATERIAL_CONSTANTS),
            ]
            self.localBindingLayout = device.createBindingLayout(localBindingLayoutDesc)

            pipelineDesc = pyd.RayTracingPipelineDesc()
            pipelineDesc.addBindingLayout(self.globalBindingLayout)

            rayGenShaderExport = self.shaderLibrary.getShader("RayGen", pyd.ShaderType.RayGeneration)
            shadowMissShaderExport = self.shaderLibrary.getShader("ShadowMiss", pyd.ShaderType.Miss)
            reflectionMissShaderExport = self.shaderLibrary.getShader("ReflectionMiss", pyd.ShaderType.Miss)
            reflectionClosestHitExport = self.shaderLibrary.getShader("ReflectionClosestHit", pyd.ShaderType.ClosestHit)
            if not rayGenShaderExport or not shadowMissShaderExport or not reflectionMissShaderExport or not reflectionClosestHitExport:
                return False

            for exportShader in (rayGenShaderExport, shadowMissShaderExport, reflectionMissShaderExport):
                shaderDesc = pyd.PipelineShaderDesc()
                shaderDesc.setShader(exportShader)
                pipelineDesc.addShader(shaderDesc)

            # Empty hit group (no closest-hit/any-hit/intersection shader): a "hit" just keeps
            # the shadow payload's default (missed=false) untouched -- only ShadowMiss sets it.
            shadowHitGroup = pyd.PipelineHitGroupDesc()
            shadowHitGroup.setExportName("ShadowHitGroup")
            pipelineDesc.addHitGroup(shadowHitGroup)

            reflectionHitGroup = pyd.PipelineHitGroupDesc()
            reflectionHitGroup.setExportName("ReflectionHitGroup")
            reflectionHitGroup.setClosestHitShader(reflectionClosestHitExport)
            reflectionHitGroup.setBindingLayout(self.localBindingLayout)
            pipelineDesc.addHitGroup(reflectionHitGroup)

            pipelineDesc.maxPayloadSize = 4 * 4  # sizeof(float4)
            pipelineDesc.maxRecursionDepth = 2  # RayGen -> ReflectionClosestHit -> (shadow ray)

            self.pipeline = device.createRayTracingPipeline(pipelineDesc)

            self.shaderTable = self.pipeline.createShaderTable()
            self.shaderTable.setRayGenerationShader("RayGen")
            self.shaderTable.addMissShader("ShadowMiss")
            self.shaderTable.addMissShader("ReflectionMiss")

            # One (ShadowHitGroup, ReflectionHitGroup) pair per scene geometry, with the
            # reflection hit group carrying a local binding set for that geometry's own
            # buffers/material. TraceRay's MultiplierForGeometryContributionToHitGroupIndex is
            # 2 in the shader (see rt_reflections.hlsl), so each geometry's pair must land at
            # index globalGeometryIndex*2 -- asserted below to catch any drift between this
            # traversal order and the one _create_accel_structs uses for
            # instanceContributionToHitGroupIndex.
            sceneGraph = self.scene.GetSceneGraph()
            for mesh in sceneGraph.GetMeshes():
                assert mesh.buffers is not None
                assert mesh.buffers.indexBuffer is not None and mesh.buffers.vertexBuffer is not None
                for geometry in mesh.geometries:
                    material = geometry.material
                    assert material is not None
                    assert material.materialConstants is not None

                    def textureOrFallback(loaded: pyd.LoadedTexture | None, fallback: pyd.Texture) -> pyd.Texture:
                        return loaded.texture if (loaded is not None and loaded.texture is not None) else fallback

                    indexByteOffset = (mesh.indexOffset + geometry.indexOffsetInMesh) * 4
                    indexByteSize = geometry.numIndices * 4
                    texCoordRange = mesh.buffers.getVertexBufferRange(pyd.VertexAttribute.TexCoord1)
                    texCoordByteOffset = (mesh.vertexOffset + geometry.vertexOffsetInMesh) * 8 + texCoordRange.byteOffset
                    texCoordByteSize = geometry.numVertices * 8
                    normalRange = mesh.buffers.getVertexBufferRange(pyd.VertexAttribute.Normal)
                    normalByteOffset = (mesh.vertexOffset + geometry.vertexOffsetInMesh) * 4 + normalRange.byteOffset
                    normalByteSize = geometry.numVertices * 4

                    bindingSetDesc = pyd.BindingSetDesc()
                    bindingSetDesc.bindings = [
                        pyd.BindingSetItem.TypedBuffer_SRV(
                            _BINDING_INDEX_BUFFER, mesh.buffers.indexBuffer, pyd.Format.R32_UINT,
                            pyd.BufferRange(indexByteOffset, indexByteSize),
                        ),
                        pyd.BindingSetItem.TypedBuffer_SRV(
                            _BINDING_TEX_COORD_BUFFER, mesh.buffers.vertexBuffer, pyd.Format.RG32_FLOAT,
                            pyd.BufferRange(texCoordByteOffset, texCoordByteSize),
                        ),
                        pyd.BindingSetItem.TypedBuffer_SRV(
                            _BINDING_NORMAL_BUFFER, mesh.buffers.vertexBuffer, pyd.Format.RGBA8_SNORM,
                            pyd.BufferRange(normalByteOffset, normalByteSize),
                        ),
                        pyd.BindingSetItem.Texture_SRV(_BINDING_DIFFUSE_TEXTURE, textureOrFallback(material.baseOrDiffuseTexture, self.commonPasses.m_WhiteTexture)),
                        pyd.BindingSetItem.Texture_SRV(_BINDING_SPECULAR_TEXTURE, textureOrFallback(material.metalRoughOrSpecularTexture, self.commonPasses.m_WhiteTexture)),
                        pyd.BindingSetItem.Texture_SRV(_BINDING_NORMAL_TEXTURE, textureOrFallback(material.normalTexture, self.commonPasses.m_BlackTexture)),
                        pyd.BindingSetItem.Texture_SRV(_BINDING_EMISSIVE_TEXTURE, textureOrFallback(material.emissiveTexture, self.commonPasses.m_BlackTexture)),
                        pyd.BindingSetItem.Texture_SRV(_BINDING_OCCLUSION_TEXTURE, textureOrFallback(material.occlusionTexture, self.commonPasses.m_WhiteTexture)),
                        pyd.BindingSetItem.Texture_SRV(_BINDING_TRANSMISSION_TEXTURE, textureOrFallback(material.transmissionTexture, self.commonPasses.m_BlackTexture)),
                        pyd.BindingSetItem.Texture_SRV(_BINDING_OPACITY_TEXTURE, textureOrFallback(material.opacityTexture, self.commonPasses.m_WhiteTexture)),
                        pyd.BindingSetItem.ConstantBuffer(_BINDING_MATERIAL_CONSTANTS, material.materialConstants),
                    ]
                    localBindingSet = device.createBindingSet(bindingSetDesc, self.localBindingLayout)

                    hitGroupIndex = self.shaderTable.addHitGroup("ShadowHitGroup")
                    assert hitGroupIndex == geometry.globalGeometryIndex * 2

                    self.shaderTable.addHitGroup("ReflectionHitGroup", localBindingSet)

            return True

        def _create_accel_structs(self: RayTracedReflections, commandList: pyd.CommandList) -> None:
            assert self.scene is not None
            sceneGraph = self.scene.GetSceneGraph()

            for mesh in sceneGraph.GetMeshes():
                assert mesh.buffers is not None
                blasDesc = pyd.AccelStructDesc()
                blasDesc.isTopLevel = False

                geometryDescs = []
                for geometry in mesh.geometries:
                    triangles = pyd.GeometryTriangles()
                    triangles.indexBuffer = mesh.buffers.indexBuffer
                    triangles.indexOffset = (mesh.indexOffset + geometry.indexOffsetInMesh) * 4
                    triangles.indexFormat = pyd.Format.R32_UINT
                    triangles.indexCount = geometry.numIndices
                    triangles.vertexBuffer = mesh.buffers.vertexBuffer
                    positionRange = mesh.buffers.getVertexBufferRange(pyd.VertexAttribute.Position)
                    triangles.vertexOffset = (mesh.vertexOffset + geometry.vertexOffsetInMesh) * 12 + positionRange.byteOffset
                    triangles.vertexFormat = pyd.Format.RGB32_FLOAT
                    triangles.vertexStride = 12  # sizeof(float3)
                    triangles.vertexCount = geometry.numVertices

                    geometryDesc = pyd.GeometryDesc()
                    geometryDesc.setTriangles(triangles)
                    geometryDesc.flags = pyd.GeometryFlags.Opaque
                    geometryDescs.append(geometryDesc)

                blasDesc.bottomLevelGeometries = geometryDescs

                as_ = self.GetDevice().createAccelStruct(blasDesc)
                pyd.BuildBottomLevelAccelStruct(commandList, as_, blasDesc)

                mesh.accelStruct = as_

            tlasDesc = pyd.AccelStructDesc()
            tlasDesc.isTopLevel = True

            instances = []
            for instance in sceneGraph.GetMeshInstances():
                mesh = instance.GetMesh()

                instanceDesc = pyd.InstanceDesc()
                assert mesh.accelStruct is not None
                instanceDesc.setBLAS(mesh.accelStruct)
                instanceDesc.setInstanceMask(1)
                instanceDesc.setInstanceContributionToHitGroupIndex(mesh.geometries[0].globalGeometryIndex * 2)

                node = instance.GetNode()
                assert node is not None
                instanceDesc.setTransformFromNode(node)

                instances.append(instanceDesc)

            tlasDesc.topLevelMaxInstances = len(instances)
            self.topLevelAS = self.GetDevice().createAccelStruct(tlasDesc)
            commandList.buildTopLevelAccelStruct(self.topLevelAS, instances)

        def LoadScene(self: RayTracedReflections, fs: pyd.IFileSystem, sceneFileName: Path) -> bool:
            assert self.shaderFactory is not None
            assert self.textureCache is not None
            device = self.GetDevice()
            self.scene = pyd.Scene(device, self.shaderFactory, fs, self.textureCache, None)
            return self.scene.Load(sceneFileName)

        def KeyboardUpdate(self: RayTracedReflections, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            return True

        def MousePosUpdate(self: RayTracedReflections, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: RayTracedReflections, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def Animate(self: RayTracedReflections, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: RayTracedReflections) -> None:
            self.renderTargets = None
            assert self.bindingCache is not None
            self.bindingCache.Clear()
            self.gbufferPass = None
            self.forwardPass = None

        def Render(self: RayTracedReflections, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.shaderFactory is not None
            assert self.commonPasses is not None
            assert self.scene is not None
            assert self.sunLight is not None
            assert self.constantBuffer is not None
            assert self.shaderTable is not None
            assert self.globalBindingLayout is not None
            assert self.topLevelAS is not None

            fbinfo = framebuffer.getFramebufferInfo()
            size = (fbinfo.width, fbinfo.height)

            if self.renderTargets is None or self.renderTargets.size != size:
                self.renderTargets = RenderTargets(device, size)

                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.ConstantBuffer(_BINDING_LIGHTING_CONSTANTS, self.constantBuffer),
                    pyd.BindingSetItem.RayTracingAccelStruct(_BINDING_SCENE_BVH, self.topLevelAS),
                    pyd.BindingSetItem.Texture_SRV(_BINDING_GBUFFER_DEPTH_TEXTURE, self.renderTargets.depth),
                    pyd.BindingSetItem.Texture_SRV(_BINDING_GBUFFER_0_TEXTURE, self.renderTargets.gbufferDiffuse),
                    pyd.BindingSetItem.Texture_SRV(_BINDING_GBUFFER_1_TEXTURE, self.renderTargets.gbufferSpecular),
                    pyd.BindingSetItem.Texture_SRV(_BINDING_GBUFFER_2_TEXTURE, self.renderTargets.gbufferNormals),
                    pyd.BindingSetItem.Texture_SRV(_BINDING_GBUFFER_3_TEXTURE, self.renderTargets.gbufferEmissive),
                    pyd.BindingSetItem.Texture_UAV(_BINDING_OUTPUT_UAV, self.renderTargets.hdrColor),
                    pyd.BindingSetItem.Sampler(_BINDING_MATERIAL_SAMPLER, self.commonPasses.m_LinearWrapSampler),
                ]
                self.bindingSet = device.createBindingSet(bindingSetDesc, self.globalBindingLayout)

            if not self.gbufferPass:
                self.gbufferPass = pyd.GBufferFillPass(device, self.commonPasses)
                gbufferParams = pyd.GBufferFillPassCreateParameters()
                self.gbufferPass.Init(self.shaderFactory, gbufferParams)

            if not self.forwardPass:
                self.forwardPass = pyd.ForwardShadingPass(device, self.commonPasses)
                forwardParams = pyd.ForwardShadingPassCreateParameters()
                self.forwardPass.Init(self.shaderFactory, forwardParams)

            windowViewport = pyd.Viewport(float(fbinfo.width), float(fbinfo.height))
            self.view.SetViewport(windowViewport)
            self.view.SetMatricesFromCamera(self.camera, windowViewport.width() / windowViewport.height())
            self.view.UpdateCache()

            self.commandList.open()

            self.renderTargets.Clear(self.commandList)

            gbufferContext = pyd.GBufferFillPassContext()
            pyd.RenderCompositeView(
                self.commandList, self.view, self.view, self.renderTargets.gbufferFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(), self.opaqueDrawStrategy, self.gbufferPass, gbufferContext,
            )

            ambient = 0.2
            ambientColor = struct.pack("<4f", ambient, ambient, ambient, ambient)
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

            forwardContext = pyd.ForwardShadingPassContext()
            self.forwardPass.PrepareLights(
                forwardContext, self.commandList, self.scene.GetSceneGraph().GetLights(),
                ambient, ambient, ambient, ambient, ambient, ambient,
            )
            pyd.RenderCompositeView(
                self.commandList, self.view, self.view, self.renderTargets.hdrFramebufferDepth,
                self.scene.GetSceneGraph().GetRootNode(), self.transparentDrawStrategy, self.forwardPass, forwardContext,
            )

            self.commonPasses.BlitTexture(self.commandList, framebuffer, self.renderTargets.hdrColor, self.bindingCache)

            self.commandList.close()
            device.executeCommandList(self.commandList)

            self.GetDeviceManager().SetVsyncEnabled(True)

    is_debug = "-debug" in sys.argv

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures are actually visible here.
    pyd.log.ConsoleApplicationMode()

    # Ray tracing pipelines with recursive TraceRay calls need D3D12 or Vulkan; the C++
    # original hardcodes D3D12 (no -vk option), so this port does the same.
    api = pyd.GraphicsAPI.D3D12
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

    if not deviceManager.GetDevice().queryFeatureSupport(pyd.Feature.RayTracingPipeline):
        pyd.log.fatal("The graphics device does not support Ray Tracing Pipelines")
        sys.exit(1)

    example = RayTracedReflections(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
