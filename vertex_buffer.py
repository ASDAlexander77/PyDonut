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

    WINDOW_TITLE = "PyDonut Vertex Buffer"
    folder = Path(__file__).resolve().parent

    NUM_VIEWS = 4
    # This example uses a single large constant buffer with multiple views to draw multiple
    # rotated versions of the same model. Partially bound constant buffers must have offsets
    # aligned to nvrhi.c_ConstantBufferOffsetSizeAlignment (256) and sizes that are a multiple
    # of it -- each view's viewProjMatrix (64 bytes) is padded out to that with zeros.
    CONSTANT_BUFFER_ENTRY_SIZE = 256
    _ROTATION_AXES = [
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
    ]

    # Transcribed from Donut-Samples/examples/vertex_buffer/vertex_buffer.cpp.
    # Each entry is (posX, posY, posZ, u, v).
    _VERTICES = [
        (-0.5, 0.5, -0.5, 0.0, 0.0), (0.5, -0.5, -0.5, 1.0, 1.0),  # front face
        (-0.5, -0.5, -0.5, 0.0, 1.0), (0.5, 0.5, -0.5, 1.0, 0.0),

        (0.5, -0.5, -0.5, 0.0, 1.0), (0.5, 0.5, 0.5, 1.0, 0.0),    # right side face
        (0.5, -0.5, 0.5, 1.0, 1.0), (0.5, 0.5, -0.5, 0.0, 0.0),

        (-0.5, 0.5, 0.5, 0.0, 0.0), (-0.5, -0.5, -0.5, 1.0, 1.0),  # left side face
        (-0.5, -0.5, 0.5, 0.0, 1.0), (-0.5, 0.5, -0.5, 1.0, 0.0),

        (0.5, 0.5, 0.5, 0.0, 0.0), (-0.5, -0.5, 0.5, 1.0, 1.0),    # back face
        (0.5, -0.5, 0.5, 0.0, 1.0), (-0.5, 0.5, 0.5, 1.0, 0.0),

        (-0.5, 0.5, -0.5, 0.0, 1.0), (0.5, 0.5, 0.5, 1.0, 0.0),    # top face
        (0.5, 0.5, -0.5, 1.0, 1.0), (-0.5, 0.5, 0.5, 0.0, 0.0),

        (0.5, -0.5, 0.5, 1.0, 1.0), (-0.5, -0.5, -0.5, 0.0, 0.0),  # bottom face
        (0.5, -0.5, -0.5, 1.0, 0.0), (-0.5, -0.5, 0.5, 0.0, 1.0),
    ]
    _INDICES = [
        0, 1, 2, 0, 3, 1,
        4, 5, 6, 4, 7, 5,
        8, 9, 10, 8, 11, 9,
        12, 13, 14, 12, 15, 13,
        16, 17, 18, 16, 19, 17,
        20, 21, 22, 20, 23, 21,
    ]
    # sizeof(float3) + sizeof(float2) == 20 bytes; position is first, uv follows.
    VERTEX_STRIDE = 20
    POSITION_OFFSET = 0
    UV_OFFSET = 12

    def _build_vertex_bytes() -> bytes:
        return struct.pack(f"<{len(_VERTICES) * 5}f", *(c for v in _VERTICES for c in v))

    class VertexBuffer(pyd.IRenderPass):
        def __init__(self: VertexBuffer, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.vertexShader: pyd.Shader | None = None
            self.pixelShader: pyd.Shader | None = None
            self.inputLayout: pyd.InputLayout | None = None
            self.constantBuffer: pyd.Buffer | None = None
            self.vertexBuffer: pyd.Buffer | None = None
            self.indexBuffer: pyd.Buffer | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindingSets: list[pyd.BindingSet | None] = [None] * NUM_VIEWS
            self.pipeline: pyd.GraphicsPipeline | None = None
            self.commandList: pyd.CommandList | None = None
            self.rotation = 0.0

        def Init(self: VertexBuffer) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "vertex_buffer" / "shaders.hlsl"
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

            constantBufferDesc = pyd.CreateStaticConstantBufferDesc(
                CONSTANT_BUFFER_ENTRY_SIZE * NUM_VIEWS, "ConstantBuffer"
            )
            constantBufferDesc.initialState = pyd.ResourceStates.ConstantBuffer
            constantBufferDesc.keepInitialState = True
            self.constantBuffer = device.createBuffer(constantBufferDesc)

            posAttr = pyd.VertexAttributeDesc()
            posAttr.name = "POSITION"
            posAttr.format = pyd.Format.RGB32_FLOAT
            posAttr.bufferIndex = 0
            posAttr.elementStride = VERTEX_STRIDE

            uvAttr = pyd.VertexAttributeDesc()
            uvAttr.name = "UV"
            uvAttr.format = pyd.Format.RG32_FLOAT
            uvAttr.bufferIndex = 1
            uvAttr.elementStride = VERTEX_STRIDE

            self.inputLayout = device.createInputLayout([posAttr, uvAttr], self.vertexShader)

            # CommonRenderPasses' own shaders (used by TextureCache for mip generation) are
            # only statically linked in when Donut is built with DONUT_WITH_STATIC_SHADERS,
            # which this project's CMake leaves off -- so read them as precompiled .bin
            # files via the filesystem instead, same as the other examples.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            passesShaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))
            commonPasses = pyd.CommonRenderPasses(device, passesShaderFactory)

            nativeFS = pyd.NativeFileSystem()
            textureCache = pyd.TextureCache(device, nativeFS, None)

            self.commandList = device.createCommandList()
            self.commandList.open()

            vertexBufferDesc = pyd.BufferDesc()
            vertexBufferDesc.byteSize = len(_VERTICES) * VERTEX_STRIDE
            vertexBufferDesc.isVertexBuffer = True
            vertexBufferDesc.debugName = "VertexBuffer"
            vertexBufferDesc.initialState = pyd.ResourceStates.VertexBuffer
            vertexBufferDesc.keepInitialState = True
            self.vertexBuffer = device.createBuffer(vertexBufferDesc)
            self.commandList.writeBuffer(self.vertexBuffer, _build_vertex_bytes())

            indices = struct.pack(f"<{len(_INDICES)}I", *_INDICES)
            indexBufferDesc = pyd.BufferDesc()
            indexBufferDesc.byteSize = len(indices)
            indexBufferDesc.isIndexBuffer = True
            indexBufferDesc.debugName = "IndexBuffer"
            indexBufferDesc.initialState = pyd.ResourceStates.IndexBuffer
            indexBufferDesc.keepInitialState = True
            self.indexBuffer = device.createBuffer(indexBufferDesc)
            self.commandList.writeBuffer(self.indexBuffer, indices)

            textureFileName = folder / "media" / "nvidia-logo.png"
            texture = textureCache.LoadTextureFromFile(textureFileName, True, None, self.commandList)

            self.commandList.close()
            device.executeCommandList(self.commandList)

            if not texture or not texture.texture:
                pyd.log.error("Couldn't load the texture")
                return False

            # Create a single binding layout and multiple binding sets, one set per view.
            # The different binding sets use different slices of the same constant buffer.
            # All 4 binding sets must share the exact same BindingLayout object -- a pipeline
            # is created against one layout instance, and nvrhi validates every binding set
            # used with it against that same instance, not just a structurally equal one.
            # pyd.CreateBindingSetAndLayout always allocates a fresh layout (unlike the C++
            # nvrhi::utils::CreateBindingSetAndLayout, which reuses an existing BindingLayoutHandle&
            # passed back in), so only the first view goes through it; the rest reuse
            # self.bindingLayout via Device.createBindingSet directly.
            for viewIndex in range(NUM_VIEWS):
                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.ConstantBuffer(
                        0, self.constantBuffer,
                        pyd.BufferRange(CONSTANT_BUFFER_ENTRY_SIZE * viewIndex, CONSTANT_BUFFER_ENTRY_SIZE),
                    ),
                    # Texture and sampler are the same for all model views.
                    pyd.BindingSetItem.Texture_SRV(0, texture.texture),
                    pyd.BindingSetItem.Sampler(0, commonPasses.m_AnisotropicWrapSampler),
                ]
                if self.bindingLayout is None:
                    self.bindingLayout, bindingSet = pyd.CreateBindingSetAndLayout(
                        device, pyd.ShaderType.All, 0, bindingSetDesc
                    )
                else:
                    bindingSet = device.createBindingSet(bindingSetDesc, self.bindingLayout)
                self.bindingSets[viewIndex] = bindingSet

            return True

        def Animate(self: VertexBuffer, elapsedTimeSeconds: float) -> None:
            self.rotation += elapsedTimeSeconds * 1.1
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: VertexBuffer) -> None:
            self.pipeline = None

        def Render(self: VertexBuffer, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.constantBuffer is not None
            assert self.vertexBuffer is not None
            assert self.indexBuffer is not None
            assert self.bindingLayout is not None

            fbinfo = framebuffer.getFramebufferInfo()

            if not self.pipeline:
                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.vertexShader
                psoDesc.PS = self.pixelShader
                psoDesc.inputLayout = self.inputLayout
                psoDesc.addBindingLayout(self.bindingLayout)
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.renderState.depthStencilState.depthTestEnable = False

                self.pipeline = device.createGraphicsPipeline(psoDesc, framebuffer.getFramebufferInfo())

            self.commandList.open()

            pyd.ClearColorAttachment(self.commandList, framebuffer, 0, pyd.Color(0.0))

            # Fill out the constant buffer slices for the multiple views of the model, and
            # upload them all at once.
            aspectRatio = float(fbinfo.width) / float(fbinfo.height)
            constants = bytearray()
            for axis in _ROTATION_AXES:
                viewProjBytes = pyd.ComputeRotatingViewProjMatrix(
                    axis[0], axis[1], axis[2], self.rotation,
                    math.radians(-30.0), 2.0, aspectRatio, math.radians(60.0), 0.1, 10.0,
                )
                constants += viewProjBytes
                constants += bytes(CONSTANT_BUFFER_ENTRY_SIZE - len(viewProjBytes))
            self.commandList.writeBuffer(self.constantBuffer, bytes(constants))

            for viewIndex in range(NUM_VIEWS):
                state = pyd.GraphicsState()
                # Pick the right binding set for this view.
                viewBindingSet = self.bindingSets[viewIndex]
                assert viewBindingSet is not None
                state.addBindingSet(viewBindingSet)
                state.setIndexBuffer(self.indexBuffer, pyd.Format.R32_UINT, 0)
                # Bind the vertex buffers in reverse order to test binding-slot handling,
                # matching the C++ sample.
                state.addVertexBuffer(self.vertexBuffer, 1, UV_OFFSET)
                state.addVertexBuffer(self.vertexBuffer, 0, POSITION_OFFSET)
                state.pipeline = self.pipeline
                state.framebuffer = framebuffer

                # Construct the viewport so that all viewports form a grid.
                width = float(fbinfo.width) * 0.5
                height = float(fbinfo.height) * 0.5
                left = width * float(viewIndex % 2)
                top = height * float(viewIndex // 2)
                viewport = pyd.Viewport(left, left + width, top, top + height, 0.0, 1.0)
                state.viewport.addViewportAndScissorRect(viewport)

                self.commandList.setGraphicsState(state)

                args = pyd.DrawArguments()
                args.vertexCount = len(_INDICES)
                self.commandList.drawIndexed(args)

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

    example = VertexBuffer(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
