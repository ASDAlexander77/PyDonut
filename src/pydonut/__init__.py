from __future__ import annotations
import typing
from pydonut._pydonut import GraphicsAPI
from pydonut._pydonut import Format
from pydonut._pydonut import LogSeverity
from pydonut._pydonut import ShaderType
from pydonut._pydonut import PrimitiveType
from pydonut._pydonut import CommandQueue
from pydonut._pydonut import Feature
from pydonut._pydonut import ResourceStates
from pydonut._pydonut import GeometryFlags
from pydonut._pydonut import InstanceFlags
from pydonut._pydonut import Color
from pydonut._pydonut import Viewport
from pydonut._pydonut import ViewportState
from pydonut._pydonut import FramebufferInfo
from pydonut._pydonut import DepthStencilState
from pydonut._pydonut import RenderState
from pydonut._pydonut import DrawArguments
from pydonut._pydonut import GraphicsPipelineDesc
from pydonut._pydonut import GraphicsState
from pydonut._pydonut import BufferDesc
from pydonut._pydonut import TextureDesc
from pydonut._pydonut import FramebufferAttachment
from pydonut._pydonut import FramebufferDesc
from pydonut._pydonut import BindingLayoutItem
from pydonut._pydonut import BindingLayoutDesc
from pydonut._pydonut import BindingSetItem
from pydonut._pydonut import BindingSetDesc
from pydonut._pydonut import GeometryTriangles
from pydonut._pydonut import GeometryDesc
from pydonut._pydonut import AccelStructDesc
from pydonut._pydonut import InstanceDesc
from pydonut._pydonut import PipelineShaderDesc
from pydonut._pydonut import PipelineHitGroupDesc
from pydonut._pydonut import RayTracingPipelineDesc
from pydonut._pydonut import RayTracingState
from pydonut._pydonut import DispatchRaysArguments
from pydonut._pydonut import Framebuffer
from pydonut._pydonut import Texture
from pydonut._pydonut import Shader
from pydonut._pydonut import ShaderLibrary
from pydonut._pydonut import GraphicsPipeline
from pydonut._pydonut import RayTracingPipeline
from pydonut._pydonut import ShaderTable
from pydonut._pydonut import CommandList
from pydonut._pydonut import Buffer
from pydonut._pydonut import BindingLayout
from pydonut._pydonut import BindingSet
from pydonut._pydonut import AccelStruct
from pydonut._pydonut import Device
from pydonut._pydonut import IFileSystem
from pydonut._pydonut import NativeFileSystem
from pydonut._pydonut import RootFileSystem
from pydonut._pydonut import ShaderFactory
from pydonut._pydonut import BindingCache
from pydonut._pydonut import CommonRenderPasses
from pydonut._pydonut import AdapterInfo
from pydonut._pydonut import IRenderPass
from pydonut._pydonut import PipelineCallbacks
from pydonut._pydonut import DeviceManager
from pydonut._pydonut import DeviceCreationParameters
from pydonut._pydonut import GetGraphicsAPIFromCommandLine
from pydonut._pydonut import GetDirectoryWithExecutable
from pydonut._pydonut import GetShaderTypeName
from pydonut._pydonut import ClearColorAttachment
from pydonut._pydonut import BuildBottomLevelAccelStruct
from pydonut._pydonut import log

try:
    # Only present when the native module was built with DXC available.
    from pydonut._pydonut import CompileShader
    from pydonut._pydonut import CompileShaderLibrary
except ImportError:
    CompileShader = None
    CompileShaderLibrary = None

__all__ = (
    'GraphicsAPI',
    'Format',
    'LogSeverity',
    'ShaderType',
    'PrimitiveType',
    'CommandQueue',
    'Feature',
    'ResourceStates',
    'GeometryFlags',
    'InstanceFlags',
    'Color',
    'Viewport',
    'ViewportState',
    'FramebufferInfo',
    'DepthStencilState',
    'RenderState',
    'DrawArguments',
    'GraphicsPipelineDesc',
    'GraphicsState',
    'BufferDesc',
    'TextureDesc',
    'FramebufferAttachment',
    'FramebufferDesc',
    'BindingLayoutItem',
    'BindingLayoutDesc',
    'BindingSetItem',
    'BindingSetDesc',
    'GeometryTriangles',
    'GeometryDesc',
    'AccelStructDesc',
    'InstanceDesc',
    'PipelineShaderDesc',
    'PipelineHitGroupDesc',
    'RayTracingPipelineDesc',
    'RayTracingState',
    'DispatchRaysArguments',
    'Framebuffer',
    'Texture',
    'Shader',
    'ShaderLibrary',
    'GraphicsPipeline',
    'RayTracingPipeline',
    'ShaderTable',
    'CommandList',
    'Buffer',
    'BindingLayout',
    'BindingSet',
    'AccelStruct',
    'Device',
    'IFileSystem',
    'NativeFileSystem',
    'RootFileSystem',
    'ShaderFactory',
    'BindingCache',
    'CommonRenderPasses',
    'AdapterInfo',
    'IRenderPass',
    'PipelineCallbacks',
    'DeviceManager',
    'DeviceCreationParameters',
    'GetGraphicsAPIFromCommandLine',
    'GetDirectoryWithExecutable',
    'GetShaderTypeName',
    'ClearColorAttachment',
    'BuildBottomLevelAccelStruct',
    'log',
    'CompileShader',
    'CompileShaderLibrary',
)
