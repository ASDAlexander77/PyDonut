from __future__ import annotations
import typing
from pydonut._pydonut import GraphicsAPI
from pydonut._pydonut import Format
from pydonut._pydonut import LogSeverity
from pydonut._pydonut import ShaderType
from pydonut._pydonut import PrimitiveType
from pydonut._pydonut import ComparisonFunc
from pydonut._pydonut import RasterCullMode
from pydonut._pydonut import CommandQueue
from pydonut._pydonut import Feature
from pydonut._pydonut import ResourceStates
from pydonut._pydonut import TextureDimension
from pydonut._pydonut import VariableShadingRate
from pydonut._pydonut import ShadingRateCombiner
from pydonut._pydonut import GeometryFlags
from pydonut._pydonut import InstanceFlags
from pydonut._pydonut import Color
from pydonut._pydonut import Viewport
from pydonut._pydonut import ViewportState
from pydonut._pydonut import FramebufferInfo
from pydonut._pydonut import DepthStencilState
from pydonut._pydonut import RasterState
from pydonut._pydonut import RenderState
from pydonut._pydonut import VertexAttributeDesc
from pydonut._pydonut import DrawArguments
from pydonut._pydonut import GraphicsPipelineDesc
from pydonut._pydonut import GraphicsState
from pydonut._pydonut import MeshletPipelineDesc
from pydonut._pydonut import MeshletState
from pydonut._pydonut import VariableRateShadingState
from pydonut._pydonut import VariableRateShadingFeatureInfo
from pydonut._pydonut import ComputePipelineDesc
from pydonut._pydonut import ComputeState
from pydonut._pydonut import BufferDesc
from pydonut._pydonut import TextureDesc
from pydonut._pydonut import FramebufferAttachment
from pydonut._pydonut import FramebufferDesc
from pydonut._pydonut import BindingLayoutItem
from pydonut._pydonut import BindingLayoutDesc
from pydonut._pydonut import BufferRange
from pydonut._pydonut import BindingSetItem
from pydonut._pydonut import BindingSetDesc
from pydonut._pydonut import BindlessLayoutDesc
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
from pydonut._pydonut import InputLayout
from pydonut._pydonut import GraphicsPipeline
from pydonut._pydonut import MeshletPipeline
from pydonut._pydonut import ComputePipeline
from pydonut._pydonut import RayTracingPipeline
from pydonut._pydonut import ShaderTable
from pydonut._pydonut import CommandList
from pydonut._pydonut import Buffer
from pydonut._pydonut import BindingLayout
from pydonut._pydonut import BindingSet
from pydonut._pydonut import Sampler
from pydonut._pydonut import AccelStruct
from pydonut._pydonut import Device
from pydonut._pydonut import IFileSystem
from pydonut._pydonut import NativeFileSystem
from pydonut._pydonut import RootFileSystem
from pydonut._pydonut import ShaderFactory
from pydonut._pydonut import BindingCache
from pydonut._pydonut import CommonRenderPasses
from pydonut._pydonut import DescriptorTableManager
from pydonut._pydonut import TextureCache
from pydonut._pydonut import LoadedTexture
from pydonut._pydonut import VertexAttribute
from pydonut._pydonut import BufferGroup
from pydonut._pydonut import Material
from pydonut._pydonut import CreateMaterialConstantBuffer
from pydonut._pydonut import MeshGeometry
from pydonut._pydonut import MeshInfo
from pydonut._pydonut import SceneGraphLeaf
from pydonut._pydonut import MeshInstance
from pydonut._pydonut import Light
from pydonut._pydonut import DirectionalLight
from pydonut._pydonut import SceneGraphNode
from pydonut._pydonut import SceneGraph
from pydonut._pydonut import Scene
from pydonut._pydonut import SceneLoaded
from pydonut._pydonut import FirstPersonCamera
from pydonut._pydonut import PlanarView
from pydonut._pydonut import IDrawStrategy
from pydonut._pydonut import IGeometryPass
from pydonut._pydonut import GeometryPassContext
from pydonut._pydonut import GBufferRenderTargets
from pydonut._pydonut import GBufferFillPassCreateParameters
from pydonut._pydonut import GBufferFillPassContext
from pydonut._pydonut import GBufferFillPass
from pydonut._pydonut import PassthroughDrawStrategy
from pydonut._pydonut import InstancedOpaqueDrawStrategy
from pydonut._pydonut import TransparentDrawStrategy
from pydonut._pydonut import DeferredLightingPassInputs
from pydonut._pydonut import DeferredLightingPass
from pydonut._pydonut import ForwardShadingPassCreateParameters
from pydonut._pydonut import ForwardShadingPassContext
from pydonut._pydonut import ForwardShadingPass
from pydonut._pydonut import TemporalAntiAliasingParameters
from pydonut._pydonut import TemporalAntiAliasingCreateParameters
from pydonut._pydonut import TemporalAntiAliasingPass
from pydonut._pydonut import FramebufferFactory
from pydonut._pydonut import RenderView
from pydonut._pydonut import RenderCompositeView
from pydonut._pydonut import AdapterInfo
from pydonut._pydonut import IRenderPass
from pydonut._pydonut import ApplicationBase
from pydonut._pydonut import PipelineCallbacks
from pydonut._pydonut import DeviceManager
from pydonut._pydonut import DeviceCreationParameters
from pydonut._pydonut import GetGraphicsAPIFromCommandLine
from pydonut._pydonut import GetDirectoryWithExecutable
from pydonut._pydonut import GetShaderTypeName
from pydonut._pydonut import ClearColorAttachment
from pydonut._pydonut import ClearDepthStencilAttachment
from pydonut._pydonut import BuildBottomLevelAccelStruct
from pydonut._pydonut import CreateVolatileConstantBufferDesc
from pydonut._pydonut import CreateStaticConstantBufferDesc
from pydonut._pydonut import ComputeRotatingViewProjMatrix
from pydonut._pydonut import CreateBindingSetAndLayout
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
    'ComparisonFunc',
    'RasterCullMode',
    'CommandQueue',
    'Feature',
    'ResourceStates',
    'TextureDimension',
    'VariableShadingRate',
    'ShadingRateCombiner',
    'GeometryFlags',
    'InstanceFlags',
    'Color',
    'Viewport',
    'ViewportState',
    'FramebufferInfo',
    'DepthStencilState',
    'RasterState',
    'RenderState',
    'VertexAttributeDesc',
    'DrawArguments',
    'GraphicsPipelineDesc',
    'GraphicsState',
    'MeshletPipelineDesc',
    'MeshletState',
    'VariableRateShadingState',
    'VariableRateShadingFeatureInfo',
    'ComputePipelineDesc',
    'ComputeState',
    'BufferDesc',
    'TextureDesc',
    'FramebufferAttachment',
    'FramebufferDesc',
    'BindingLayoutItem',
    'BindingLayoutDesc',
    'BufferRange',
    'BindingSetItem',
    'BindingSetDesc',
    'BindlessLayoutDesc',
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
    'InputLayout',
    'GraphicsPipeline',
    'MeshletPipeline',
    'ComputePipeline',
    'RayTracingPipeline',
    'ShaderTable',
    'CommandList',
    'Buffer',
    'BindingLayout',
    'BindingSet',
    'Sampler',
    'AccelStruct',
    'Device',
    'IFileSystem',
    'NativeFileSystem',
    'RootFileSystem',
    'ShaderFactory',
    'BindingCache',
    'CommonRenderPasses',
    'DescriptorTableManager',
    'TextureCache',
    'LoadedTexture',
    'VertexAttribute',
    'BufferGroup',
    'Material',
    'CreateMaterialConstantBuffer',
    'MeshGeometry',
    'MeshInfo',
    'SceneGraphLeaf',
    'MeshInstance',
    'Light',
    'DirectionalLight',
    'SceneGraphNode',
    'SceneGraph',
    'Scene',
    'SceneLoaded',
    'FirstPersonCamera',
    'PlanarView',
    'IDrawStrategy',
    'IGeometryPass',
    'GeometryPassContext',
    'GBufferRenderTargets',
    'GBufferFillPassCreateParameters',
    'GBufferFillPassContext',
    'GBufferFillPass',
    'PassthroughDrawStrategy',
    'InstancedOpaqueDrawStrategy',
    'TransparentDrawStrategy',
    'DeferredLightingPassInputs',
    'DeferredLightingPass',
    'ForwardShadingPassCreateParameters',
    'ForwardShadingPassContext',
    'ForwardShadingPass',
    'TemporalAntiAliasingParameters',
    'TemporalAntiAliasingCreateParameters',
    'TemporalAntiAliasingPass',
    'FramebufferFactory',
    'RenderView',
    'RenderCompositeView',
    'AdapterInfo',
    'IRenderPass',
    'ApplicationBase',
    'PipelineCallbacks',
    'DeviceManager',
    'DeviceCreationParameters',
    'GetGraphicsAPIFromCommandLine',
    'GetDirectoryWithExecutable',
    'GetShaderTypeName',
    'ClearColorAttachment',
    'ClearDepthStencilAttachment',
    'BuildBottomLevelAccelStruct',
    'CreateVolatileConstantBufferDesc',
    'CreateStaticConstantBufferDesc',
    'ComputeRotatingViewProjMatrix',
    'CreateBindingSetAndLayout',
    'log',
    'CompileShader',
    'CompileShaderLibrary',
)
