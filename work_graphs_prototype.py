if __name__ == "__main__":
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    folder = Path(__file__).resolve().parent

    def RunPrototype(device: pyd.Device) -> bool:
        if pyd.D3D12WorkGraphPipeline is None:
            pyd.log.error("This build has no D3D12WorkGraphPipeline (not a D3D12 build).")
            return False

        api = device.getGraphicsAPI()
        shaderDir = folder / "shaders" / "work_graphs_prototype"

        dummySource = (shaderDir / "dummy_cs.hlsl").read_text(encoding="utf-8")
        workGraphSource = (shaderDir / "work_graph.hlsl").read_text(encoding="utf-8")

        assert pyd.CompileShader is not None and pyd.CompileShaderLibrary is not None
        dummyBytecode = pyd.CompileShader(
            dummySource, "CSDummy", pyd.ShaderType.Compute, api, sourceName="dummy_cs.hlsl"
        )
        workGraphBytecode = pyd.CompileShaderLibrary(
            workGraphSource, api, sourceName="work_graph.hlsl", shaderModel="6_8"
        )

        dummyShader = device.createShader(dummyBytecode, "CSDummy", pyd.ShaderType.Compute)
        shaderLibrary = device.createShaderLibrary(workGraphBytecode)

        outputBufferDesc = pyd.BufferDesc()
        outputBufferDesc.byteSize = 4
        outputBufferDesc.canHaveTypedViews = True
        outputBufferDesc.canHaveUAVs = True
        outputBufferDesc.format = pyd.Format.R32_UINT
        outputBufferDesc.debugName = "WorkGraphOutput"
        outputBufferDesc.initialState = pyd.ResourceStates.UnorderedAccess
        outputBufferDesc.keepInitialState = True
        outputBuffer = device.createBuffer(outputBufferDesc)

        bindingSetDesc = pyd.BindingSetDesc()
        bindingSetDesc.bindings = [pyd.BindingSetItem.TypedBuffer_UAV(0, outputBuffer)]
        bindingLayout, bindingSet = pyd.CreateBindingSetAndLayout(
            device, pyd.ShaderType.Compute, 0, bindingSetDesc
        )
        if not bindingLayout or not bindingSet:
            pyd.log.error("Failed to create binding layout/set.")
            return False

        dummyPipelineDesc = pyd.ComputePipelineDesc()
        dummyPipelineDesc.CS = dummyShader
        dummyPipelineDesc.addBindingLayout(bindingLayout)
        dummyPipeline = device.createComputePipeline(dummyPipelineDesc)

        workGraphPipeline = pyd.D3D12WorkGraphPipeline(
            device, shaderLibrary, dummyPipeline, "PrototypeWorkGraph"
        )
        backingSize = workGraphPipeline.getBackingMemorySize()
        print(f"Work graph backing memory size: {backingSize} bytes")

        backingBufferDesc = pyd.BufferDesc()
        backingBufferDesc.byteSize = max(backingSize, 1)
        backingBufferDesc.canHaveUAVs = True
        backingBufferDesc.debugName = "WorkGraphBackingMemory"
        backingBufferDesc.initialState = pyd.ResourceStates.UnorderedAccess
        backingBufferDesc.keepInitialState = True
        backingBuffer = device.createBuffer(backingBufferDesc)

        readbackBufferDesc = pyd.BufferDesc()
        readbackBufferDesc.byteSize = outputBufferDesc.byteSize
        readbackBufferDesc.cpuAccess = pyd.CpuAccessMode.Read
        readbackBufferDesc.debugName = "ReadbackBuffer"
        readbackBufferDesc.initialState = pyd.ResourceStates.CopyDest
        readbackBufferDesc.keepInitialState = True
        readbackBuffer = device.createBuffer(readbackBufferDesc)

        commandList = device.createCommandList()
        commandList.open()

        state = pyd.ComputeState()
        state.pipeline = dummyPipeline
        state.addBindingSet(bindingSet)
        commandList.setComputeState(state)

        commandList.dispatchWorkGraph(workGraphPipeline, backingBuffer, True, 1)

        commandList.copyBuffer(readbackBuffer, 0, outputBuffer, 0, readbackBufferDesc.byteSize)

        commandList.close()
        device.executeCommandList(commandList)
        device.waitForIdle()

        computedResult = struct.unpack("<I", device.readBuffer(readbackBuffer, 4))[0]
        expectedResult = 0xC0FFEE
        print(f"Expected result: {expectedResult:#x}, computed result: {computedResult:#x}")
        return computedResult == expectedResult

    is_debug = "-debug" in sys.argv
    pyd.log.ConsoleApplicationMode()
    if not is_debug:
        pyd.log.SetMinSeverity(pyd.LogSeverity.Warning)

    api = pyd.GraphicsAPI.D3D12
    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateHeadlessDevice(deviceParams):
        pyd.log.error("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    ok = RunPrototype(deviceManager.GetDevice())
    print("Test PASSED" if ok else "Test FAILED!")
    deviceManager.Shutdown()
    sys.exit(0 if ok else 1)
