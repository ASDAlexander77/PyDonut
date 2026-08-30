# /******************************************************************************
# * Copyright (C) 1991-2026 ASDAlexander77.
# *
# * Permission is hereby granted, free of charge, to any person obtaining
# * a copy of this software and associated documentation files (the
# * "Software"), to deal in the Software without restriction, including
# * without limitation the rights to use, copy, modify, merge, publish,
# * distribute, sublicense, and/or sell copies of the Software, and to
# * permit persons to whom the Software is furnished to do so, subject to
# * the following conditions:
# *
# * The above copyright notice and this permission notice shall be
# * included in all copies or substantial portions of the Software.
# *
# * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# * IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# * CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# * TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ******************************************************************************/

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
from pydonut._pydonut import CpuAccessMode
from pydonut._pydonut import Feature
from pydonut._pydonut import ResourceStates
from pydonut._pydonut import TextureDimension
from pydonut._pydonut import VariableShadingRate
from pydonut._pydonut import ShadingRateCombiner
from pydonut._pydonut import GeometryFlags
from pydonut._pydonut import AccelStructBuildFlags
from pydonut._pydonut import InstanceFlags
from pydonut._pydonut import ShaderSpecialization
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
from pydonut._pydonut import GeometryAABB
from pydonut._pydonut import GeometryAABBs
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
from pydonut._pydonut import TimerQuery
from pydonut._pydonut import ShaderLibrary
from pydonut._pydonut import InputLayout
from pydonut._pydonut import GraphicsPipeline
from pydonut._pydonut import MeshletPipeline
from pydonut._pydonut import ComputePipeline
from pydonut._pydonut import RayTracingPipeline
from pydonut._pydonut import ShaderTable
from pydonut._pydonut import CommandListParameters
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
from pydonut._pydonut import BlitParameters
from pydonut._pydonut import CommonRenderPasses
from pydonut._pydonut import DescriptorHandle
from pydonut._pydonut import DescriptorTableManager
from pydonut._pydonut import TextureCache
from pydonut._pydonut import LoadedTexture
from pydonut._pydonut import VertexAttribute
from pydonut._pydonut import BufferGroup
from pydonut._pydonut import MaterialDomain
from pydonut._pydonut import Material
from pydonut._pydonut import CreateMaterialConstantBuffer
from pydonut._pydonut import MeshGeometry
from pydonut._pydonut import MeshInfo
from pydonut._pydonut import SceneGraphLeaf
from pydonut._pydonut import MeshInstance
from pydonut._pydonut import SkinnedMeshInstance
from pydonut._pydonut import IShadowMap
from pydonut._pydonut import Light
from pydonut._pydonut import DirectionalLight
from pydonut._pydonut import SpotLight
from pydonut._pydonut import PointLight
from pydonut._pydonut import LightProbe
from pydonut._pydonut import SceneCamera
from pydonut._pydonut import PerspectiveCamera
from pydonut._pydonut import LightEditor
from pydonut._pydonut import MaterialEditor
from pydonut._pydonut import SceneGraphAnimation
from pydonut._pydonut import SceneGraphNode
from pydonut._pydonut import SceneGraph
from pydonut._pydonut import Scene
from pydonut._pydonut import SceneLoadingStats
from pydonut._pydonut import SceneLoaded
from pydonut._pydonut import BaseCamera
from pydonut._pydonut import FirstPersonCamera
from pydonut._pydonut import ThirdPersonCamera
from pydonut._pydonut import SwitchableCamera
from pydonut._pydonut import ICompositeView
from pydonut._pydonut import IView
from pydonut._pydonut import PlanarView
from pydonut._pydonut import StereoPlanarView
from pydonut._pydonut import CubemapView
from pydonut._pydonut import IDrawStrategy
from pydonut._pydonut import IGeometryPass
from pydonut._pydonut import GeometryPassContext
from pydonut._pydonut import GBufferRenderTargets
from pydonut._pydonut import GBufferFillPassCreateParameters
from pydonut._pydonut import GBufferFillPassContext
from pydonut._pydonut import GBufferFillPass
from pydonut._pydonut import MaterialIDPass
from pydonut._pydonut import PixelReadbackPass
from pydonut._pydonut import DepthPassCreateParameters
from pydonut._pydonut import DepthPassContext
from pydonut._pydonut import DepthPass
from pydonut._pydonut import PassthroughDrawStrategy
from pydonut._pydonut import InstancedOpaqueDrawStrategy
from pydonut._pydonut import TransparentDrawStrategy
from pydonut._pydonut import DeferredLightingPassInputs
from pydonut._pydonut import DeferredLightingPass
from pydonut._pydonut import ForwardShadingPassCreateParameters
from pydonut._pydonut import ForwardShadingPassContext
from pydonut._pydonut import ForwardShadingPass
from pydonut._pydonut import TemporalAntiAliasingJitter
from pydonut._pydonut import TemporalAntiAliasingParameters
from pydonut._pydonut import TemporalAntiAliasingCreateParameters
from pydonut._pydonut import TemporalAntiAliasingPass
from pydonut._pydonut import SkyParameters
from pydonut._pydonut import SkyPass
from pydonut._pydonut import SsaoParameters
from pydonut._pydonut import SsaoPass
from pydonut._pydonut import MipMapGenPassMode
from pydonut._pydonut import MipMapGenPass
from pydonut._pydonut import LightProbeProcessingPass
from pydonut._pydonut import ToneMappingParameters
from pydonut._pydonut import ToneMappingPassCreateParameters
from pydonut._pydonut import ToneMappingPass
from pydonut._pydonut import BloomPass
from pydonut._pydonut import CascadedShadowMap
from pydonut._pydonut import FramebufferFactory
from pydonut._pydonut import RenderView
from pydonut._pydonut import RenderCompositeView
from pydonut._pydonut import SaveTextureToFile
from pydonut._pydonut import FileDialog
from pydonut._pydonut import AdapterInfo
from pydonut._pydonut import IRenderPass
from pydonut._pydonut import ApplicationBase
from pydonut._pydonut import ImGui_Renderer
from pydonut._pydonut import ImGui
from pydonut._pydonut import PipelineCallbacks
from pydonut._pydonut import DeviceManager
from pydonut._pydonut import DeviceCreationParameters
from pydonut._pydonut import GetGraphicsAPIFromCommandLine
from pydonut._pydonut import GetDirectoryWithExecutable
from pydonut._pydonut import GetShaderTypeName
from pydonut._pydonut import FindScenes
from pydonut._pydonut import FindPreferredScene
from pydonut._pydonut import AFTERMATH_AVAILABLE
from pydonut._pydonut import DestroyBufferMemory_UnsafeForCrashTesting
from pydonut._pydonut import ClearColorAttachment
from pydonut._pydonut import ClearDepthStencilAttachment
from pydonut._pydonut import BuildBottomLevelAccelStruct
from pydonut._pydonut import BuildSceneAccelStructs
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

