from enum import Enum

class GraphicsAPI(Enum):
    D3D11 = 0
    D3D12 = 1
    Vulkan = 2

def GetGraphicsAPIFromCommandLine(args: list[str]) -> GraphicsAPI: ...

class DeviceManager():
    @staticmethod
    def Create(api: GraphicsAPI = GraphicsAPI.Vulkan) -> DeviceManager: ...
    def CreateWindowDeviceAndSwapChain(self: DeviceManager, params: DeviceCreationParameters, windowTitle: str = "") -> bool: ...
    def RunMessageLoop(self: DeviceManager) -> None: ...
    def Shutdown(self: DeviceManager) -> None: ...

class DeviceCreationParameters():
    enableDebugRuntime: bool
    enableNvrhiValidationLayer: bool
