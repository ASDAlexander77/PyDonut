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
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    folder = Path(__file__).resolve().parent

    def RunTest(device: pyd.Device) -> bool:
        api = device.getGraphicsAPI()
        shaderPath = folder / "shaders" / "headless" / "shaders.hlsl"
        source = shaderPath.read_text(encoding="utf-8")

        try:
            assert pyd.CompileShader is not None
            csBytecode = pyd.CompileShader(
                source, "main", pyd.ShaderType.Compute, api, sourceName=shaderPath.name
            )
        except RuntimeError as e:
            pyd.log.fatal(f"Shader compilation failed: {e}")
            return False

        computeShader = device.createShader(csBytecode, "main", pyd.ShaderType.Compute)
        if not computeShader:
            return False

        # The shader is performing a reduction operation within one thread group, adding all
        # uint's in the input buffer. The number of uint's is the same as the thread group size.
        numInputValues = 256

        # Create the input, output, and readback buffers...

        inputBufferDesc = pyd.BufferDesc()
        inputBufferDesc.byteSize = 4 * numInputValues
        inputBufferDesc.canHaveTypedViews = True
        inputBufferDesc.format = pyd.Format.R32_UINT
        inputBufferDesc.debugName = "InputBuffer"
        inputBufferDesc.initialState = pyd.ResourceStates.CopyDest
        inputBufferDesc.keepInitialState = True
        inputBuffer = device.createBuffer(inputBufferDesc)

        outputBufferDesc = pyd.BufferDesc()
        outputBufferDesc.byteSize = 4
        outputBufferDesc.canHaveTypedViews = True
        outputBufferDesc.canHaveUAVs = True
        outputBufferDesc.format = pyd.Format.R32_UINT
        outputBufferDesc.debugName = "OutputBuffer"
        outputBufferDesc.initialState = pyd.ResourceStates.UnorderedAccess
        outputBufferDesc.keepInitialState = True
        outputBuffer = device.createBuffer(outputBufferDesc)

        readbackBufferDesc = pyd.BufferDesc()
        readbackBufferDesc.byteSize = outputBufferDesc.byteSize
        readbackBufferDesc.cpuAccess = pyd.CpuAccessMode.Read
        readbackBufferDesc.debugName = "ReadbackBuffer"
        readbackBufferDesc.initialState = pyd.ResourceStates.CopyDest
        readbackBufferDesc.keepInitialState = True
        readbackBuffer = device.createBuffer(readbackBufferDesc)

        # Create the binding layout and binding set...

        bindingSetDesc = pyd.BindingSetDesc()
        bindingSetDesc.bindings = [
            pyd.BindingSetItem.TypedBuffer_SRV(0, inputBuffer),
            pyd.BindingSetItem.TypedBuffer_UAV(0, outputBuffer),
        ]
        bindingLayout, bindingSet = pyd.CreateBindingSetAndLayout(
            device, pyd.ShaderType.Compute, 0, bindingSetDesc
        )
        if not bindingLayout or not bindingSet:
            return False

        # Create the compute pipeline...

        computePipelineDesc = pyd.ComputePipelineDesc()
        computePipelineDesc.CS = computeShader
        computePipelineDesc.addBindingLayout(bindingLayout)
        computePipeline = device.createComputePipeline(computePipelineDesc)

        # Create a command list and begin recording

        commandList = device.createCommandList()
        commandList.open()

        # Fill the input buffer with some numbers and compute the expected result of shader
        # operation

        inputData = [i + 1 for i in range(numInputValues)]
        expectedResult = sum(inputData)
        commandList.writeBuffer(inputBuffer, struct.pack(f"<{numInputValues}I", *inputData))

        # Run the shader

        state = pyd.ComputeState()
        state.pipeline = computePipeline
        state.addBindingSet(bindingSet)
        commandList.setComputeState(state)
        commandList.dispatch(1, 1, 1)

        # Copy the shader output into the staging buffer

        commandList.copyBuffer(readbackBuffer, 0, outputBuffer, 0, readbackBufferDesc.byteSize)

        # Close and execute the command list, wait on the CPU side for it to be finished

        commandList.close()
        device.executeCommandList(commandList)
        device.waitForIdle()

        # Read the shader output

        computedResult = struct.unpack("<I", device.readBuffer(readbackBuffer, 4))[0]

        # Compare the result to the expected one to see if the test passes

        print(f"Expected result: {expectedResult}, computed result: {computedResult}")
        if computedResult == expectedResult:
            print("Test PASSED")
            return True
        else:
            print("Test FAILED!")
            return False

    is_debug = "-debug" in sys.argv

    pyd.log.ConsoleApplicationMode()
    if not is_debug:
        pyd.log.SetMinSeverity(pyd.LogSeverity.Warning)

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    for i in range(1, len(sys.argv)):
        arg = sys.argv[i]
        if arg == "--help":
            print(
                f"Usage: {sys.argv[0]} [options]\n"
                " -dx11            Use DX11 API\n"
                " -dx12            Use DX12 API (default)\n"
                " -vk              Use Vulkan API\n"
                " --list-adapters  Enumerate the graphics adapters present in the system\n"
                " --adapter <n>    Use graphics adapter with index <n> as reported by --list-adapters"
            )
            sys.exit(0)
        if arg == "--list-adapters":
            if not deviceManager.CreateInstance(deviceParams):
                pyd.log.error(f"Cannot initialize a {api} subsystem.")
                sys.exit(1)

            ok, adapters = deviceManager.EnumerateAdapters()
            if not ok:
                pyd.log.error("Cannot enumerate graphics adapters.")
                sys.exit(1)

            for adapterIndex, info in enumerate(adapters):
                deviceMemoryMB = info.dedicatedVideoMemory // (1024 * 1024)
                print(f"Adapter {adapterIndex}: {info.name} ({deviceMemoryMB} MB VRAM)")
            sys.exit(0)
        elif arg == "--adapter":
            if i + 1 >= len(sys.argv):
                pyd.log.error("--device requires a parameter")
                sys.exit(1)
            deviceParams.adapterIndex = int(sys.argv[i + 1])

    if not deviceManager.CreateHeadlessDevice(deviceParams):
        pyd.log.error("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    print(f"Using {api} API with {deviceManager.GetRendererString()}.")

    if not RunTest(deviceManager.GetDevice()):
        sys.exit(1)

    deviceManager.Shutdown()
