from enum import Enum

class GraphicsAPI(Enum):
    D3D11 = 0
    D3D12 = 1
    Vulkan = 2

def GetGraphicsAPIFromCommandLine(args: list[str]) -> GraphicsAPI: ...