try:
    # Only present in Windows/D3D12 builds (NVRHI_WITH_DX12) -- a prototype interop class,
    # not part of the stable API.
    from pydonut._pydonut import D3D12WorkGraphPipeline
except ImportError:
    D3D12WorkGraphPipeline = None

__all__ = (
    'GraphicsAPI',
    'Format',
    'LogSeverity',
    'ShaderType',
    'PrimitiveType',
    'ComparisonFunc',
    'RasterCullMode',
    'CommandQueue',
    'CpuAccessMode',
    'Feature',
    'ResourceStates',
    'TextureDimension',
    'VariableShadingRate',
    'ShadingRateCombiner',
    'GeometryFlags',
    'AccelStructBuildFlags',
    'InstanceFlags',
    'ShaderSpecialization',
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
    'GeometryAABB',
    'GeometryAABBs',
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
    'TimerQuery',
    'ShaderLibrary',
    'InputLayout',
    'GraphicsPipeline',
    'MeshletPipeline',
    'ComputePipeline',
    'RayTracingPipeline',
    'ShaderTable',
    'CommandListParameters',
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
    'BlitParameters',
    'CommonRenderPasses',
    'DescriptorHandle',
    'DescriptorTableManager',
    'TextureCache',
    'LoadedTexture',
    'VertexAttribute',
    'BufferGroup',
    'MaterialDomain',
    'Material',
    'CreateMaterialConstantBuffer',
    'MeshGeometry',
    'MeshInfo',
    'SceneGraphLeaf',
    'MeshInstance',
    'SkinnedMeshInstance',
    'IShadowMap',
    'Light',
    'DirectionalLight',
    'SpotLight',
    'PointLight',
    'LightProbe',
    'SceneCamera',
    'PerspectiveCamera',
    'LightEditor',
    'MaterialEditor',
    'SceneGraphAnimation',
    'SceneGraphNode',
    'SceneGraph',
    'Scene',
    'SceneLoadingStats',
    'SceneLoaded',
    'BaseCamera',
    'FirstPersonCamera',
    'ThirdPersonCamera',
    'SwitchableCamera',
    'ICompositeView',
    'IView',
    'PlanarView',
    'StereoPlanarView',
    'CubemapView',
    'IDrawStrategy',
    'IGeometryPass',
    'GeometryPassContext',
    'GBufferRenderTargets',
    'GBufferFillPassCreateParameters',
    'GBufferFillPassContext',
    'GBufferFillPass',
    'MaterialIDPass',
    'PixelReadbackPass',
    'DepthPassCreateParameters',
    'DepthPassContext',
    'DepthPass',
    'PassthroughDrawStrategy',
    'InstancedOpaqueDrawStrategy',
    'TransparentDrawStrategy',
    'DeferredLightingPassInputs',
    'DeferredLightingPass',
    'ForwardShadingPassCreateParameters',
    'ForwardShadingPassContext',
    'ForwardShadingPass',
    'TemporalAntiAliasingJitter',
    'TemporalAntiAliasingParameters',
    'TemporalAntiAliasingCreateParameters',
    'TemporalAntiAliasingPass',
    'SkyParameters',
    'SkyPass',
    'SsaoParameters',
    'SsaoPass',
    'MipMapGenPassMode',
    'MipMapGenPass',
    'LightProbeProcessingPass',
    'ToneMappingParameters',
    'ToneMappingPassCreateParameters',
    'ToneMappingPass',
    'BloomPass',
    'CascadedShadowMap',
    'FramebufferFactory',
    'RenderView',
    'RenderCompositeView',
    'SaveTextureToFile',
    'FileDialog',
    'AdapterInfo',
    'IRenderPass',
    'ApplicationBase',
    'ImGui_Renderer',
    'ImGui',
    'PipelineCallbacks',
    'DeviceManager',
    'DeviceCreationParameters',
    'GetGraphicsAPIFromCommandLine',
    'GetDirectoryWithExecutable',
    'GetShaderTypeName',
    'FindScenes',
    'FindPreferredScene',
    'AFTERMATH_AVAILABLE',
    'DestroyBufferMemory_UnsafeForCrashTesting',
    'ClearColorAttachment',
    'ClearDepthStencilAttachment',
    'BuildBottomLevelAccelStruct',
    'BuildSceneAccelStructs',
    'CreateVolatileConstantBufferDesc',
    'CreateStaticConstantBufferDesc',
    'ComputeRotatingViewProjMatrix',
    'CreateBindingSetAndLayout',
    'log',
    'CompileShader',
    'CompileShaderLibrary',
    'D3D12WorkGraphPipeline',
)
