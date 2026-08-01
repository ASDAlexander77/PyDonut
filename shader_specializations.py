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
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Shader Specializations"
    folder = Path(__file__).resolve().parent

    # (vertex-shader x-offset, pixel-shader color) per triangle -- transcribed verbatim from
    # Donut-Samples/examples/shader_specializations/shader_specializations.cpp. Expected output:
    # 4 triangles side-by-side; red, green, blue, magenta.
    _OFFSETS = [float(i) * 0.5 - 0.75 for i in range(4)]
    _COLORS = [0x0000FF, 0x00FF00, 0xFF0000, 0xFF00FF]

    class ShaderSpecializations(pyd.IRenderPass):
        def __init__(self: ShaderSpecializations, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.vertexShader: pyd.Shader | None = None
            self.pixelShader: pyd.Shader | None = None
            self.pipelines: list[pyd.GraphicsPipeline] = []
            self.commandList: pyd.CommandList | None = None

        def Init(self: ShaderSpecializations) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "shader_specializations" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                vsBytecode = pyd.CompileShader(
                    source, "main_vs", pyd.ShaderType.Vertex, api, sourceName=shaderPath.name
                )
                psBytecode = pyd.CompileShader(
                    source, "main_ps", pyd.ShaderType.Pixel, api, sourceName=shaderPath.name
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.vertexShader = device.createShader(vsBytecode, "main_vs", pyd.ShaderType.Vertex)
            self.pixelShader = device.createShader(psBytecode, "main_ps", pyd.ShaderType.Pixel)

            if not self.vertexShader or not self.pixelShader:
                return False

            self.commandList = device.createCommandList()

            return True

        def Animate(self: ShaderSpecializations, elapsedTimeSeconds: float) -> None:
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def BackBufferResizing(self: ShaderSpecializations) -> None:
            self.pipelines = []

        def Render(self: ShaderSpecializations, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.vertexShader is not None
            assert self.pixelShader is not None

            if not self.pipelines:
                # Created lazily here (cheap, so no need to do it ahead of time) rather than in
                # Init(), matching the C++ original.
                for offset, color in zip(_OFFSETS, _COLORS):
                    vertexShader = device.createShaderSpecialization(
                        self.vertexShader, [pyd.ShaderSpecialization.Float(0, offset)]
                    )
                    pixelShader = device.createShaderSpecialization(
                        self.pixelShader, [pyd.ShaderSpecialization.UInt32(1, color)]
                    )

                    psoDesc = pyd.GraphicsPipelineDesc()
                    psoDesc.VS = vertexShader
                    psoDesc.PS = pixelShader
                    psoDesc.primType = pyd.PrimitiveType.TriangleList
                    psoDesc.renderState.depthStencilState.depthTestEnable = False

                    pipeline = device.createGraphicsPipeline(psoDesc, framebuffer.getFramebufferInfo())
                    self.pipelines.append(pipeline)

            self.commandList.open()

            pyd.ClearColorAttachment(self.commandList, framebuffer, 0, pyd.Color(0.0))

            # Render triangles, one with each pipeline.
            for pipeline in self.pipelines:
                state = pyd.GraphicsState()
                state.pipeline = pipeline
                state.framebuffer = framebuffer
                state.viewport.addViewportAndScissorRect(
                    framebuffer.getFramebufferInfo().getViewport()
                )

                self.commandList.setGraphicsState(state)

                args = pyd.DrawArguments()
                args.vertexCount = 3
                self.commandList.draw(args)

            self.commandList.close()
            device.executeCommandList(self.commandList)

    is_debug = "-debug" in sys.argv

    # Vulkan-only: shader specialization constants ([[vk::constant_id(N)]]) are a Vulkan-
    # specific nvrhi feature with no D3D12 equivalent, matching the C++ original hardcoding
    # GraphicsAPI::VULKAN rather than taking a -d3d12/-vk command-line flag.
    api = pyd.GraphicsAPI.Vulkan
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

    example = ShaderSpecializations(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
