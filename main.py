if __name__ == "__main__":
    import sys
    from src import pydonut as pyd

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

    # TODO: finish it
    deviceManager.RunMessageLoop()

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")