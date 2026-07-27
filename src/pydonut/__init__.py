from __future__ import annotations
import typing
from pydonut._pydonut import GraphicsAPI
from pydonut._pydonut import Format
from pydonut._pydonut import LogSeverity
from pydonut._pydonut import ShaderType
from pydonut._pydonut import PrimitiveType
from pydonut._pydonut import CommandQueue
from pydonut._pydonut import Color
from pydonut._pydonut import Viewport
from pydonut._pydonut import ViewportState
from pydonut._pydonut import FramebufferInfo
from pydonut._pydonut import DepthStencilState
from pydonut._pydonut import RenderState
from pydonut._pydonut import DrawArguments
from pydonut._pydonut import GraphicsPipelineDesc
from pydonut._pydonut import GraphicsState
from pydonut._pydonut import Framebuffer
from pydonut._pydonut import Texture
from pydonut._pydonut import Shader
from pydonut._pydonut import GraphicsPipeline
from pydonut._pydonut import CommandList
from pydonut._pydonut import Device
from pydonut._pydonut import IFileSystem
from pydonut._pydonut import NativeFileSystem
from pydonut._pydonut import ShaderFactory
from pydonut._pydonut import AdapterInfo
from pydonut._pydonut import IRenderPass
from pydonut._pydonut import PipelineCallbacks
from pydonut._pydonut import DeviceManager
from pydonut._pydonut import DeviceCreationParameters
from pydonut._pydonut import GetGraphicsAPIFromCommandLine
from pydonut._pydonut import GetDirectoryWithExecutable
from pydonut._pydonut import GetShaderTypeName
from pydonut._pydonut import ClearColorAttachment

try:
    # Only present when the native module was built with DXC available.
    from pydonut._pydonut import CompileShader
except ImportError:
    CompileShader = None

__all__ = (
    'GraphicsAPI',
    'Format',
    'LogSeverity',
    'ShaderType',
    'PrimitiveType',
    'CommandQueue',
    'Color',
    'Viewport',
    'ViewportState',
    'FramebufferInfo',
    'DepthStencilState',
    'RenderState',
    'DrawArguments',
    'GraphicsPipelineDesc',
    'GraphicsState',
    'Framebuffer',
    'Texture',
    'Shader',
    'GraphicsPipeline',
    'CommandList',
    'Device',
    'IFileSystem',
    'NativeFileSystem',
    'ShaderFactory',
    'AdapterInfo',
    'IRenderPass',
    'PipelineCallbacks',
    'DeviceManager',
    'DeviceCreationParameters',
    'GetGraphicsAPIFromCommandLine',
    'GetDirectoryWithExecutable',
    'GetShaderTypeName',
    'ClearColorAttachment',
    'CompileShader',
)
