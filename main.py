if __name__ == "__main__":
    from src import pydonut as pyd
    import sys

    print(pyd.hello_from_bin())

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        print("Failed to create DeviceManager.")
        exit(1)

    print("Done.")