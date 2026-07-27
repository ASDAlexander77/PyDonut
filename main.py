from xmlrpc.client import Boolean
if __name__ == "__main__":
    import sys
    from src import pydonut as pyd

    class BasicTriangle(pyd.IRenderPass):
        def __init__(self: BasicTriangle, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            pass

        def Init(self: BasicTriangle) -> Boolean:
            return True

        def BackBufferResizing(self: BasicTriangle):
            pass

        def Animate(self: BasicTriangle, elapsedTimeSeconds: float):
            pass

        def Render(self: BasicTriangle, framebuffer: pyd.Framebuffer):
            pass


    is_debug = "--debug" in sys.argv or "-d" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        print("Failed to create DeviceManager.", file=sys.stderr)
        exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        print("Cannot initialize a graphics device with the requested parameters", file=sys.stderr)
        exit(1)

    example = BasicTriangle(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")