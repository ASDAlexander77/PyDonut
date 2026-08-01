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

if __name__ == "__main__":
    import math
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Deferred Shading"
    folder = Path(__file__).resolve().parent

    # Mirrors donut::math::vectorToSnorm8<4>(float4) exactly (see
    # extern/donut/src/core/math/vector.cpp): scales by 127/|xyz| (the length excludes w,
    # which carries a sign bit for tangents rather than being part of the normalized vector),
    # truncates toward zero, then packs 4 signed bytes into one uint32.
    def _pack_snorm8x4(x: float, y: float, z: float, w: float) -> int:
        scale = 127.0 / math.sqrt(x * x + y * y + z * z)
        ix, iy, iz, iw = int(x * scale), int(y * scale), int(z * scale), int(w * scale)
        return (ix & 0xFF) | ((iy & 0xFF) << 8) | ((iz & 0xFF) << 16) | ((iw & 0xFF) << 24)

    # Transcribed from Donut-Samples/examples/deferred_shading/CubeGeometry.h.
    _POSITIONS = [
        (-0.5, 0.5, -0.5), (0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (0.5, 0.5, -0.5),  # front
        (0.5, -0.5, -0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, -0.5),      # right
        (-0.5, 0.5, 0.5), (-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, -0.5),  # left
        (0.5, 0.5, 0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (-0.5, 0.5, 0.5),      # back
        (-0.5, 0.5, -0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, 0.5),      # top
        (0.5, -0.5, 0.5), (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (-0.5, -0.5, 0.5),  # bottom
    ]
    _TEXCOORDS = [
        (0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0),  # front
        (0.0, 1.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0),  # right
        (0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0),  # left
        (0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0),  # back
        (0.0, 1.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0),  # top
        (1.0, 1.0), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0),  # bottom
    ]
    # One direction per face; each is repeated 4x (once per face vertex) when packed below.
    _FACE_NORMALS = [
        (0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
    ]
    _FACE_TANGENTS = [
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
        (-1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 0.0),
    ]
    _INDICES = [
        0, 1, 2, 0, 3, 1,
        4, 5, 6, 4, 7, 5,
        8, 9, 10, 8, 11, 9,
        12, 13, 14, 12, 15, 13,
        16, 17, 18, 16, 19, 17,
        20, 21, 22, 20, 23, 21,
    ]

    def _build_cube_bytes() -> tuple[bytes, bytes, bytes, bytes, bytes]:
        positions = struct.pack(f"<{len(_POSITIONS) * 3}f", *(c for p in _POSITIONS for c in p))
        texcoords = struct.pack(f"<{len(_TEXCOORDS) * 2}f", *(c for t in _TEXCOORDS for c in t))
        normals = struct.pack(f"<{len(_FACE_NORMALS) * 4}I", *(
            _pack_snorm8x4(*n, 0.0) for n in _FACE_NORMALS for _ in range(4)
        ))
        tangents = struct.pack(f"<{len(_FACE_TANGENTS) * 4}I", *(
            _pack_snorm8x4(*t, 1.0) for t in _FACE_TANGENTS for _ in range(4)
        ))
        indices = struct.pack(f"<{len(_INDICES)}I", *_INDICES)
        return positions, texcoords, normals, tangents, indices

    class DeferredShading(pyd.IRenderPass):
        def __init__(self: DeferredShading, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.deferredLightingPass: pyd.DeferredLightingPass | None = None
            self.textureCache: pyd.TextureCache | None = None
            self.commandList: pyd.CommandList | None = None
            self.bufferGroup: pyd.BufferGroup | None = None
            self.material: pyd.Material | None = None
            self.meshInfo: pyd.MeshInfo | None = None
            self.meshGeometry: pyd.MeshGeometry | None = None
            self.meshInstance: pyd.MeshInstance | None = None
            self.sceneGraph: pyd.SceneGraph | None = None
            self.renderTargets: pyd.GBufferRenderTargets | None = None
            self.shadedColor: pyd.Texture | None = None
            self.gbufferPass: pyd.GBufferFillPass | None = None
            self.view = pyd.PlanarView()
            self.rotation = 0.0

        def Init(self: DeferredShading) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            # CommonRenderPasses' own shaders (used by TextureCache for mip generation) and
            # GBufferFillPass/DeferredLightingPass's shaders are only statically linked in
            # when Donut is built with DONUT_WITH_STATIC_SHADERS, which this project's CMake
            # leaves off -- so read them as precompiled .bin files via the filesystem instead,
            # same as rt_triangle.py/bindless_rendering.py. No example-specific HLSL is needed
            # here: both passes only consume Donut's precompiled framework shaders.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.shaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.bindingCache = pyd.BindingCache(device)

            self.deferredLightingPass = pyd.DeferredLightingPass(device, self.commonPasses)
            self.deferredLightingPass.Init(self.shaderFactory)

            nativeFS = pyd.NativeFileSystem()
            self.textureCache = pyd.TextureCache(device, nativeFS, None)

            self.commandList = device.createCommandList()

            return self._build_scene()

        def _build_scene(self: DeferredShading) -> bool:
            device = self.GetDevice()
            commandList = self.commandList
            assert commandList is not None
            assert self.textureCache is not None

            commandList.open()

            positions, texcoords, normals, tangents, indices = _build_cube_bytes()

            indexBufferDesc = pyd.BufferDesc()
            indexBufferDesc.byteSize = len(indices)
            indexBufferDesc.isIndexBuffer = True
            indexBufferDesc.initialState = pyd.ResourceStates.IndexBuffer
            indexBufferDesc.keepInitialState = True
            indexBuffer = device.createBuffer(indexBufferDesc)
            commandList.writeBuffer(indexBuffer, indices)

            vertexBytes = positions + texcoords + normals + tangents
            vertexBufferDesc = pyd.BufferDesc()
            vertexBufferDesc.byteSize = len(vertexBytes)
            vertexBufferDesc.canHaveRawViews = True
            vertexBufferDesc.initialState = pyd.ResourceStates.ShaderResource
            vertexBufferDesc.keepInitialState = True
            vertexBuffer = device.createBuffer(vertexBufferDesc)
            commandList.writeBuffer(vertexBuffer, vertexBytes)

            buffers = pyd.BufferGroup()
            buffers.indexBuffer = indexBuffer
            buffers.vertexBuffer = vertexBuffer
            offset = 0
            for attr, chunk in (
                (pyd.VertexAttribute.Position, positions),
                (pyd.VertexAttribute.TexCoord1, texcoords),
                (pyd.VertexAttribute.Normal, normals),
                (pyd.VertexAttribute.Tangent, tangents),
            ):
                buffers.setVertexBufferRange(attr, offset, len(chunk))
                offset += len(chunk)

            # InstanceData (donut/shaders/bindless.h): 4x uint32 (flags/geometry indices,
            # unused for this single-instance, single-geometry cube) followed by two row-major
            # 3x4 transforms. A static, unrotated cube -> both are the identity.
            identity3x4 = (
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
            )
            instanceBytes = struct.pack("<4I12f12f", 0, 0, 0, 0, *identity3x4, *identity3x4)
            needStructuredBuffer = device.getGraphicsAPI() != pyd.GraphicsAPI.D3D11
            instanceBufferDesc = pyd.BufferDesc()
            instanceBufferDesc.byteSize = len(instanceBytes)
            instanceBufferDesc.canHaveRawViews = True
            instanceBufferDesc.structStride = len(instanceBytes) if needStructuredBuffer else 0
            instanceBufferDesc.initialState = pyd.ResourceStates.ShaderResource
            instanceBufferDesc.keepInitialState = True
            instanceBuffer = device.createBuffer(instanceBufferDesc)
            commandList.writeBuffer(instanceBuffer, instanceBytes)
            buffers.instanceBuffer = instanceBuffer

            textureFileName = folder / "media" / "nvidia-logo.png"

            material = pyd.Material()
            material.name = "CubeMaterial"
            material.useSpecularGlossModel = True
            material.enableBaseOrDiffuseTexture = True
            material.baseOrDiffuseTexture = self.textureCache.LoadTextureFromFile(
                textureFileName, True, None, commandList
            )
            material.materialConstants = pyd.CreateMaterialConstantBuffer(device, commandList, material)

            commandList.close()
            device.executeCommandList(commandList)

            if not material.baseOrDiffuseTexture or not material.baseOrDiffuseTexture.texture:
                pyd.log.error("Couldn't load the texture")
                return False

            geometry = pyd.MeshGeometry()
            geometry.material = material
            geometry.numIndices = len(_INDICES)
            geometry.numVertices = len(_POSITIONS)

            meshInfo = pyd.MeshInfo()
            meshInfo.name = "CubeMesh"
            meshInfo.buffers = buffers
            meshInfo.SetObjectSpaceBounds(-0.5, -0.5, -0.5, 0.5, 0.5, 0.5)
            meshInfo.totalIndices = geometry.numIndices
            meshInfo.totalVertices = geometry.numVertices
            meshInfo.geometries = [geometry]

            self.bufferGroup = buffers
            self.material = material
            self.meshGeometry = geometry
            self.meshInfo = meshInfo
            self.meshInstance = pyd.MeshInstance(meshInfo)

            self.sceneGraph = pyd.SceneGraph()
            node = pyd.SceneGraphNode()
            self.sceneGraph.SetRootNode(node)
            node.SetLeaf(self.meshInstance)
            node.SetName("CubeNode")

            sunLight = pyd.DirectionalLight()
            self.sceneGraph.AttachLeafNode(node, sunLight)
            sunLight.SetDirection(0.1, -1.0, 0.2)
            sunLight.angularSize = 0.53
            sunLight.irradiance = 1.0
            sunLight.SetName("Sun")

            self.sceneGraph.Refresh(0)

            return True

        def SetupView(self: DeferredShading) -> None:
            assert self.renderTargets is not None
            width, height = self.renderTargets.width, self.renderTargets.height

            self.view.SetViewport(pyd.Viewport(float(width), float(height)))
            self.view.SetMatricesOrbit(
                self.rotation, math.radians(-30.0), 2.0,
                width / height, math.radians(60.0), 0.1, 10.0,
            )
            self.view.UpdateCache()

        def Animate(self: DeferredShading, elapsedTimeSeconds: float) -> None:
            self.rotation += elapsedTimeSeconds * 1.1
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: DeferredShading) -> None:
            pass

        def Render(self: DeferredShading, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.bindingCache is not None
            assert self.deferredLightingPass is not None
            assert self.commonPasses is not None
            assert self.shaderFactory is not None
            assert self.sceneGraph is not None
            assert self.meshInstance is not None
            assert self.meshInfo is not None
            assert self.meshGeometry is not None
            assert self.material is not None
            assert self.bufferGroup is not None

            fbinfo = framebuffer.getFramebufferInfo()
            size = (fbinfo.width, fbinfo.height)

            if self.renderTargets is None or (self.renderTargets.width, self.renderTargets.height) != size:
                self.renderTargets = None
                self.bindingCache.Clear()
                self.deferredLightingPass.ResetBindingCache()
                self.gbufferPass = None

                self.renderTargets = pyd.GBufferRenderTargets()
                self.renderTargets.Init(device, size[0], size[1], 1, False, False)

                shadedColorDesc = pyd.TextureDesc()
                shadedColorDesc.width = size[0]
                shadedColorDesc.height = size[1]
                shadedColorDesc.sampleCount = 1
                shadedColorDesc.format = pyd.Format.RGBA16_FLOAT
                shadedColorDesc.isUAV = True
                shadedColorDesc.initialState = pyd.ResourceStates.UnorderedAccess
                shadedColorDesc.keepInitialState = True
                shadedColorDesc.debugName = "ShadedColor"
                self.shadedColor = device.createTexture(shadedColorDesc)

            self.SetupView()

            if not self.gbufferPass:
                params = pyd.GBufferFillPassCreateParameters()
                self.gbufferPass = pyd.GBufferFillPass(device, self.commonPasses)
                self.gbufferPass.Init(self.shaderFactory, params)

            self.commandList.open()

            self.renderTargets.Clear(self.commandList)

            drawStrategy = pyd.PassthroughDrawStrategy()
            drawStrategy.SetSingleItem(
                self.meshInstance, self.meshInfo, self.meshGeometry, self.material,
                self.bufferGroup, 0.0, pyd.RasterCullMode.Back,
            )

            context = pyd.GBufferFillPassContext()

            pyd.RenderView(
                self.commandList, self.view, self.view,
                self.renderTargets.GetFramebuffer(self.view),
                drawStrategy, self.gbufferPass, context, False,
            )

            deferredInputs = pyd.DeferredLightingPassInputs()
            deferredInputs.SetGBuffer(self.renderTargets)
            deferredInputs.SetAmbientColors(0.2, 0.2, 0.2, 0.2 * 0.3, 0.2 * 0.4, 0.2 * 0.3)
            deferredInputs.SetLights(self.sceneGraph.GetLights())
            deferredInputs.output = self.shadedColor

            self.deferredLightingPass.Render(self.commandList, self.view, deferredInputs)

            assert self.shadedColor is not None
            self.commonPasses.BlitTexture(self.commandList, framebuffer, self.shadedColor, self.bindingCache)

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
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        pyd.log.fatal(
            "Cannot initialize a graphics device with the requested parameters"
        )
        sys.exit(1)

    example = DeferredShading(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
