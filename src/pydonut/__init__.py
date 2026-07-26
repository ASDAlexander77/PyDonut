from __future__ import annotations
import typing
from pydonut._core import hello_from_bin
from pydonut._pydonut import GraphicsAPI
from pydonut._pydonut import GetGraphicsAPIFromCommandLine

__all__ = (
    'hello_from_bin', 
    'GraphicsAPI',
    'DeviceManager',
    'GetGraphicsAPIFromCommandLine',
)

class DeviceManager():
    @staticmethod
    def Create(api: GraphicsAPI = GraphicsAPI.Vulkan) -> DeviceManager: ...        
