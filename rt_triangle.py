if __name__ == "__main__":
    import struct
    import sys
    from pathlib import Path
    from typing import Optional

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Ray Traced Triangle"
    folder = Path(__file__).resolve().parent

    class RayTracedTriangle(pyd.IRenderPass):
        def __init__(self: RayTracedTriangle, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.shaderLibrary: pyd.ShaderLibrary | None = None
            self.pipeline: pyd.RayTracingPipeline | None = None
            self.shaderTable: pyd.ShaderTable | None = None
            self.commandList: pyd.CommandList | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.bottomLevelAS: pyd.AccelStruct | None = None
            self.topLevelAS: pyd.AccelStruct | None = None
            self.renderTarget: pyd.Texture | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None

        def Init(self: RayTracedTriangle) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "rt_triangle" / "rt_triangle.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShaderLibrary is not None
                bytecode = pyd.CompileShaderLibrary(
                    source, api, sourceName=shaderPath.name
                )
            except RuntimeError as e:
                print(f"Shader compilation failed: {e}", file=sys.stderr)
                return False

            self.shaderLibrary = device.createShaderLibrary(bytecode)

            if not self.shaderLibrary:
                return False

            # CommonRenderPasses' own shaders (blit/fullscreen/etc.) are only statically
            # linked in when Donut is built with DONUT_WITH_STATIC_SHADERS, which this
            # project's CMake leaves off -- so it always reads them as precompiled .bin
            # files instead, via the filesystem. Those are produced by ShaderMake as part
            # of the normal `uv sync` build (see CMAKE_RUNTIME_OUTPUT_DIRECTORY / bin/shaders
            # in CMakeLists.txt), so mount that directory in.
            frameworkShaderPath = (
                folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            )
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            shaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))

            self.bindingCache = pyd.BindingCache(device)
            self.commonPasses = pyd.CommonRenderPasses(device, shaderFactory)

            bindingLayoutDesc = pyd.BindingLayoutDesc()
            bindingLayoutDesc.visibility = pyd.ShaderType.All
            bindingLayoutDesc.bindings = [
                pyd.BindingLayoutItem.RayTracingAccelStruct(0),
                pyd.BindingLayoutItem.Texture_UAV(0),
            ]

            self.bindingLayout = device.createBindingLayout(bindingLayoutDesc)

            pipelineDesc = pyd.RayTracingPipelineDesc()
            pipelineDesc.addBindingLayout(self.bindingLayout)

            rayGenShaderExport = self.shaderLibrary.getShader(
                "RayGen", pyd.ShaderType.RayGeneration
            )
            missShaderExport = self.shaderLibrary.getShader("Miss", pyd.ShaderType.Miss)
            closestHitShaderExport = self.shaderLibrary.getShader(
                "ClosestHit", pyd.ShaderType.ClosestHit
            )
            if (
                not rayGenShaderExport
                or not missShaderExport
                or not closestHitShaderExport
            ):
                return False

            rayGenShader = pyd.PipelineShaderDesc()
            rayGenShader.setShader(rayGenShaderExport)
            pipelineDesc.addShader(rayGenShader)

            missShader = pyd.PipelineShaderDesc()
            missShader.setShader(missShaderExport)
            pipelineDesc.addShader(missShader)

            hitGroup = pyd.PipelineHitGroupDesc()
            hitGroup.setExportName("HitGroup")
            hitGroup.setClosestHitShader(closestHitShaderExport)
            pipelineDesc.addHitGroup(hitGroup)

            pipelineDesc.maxPayloadSize = 4 * 4  # sizeof(float4)

            self.pipeline = device.createRayTracingPipeline(pipelineDesc)

            self.shaderTable = self.pipeline.createShaderTable()
            self.shaderTable.setRayGenerationShader("RayGen")
            self.shaderTable.addHitGroup("HitGroup")
            self.shaderTable.addMissShader("Miss")

            self.commandList = device.createCommandList()

            self.commandList.open()

            indices = struct.pack("<3I", 0, 1, 2)
            vertices = struct.pack("<9f", 0.0, -1.0, 1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0)

            indexBufferDesc = pyd.BufferDesc()
            indexBufferDesc.byteSize = len(indices)
            indexBufferDesc.initialState = pyd.ResourceStates.ShaderResource
            indexBufferDesc.keepInitialState = True
            indexBufferDesc.isAccelStructBuildInput = True
            indexBuffer = device.createBuffer(indexBufferDesc)

            vertexBufferDesc = pyd.BufferDesc()
            vertexBufferDesc.byteSize = len(vertices)
            vertexBufferDesc.initialState = pyd.ResourceStates.ShaderResource
            vertexBufferDesc.keepInitialState = True
            vertexBufferDesc.isAccelStructBuildInput = True
            vertexBuffer = device.createBuffer(vertexBufferDesc)

            self.commandList.writeBuffer(indexBuffer, indices)
            self.commandList.writeBuffer(vertexBuffer, vertices)

            triangles = pyd.GeometryTriangles()
            triangles.indexBuffer = indexBuffer
            triangles.vertexBuffer = vertexBuffer
            triangles.indexFormat = pyd.Format.R32_UINT
            triangles.indexCount = 3
            triangles.vertexFormat = pyd.Format.RGB32_FLOAT
            triangles.vertexStride = 4 * 3  # sizeof(float3)
            triangles.vertexCount = 3

            geometryDesc = pyd.GeometryDesc()
            geometryDesc.setTriangles(triangles)
            geometryDesc.flags = pyd.GeometryFlags.Opaque

            blasDesc = pyd.AccelStructDesc()
            blasDesc.isTopLevel = False
            blasDesc.bottomLevelGeometries = [geometryDesc]

            self.bottomLevelAS = device.createAccelStruct(blasDesc)
            pyd.BuildBottomLevelAccelStruct(
                self.commandList, self.bottomLevelAS, blasDesc
            )

            tlasDesc = pyd.AccelStructDesc()
            tlasDesc.isTopLevel = True
            tlasDesc.topLevelMaxInstances = 1

            self.topLevelAS = device.createAccelStruct(tlasDesc)

            instanceDesc = pyd.InstanceDesc()
            instanceDesc.setInstanceMask(1)
            instanceDesc.setFlags(pyd.InstanceFlags.TriangleFrontCounterclockwise)
            instanceDesc.setBLAS(self.bottomLevelAS)

            self.commandList.buildTopLevelAccelStruct(self.topLevelAS, [instanceDesc])

            self.commandList.close()
            device.executeCommandList(self.commandList)

            return True

        def Animate(self: RayTracedTriangle, elapsedTimeSeconds: float):
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: RayTracedTriangle):
            self.renderTarget = None
            assert self.bindingCache is not None
            self.bindingCache.Clear()

        def Render(self: RayTracedTriangle, framebuffer: pyd.Framebuffer):
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.topLevelAS is not None
            assert self.bindingLayout is not None
            assert self.shaderTable is not None
            assert self.commonPasses is not None
            assert self.bindingCache is not None

            if not self.renderTarget:
                colorAttachmentTexture = (
                    framebuffer.getDesc().getColorAttachment(0).texture
                )
                assert colorAttachmentTexture is not None
                textureDesc = colorAttachmentTexture.getDesc()
                textureDesc.isUAV = True
                textureDesc.isRenderTarget = False
                textureDesc.initialState = pyd.ResourceStates.UnorderedAccess
                textureDesc.keepInitialState = True
                textureDesc.format = pyd.Format.RGBA8_UNORM
                self.renderTarget = device.createTexture(textureDesc)

                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.RayTracingAccelStruct(0, self.topLevelAS),
                    pyd.BindingSetItem.Texture_UAV(0, self.renderTarget),
                ]

                self.bindingSet = device.createBindingSet(
                    bindingSetDesc, self.bindingLayout
                )

            assert self.bindingSet is not None
            fbinfo = framebuffer.getFramebufferInfo()

            self.commandList.open()

            state = pyd.RayTracingState()
            state.shaderTable = self.shaderTable
            state.addBindingSet(self.bindingSet)
            self.commandList.setRayTracingState(state)

            args = pyd.DispatchRaysArguments()
            args.width = fbinfo.width
            args.height = fbinfo.height
            self.commandList.dispatchRays(args)

            assert self.renderTarget is not None
            self.commonPasses.BlitTexture(
                self.commandList, framebuffer, self.renderTarget, self.bindingCache
            )

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

    if not deviceManager.GetDevice().queryFeatureSupport(
        pyd.Feature.RayTracingPipeline
    ):
        pyd.log.fatal("The graphics device does not support Ray Tracing Pipelines")
        sys.exit(1)

    example = RayTracedTriangle(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")
