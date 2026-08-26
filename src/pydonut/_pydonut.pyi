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

from enum import Enum, IntFlag
from pathlib import Path
from typing import Callable, Optional, overload

class GraphicsAPI(Enum):
    D3D11 = 0
    D3D12 = 1
    Vulkan = 2

class Format(Enum):
    UNKNOWN = 0
    R8_UINT = 1
    R8_SINT = 2
    R8_UNORM = 3
    R8_SNORM = 4
    RG8_UINT = 5
    RG8_SINT = 6
    RG8_UNORM = 7
    RG8_SNORM = 8
    R16_UINT = 9
    R16_SINT = 10
    R16_UNORM = 11
    R16_SNORM = 12
    R16_FLOAT = 13
    BGRA4_UNORM = 14
    B5G6R5_UNORM = 15
    B5G5R5A1_UNORM = 16
    RGBA8_UINT = 17
    RGBA8_SINT = 18
    RGBA8_UNORM = 19
    RGBA8_SNORM = 20
    BGRA8_UNORM = 21
    BGRX8_UNORM = 22
    SRGBA8_UNORM = 23
    SBGRA8_UNORM = 24
    SBGRX8_UNORM = 25
    R10G10B10A2_UNORM = 26
    R11G11B10_FLOAT = 27
    RG16_UINT = 28
    RG16_SINT = 29
    RG16_UNORM = 30
    RG16_SNORM = 31
    RG16_FLOAT = 32
    R32_UINT = 33
    R32_SINT = 34
    R32_FLOAT = 35
    RGBA16_UINT = 36
    RGBA16_SINT = 37
    RGBA16_FLOAT = 38
    RGBA16_UNORM = 39
    RGBA16_SNORM = 40
    RG32_UINT = 41
    RG32_SINT = 42
    RG32_FLOAT = 43
    RGB32_UINT = 44
    RGB32_SINT = 45
    RGB32_FLOAT = 46
    RGBA32_UINT = 47
    RGBA32_SINT = 48
    RGBA32_FLOAT = 49
    D16 = 50
    D24S8 = 51
    X24G8_UINT = 52
    D32 = 53
    D32S8 = 54
    X32G8_UINT = 55
    BC1_UNORM = 56
    BC1_UNORM_SRGB = 57
    BC2_UNORM = 58
    BC2_UNORM_SRGB = 59
    BC3_UNORM = 60
    BC3_UNORM_SRGB = 61
    BC4_UNORM = 62
    BC4_SNORM = 63
    BC5_UNORM = 64
    BC5_SNORM = 65
    BC6H_UFLOAT = 66
    BC6H_SFLOAT = 67
    BC7_UNORM = 68
    BC7_UNORM_SRGB = 69
    COUNT = 70

class LogSeverity(Enum):
    None_ = 0
    Debug = 1
    Info = 2
    Warning = 3
    Error = 4
    Fatal = 5

class ShaderType(Enum):
    None_ = 0x0000
    Compute = 0x0020
    Vertex = 0x0001
    Hull = 0x0002
    Domain = 0x0004
    Geometry = 0x0008
    Pixel = 0x0010
    Amplification = 0x0040
    Mesh = 0x0080
    AllGraphics = 0x00DF
    RayGeneration = 0x0100
    AnyHit = 0x0200
    ClosestHit = 0x0400
    Miss = 0x0800
    Intersection = 0x1000
    Callable = 0x2000
    AllRayTracing = 0x3F00
    All = 0x3FFF

class PrimitiveType(Enum):
    PointList = 0
    LineList = 1
    LineStrip = 2
    TriangleList = 3
    TriangleStrip = 4
    TriangleFan = 5
    TriangleListWithAdjacency = 6
    TriangleStripWithAdjacency = 7
    PatchList = 8

class ComparisonFunc(Enum):
    Never = 1
    Less = 2
    Equal = 3
    LessOrEqual = 4
    Greater = 5
    NotEqual = 6
    GreaterOrEqual = 7
    Always = 8

class RasterCullMode(Enum):
    Back = 0
    Front = 1
    None_ = 2

class CommandQueue(Enum):
    Graphics = 0
    Compute = 1
    Copy = 2

class CpuAccessMode(Enum):
    None_ = 0
    Read = 1
    Write = 2

class Feature(Enum):
    ComputeQueue = 0
    ConservativeRasterization = 1
    ConstantBufferRanges = 2
    CopyQueue = 3
    DeferredCommandLists = 4
    FastGeometryShader = 5
    HeapDirectlyIndexed = 6
    HlslExtensionUAV = 7
    LinearSweptSpheres = 8
    Meshlets = 9
    RayQuery = 10
    RayTracingAccelStruct = 11
    RayTracingClusters = 12
    RayTracingOpacityMicromap = 13
    RayTracingPipeline = 14
    SamplerFeedback = 15
    ShaderExecutionReordering = 16
    ShaderSpecializations = 17
    SinglePassStereo = 18
    Spheres = 19
    VariableRateShading = 20
    VirtualResources = 21
    WaveLaneCountMinMax = 22
    CooperativeVectorInferencing = 23
    CooperativeVectorTraining = 24
    EnhancedBarriers = 25

class ResourceStates(IntFlag):
    Unknown = 0x00000000
    Common = 0x00000001
    ConstantBuffer = 0x00000002
    VertexBuffer = 0x00000004
    IndexBuffer = 0x00000008
    IndirectArgument = 0x00000010
    PixelShaderResource = 0x00000020
    NonPixelShaderResource = 0x00000040
    ShaderResource = 0x00000060
    UnorderedAccess = 0x00000080
    RenderTarget = 0x00000100
    DepthWrite = 0x00000200
    DepthRead = 0x00000400
    StreamOut = 0x00000800
    CopyDest = 0x00001000
    CopySource = 0x00002000
    ResolveDest = 0x00004000
    ResolveSource = 0x00008000
    Present = 0x00010000
    AccelStructRead = 0x00020000
    AccelStructWrite = 0x00040000
    AccelStructBuildInput = 0x00080000
    AccelStructBuildBlas = 0x00100000
    ShadingRateSurface = 0x00200000
    OpacityMicromapWrite = 0x00400000
    OpacityMicromapBuildInput = 0x00800000
    ConvertCoopVecMatrixInput = 0x01000000
    ConvertCoopVecMatrixOutput = 0x02000000

class TextureDimension(Enum):
    Unknown = 0
    Texture1D = 1
    Texture1DArray = 2
    Texture2D = 3
    Texture2DArray = 4
    TextureCube = 5
    TextureCubeArray = 6
    Texture2DMS = 7
    Texture2DMSArray = 8
    Texture3D = 9

class VariableShadingRate(Enum):
    e1x1 = 0
    e1x2 = 1
    e2x1 = 2
    e2x2 = 3
    e2x4 = 4
    e4x2 = 5
    e4x4 = 6

class ShadingRateCombiner(Enum):
    Passthrough = 0
    Override = 1
    Min = 2
    Max = 3
    ApplyRelative = 4

class GeometryFlags(Enum):
    None_ = 0
    Opaque = 1
    NoDuplicateAnyHitInvocation = 2

# Only the flag rt_particles.py actually sets (PreferFastTrace) plus None (the default) --
# matching the "only bind what's needed" convention used throughout.
class AccelStructBuildFlags(Enum):
    None_ = 0
    PreferFastTrace = 4

class InstanceFlags(Enum):
    None_ = 0
    TriangleCullDisable = 1
    TriangleFrontCounterclockwise = 2
    ForceOpaque = 4
    ForceNonOpaque = 8
    ForceOMM2State = 16
    DisableOMMs = 32

def GetGraphicsAPIFromCommandLine(args: list[str]) -> GraphicsAPI: ...
def GetDirectoryWithExecutable() -> Path: ...
def GetShaderTypeName(api: GraphicsAPI) -> str: ...
# True only in builds configured with -DPYDONUT_WITH_AFTERMATH=ON. When False,
# DeviceCreationParameters has no enableAftermath attribute and no crash dumps are written.
AFTERMATH_AVAILABLE: bool

# DELIBERATELY UNSAFE -- crash testing only. Destroys the native API memory backing `buffer`
# while the GPU may still be reading it, so the next draw page-faults. The device cannot be
# recovered afterwards. Raises RuntimeError on D3D11, which does not fault this way.
def DestroyBufferMemory_UnsafeForCrashTesting(device: Device, buffer: Buffer) -> None: ...

def ClearColorAttachment(commandList: CommandList, framebuffer: Framebuffer, attachmentIndex: int, color: Color) -> None: ...

class log():
    @staticmethod
    def SetMinSeverity(severity: LogSeverity) -> None: ...
    @staticmethod
    def SetCallback(callback: Callable[[LogSeverity, str], None]) -> None: ...
    @staticmethod
    def ResetCallback() -> None: ...
    @staticmethod
    def EnableOutputToMessageBox(enable: bool) -> None: ...
    @staticmethod
    def EnableOutputToConsole(enable: bool) -> None: ...
    @staticmethod
    def EnableOutputToDebug(enable: bool) -> None: ...
    @staticmethod
    def SetErrorMessageCaption(caption: str) -> None: ...
    @staticmethod
    def ConsoleApplicationMode() -> None: ...
    @staticmethod
    def message(severity: LogSeverity, message: str) -> None: ...
    @staticmethod
    def debug(message: str) -> None: ...
    @staticmethod
    def info(message: str) -> None: ...
    @staticmethod
    def warning(message: str) -> None: ...
    @staticmethod
    def error(message: str) -> None: ...
    # Aborts the process by default (Donut's DefaultCallback behavior) after logging;
    # install a custom callback via Log.SetCallback first if that's not desired.
    @staticmethod
    def fatal(message: str) -> None: ...

# In-process HLSL -> DXIL/SPIR-V compilation via DXC. Not available in every build
# (requires DXC to have been found at configure time); raises RuntimeError on a
# compile error, with DXC's diagnostic text as the message.
def CompileShader(
    source: str,
    entryPoint: str,
    shaderType: ShaderType,
    api: GraphicsAPI,
    sourceName: str = "shader.hlsl",
    shaderModel: str = "6_5",
    includePaths: list[str] = [],
    # Vulkan only: raises DXC's SPIR-V target env to vulkan1.2, needed for Wave Operations
    # (e.g. WaveActiveBitOr/WaveIsFirstLane). Leave False unless the shader actually uses them.
    requiresVulkan11: bool = False,
) -> bytes: ...

# Same as CompileShader, but for a shader library with multiple [shader("...")]-annotated
# exports (e.g. a DXR raygen/closesthit/miss set) instead of a single entry point. Feed the
# result to Device.createShaderLibrary.
def CompileShaderLibrary(
    source: str,
    api: GraphicsAPI,
    sourceName: str = "shader.hlsl",
    shaderModel: str = "6_5",
    includePaths: list[str] = [],
) -> bytes: ...

# D3D12 Work Graphs interop prototype. Only present in Windows/D3D12 builds. Builds the
# ID3D12StateObject for a single-library work graph; raises RuntimeError if the device/driver
# doesn't report D3D12_WORK_GRAPHS_TIER support, or if state object creation fails.
class D3D12WorkGraphPipeline:
    # broadcastEntryNodeName overrides that node's [NodeDispatchGrid()] attribute, which HLSL
    # can only express as a compile-time constant -- use it for grids sized from the viewport
    # (e.g. a tile count). Leave it empty to keep whatever the shader declared.
    def __init__(
        self,
        device: Device,
        shaderLibrary: ShaderLibrary,
        rootSigSourcePipeline: ComputePipeline,
        workGraphName: str,
        broadcastEntryNodeName: str = "",
        dispatchGridX: int = 1,
        dispatchGridY: int = 1,
        dispatchGridZ: int = 1,
    ) -> None: ...
    def getBackingMemorySize(self) -> int: ...

# One Vulkan spec-constant override (constantID declared in HLSL via [[vk::constant_id(N)]])
# for Device.createShaderSpecialization. Three static factories, matching the C++ API, since
# the active value depends on which one was used.
class ShaderSpecialization():
    @staticmethod
    def UInt32(constantID: int, value: int) -> ShaderSpecialization: ...
    @staticmethod
    def Int32(constantID: int, value: int) -> ShaderSpecialization: ...
    @staticmethod
    def Float(constantID: int, value: float) -> ShaderSpecialization: ...

class Color():
    r: float
    g: float
    b: float
    a: float
    @overload
    def __init__(self: Color) -> None: ...
    @overload
    def __init__(self: Color, c: float) -> None: ...
    @overload
    def __init__(self: Color, r: float, g: float, b: float, a: float) -> None: ...

class Viewport():
    minX: float
    maxX: float
    minY: float
    maxY: float
    minZ: float
    maxZ: float
    @overload
    def __init__(self: Viewport) -> None: ...
    @overload
    def __init__(self: Viewport, width: float, height: float) -> None: ...
    @overload
    def __init__(self: Viewport, minX: float, maxX: float, minY: float, maxY: float, minZ: float, maxZ: float) -> None: ...
    def width(self: Viewport) -> float: ...
    def height(self: Viewport) -> float: ...

class ViewportState():
    def __init__(self: ViewportState) -> None: ...
    def addViewportAndScissorRect(self: ViewportState, viewport: Viewport) -> None: ...

class FramebufferInfo():
    depthFormat: Format
    sampleCount: int
    sampleQuality: int
    width: int
    height: int
    arraySize: int
    def getViewport(self: FramebufferInfo, minZ: float = 0.0, maxZ: float = 1.0) -> Viewport: ...

class DepthStencilState():
    depthTestEnable: bool
    depthFunc: ComparisonFunc
    def __init__(self: DepthStencilState) -> None: ...

class RasterState():
    cullMode: RasterCullMode
    frontCounterClockwise: bool
    def __init__(self: RasterState) -> None: ...

class RenderState():
    depthStencilState: DepthStencilState
    rasterState: RasterState
    def __init__(self: RenderState) -> None: ...

class VertexAttributeDesc():
    name: str
    format: Format
    arraySize: int
    bufferIndex: int
    offset: int
    elementStride: int
    isInstanced: bool
    def __init__(self: VertexAttributeDesc) -> None: ...

class DrawArguments():
    vertexCount: int
    instanceCount: int
    startIndexLocation: int
    startVertexLocation: int
    startInstanceLocation: int
    def __init__(self: DrawArguments) -> None: ...

class GraphicsPipelineDesc():
    primType: PrimitiveType
    renderState: RenderState
    VS: Optional[Shader]
    PS: Optional[Shader]
    inputLayout: Optional[InputLayout]
    def __init__(self: GraphicsPipelineDesc) -> None: ...
    def addBindingLayout(self: GraphicsPipelineDesc, layout: BindingLayout) -> None: ...

class GraphicsState():
    viewport: ViewportState
    pipeline: Optional[GraphicsPipeline]
    framebuffer: Optional[Framebuffer]
    def __init__(self: GraphicsState) -> None: ...
    def addBindingSet(self: GraphicsState, bindingSet: BindingSet) -> None: ...
    # vertexBuffers is a fixed-capacity static_vector in nvrhi -- appended to via this method
    # rather than exposed as a plain read-write list.
    def addVertexBuffer(self: GraphicsState, buffer: Buffer, slot: int, offset: int = 0) -> None: ...
    def setIndexBuffer(self: GraphicsState, buffer: Buffer, format: Format, offset: int = 0) -> None: ...

class MeshletPipelineDesc():
    primType: PrimitiveType
    renderState: RenderState
    AS: Optional[Shader]
    MS: Optional[Shader]
    PS: Optional[Shader]
    def __init__(self: MeshletPipelineDesc) -> None: ...

class MeshletState():
    viewport: ViewportState
    pipeline: Optional[MeshletPipeline]
    framebuffer: Optional[Framebuffer]
    def __init__(self: MeshletState) -> None: ...

class VariableRateShadingState():
    enabled: bool
    shadingRate: VariableShadingRate
    pipelinePrimitiveCombiner: ShadingRateCombiner
    imageCombiner: ShadingRateCombiner
    def __init__(self: VariableRateShadingState) -> None: ...

class VariableRateShadingFeatureInfo():
    shadingRateImageTileSize: int

class ComputePipelineDesc():
    CS: Optional[Shader]
    def __init__(self: ComputePipelineDesc) -> None: ...
    def addBindingLayout(self: ComputePipelineDesc, layout: BindingLayout) -> None: ...

class ComputeState():
    pipeline: Optional[ComputePipeline]
    def __init__(self: ComputeState) -> None: ...
    def addBindingSet(self: ComputeState, bindingSet: BindingSet) -> None: ...

class BufferDesc():
    byteSize: int
    structStride: int
    maxVersions: int
    debugName: str
    format: Format
    canHaveUAVs: bool
    canHaveTypedViews: bool
    canHaveRawViews: bool
    isVertexBuffer: bool
    isIndexBuffer: bool
    isConstantBuffer: bool
    isDrawIndirectArgs: bool
    isAccelStructBuildInput: bool
    isAccelStructStorage: bool
    isShaderBindingTable: bool
    isVolatile: bool
    cpuAccess: CpuAccessMode
    initialState: ResourceStates
    keepInitialState: bool
    def __init__(self: BufferDesc) -> None: ...

class TextureDesc():
    width: int
    height: int
    depth: int
    arraySize: int
    mipLevels: int
    sampleCount: int
    format: Format
    debugName: str
    isShaderResource: bool
    isRenderTarget: bool
    isUAV: bool
    isTypeless: bool
    isShadingRateSurface: bool
    dimension: TextureDimension
    clearValue: Color
    useClearValue: bool
    initialState: ResourceStates
    keepInitialState: bool
    def __init__(self: TextureDesc) -> None: ...

class FramebufferAttachment():
    texture: Optional[Texture]

class FramebufferDesc():
    def __init__(self: FramebufferDesc) -> None: ...
    def getColorAttachment(self: FramebufferDesc, index: int) -> FramebufferAttachment: ...
    def addColorAttachment(self: FramebufferDesc, attachment: FramebufferAttachment) -> None: ...
    def setDepthAttachment(self: FramebufferDesc, texture: Texture) -> None: ...

# BindingLayoutItem/BindingSetItem are opaque -- Python only obtains instances through
# these static factories, matching how nvrhi's own C++ call sites construct them.
class BindingLayoutItem():
    @staticmethod
    def Texture_UAV(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def Texture_SRV(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def RawBuffer_SRV(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def StructuredBuffer_SRV(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def TypedBuffer_SRV(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def TypedBuffer_UAV(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def StructuredBuffer_UAV(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def PushConstants(slot: int, byteSize: int) -> BindingLayoutItem: ...
    @staticmethod
    def ConstantBuffer(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def VolatileConstantBuffer(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def Sampler(slot: int) -> BindingLayoutItem: ...
    @staticmethod
    def RayTracingAccelStruct(slot: int) -> BindingLayoutItem: ...

class BindingLayoutDesc():
    visibility: ShaderType
    # 0 (default) unless the layout needs a non-zero register space -- e.g. a per-hit-group
    # "local" root signature space in a ray tracing pipeline that also has a "global" space at 0.
    registerSpace: int
    bindings: list[BindingLayoutItem]
    def __init__(self: BindingLayoutDesc) -> None: ...

class BufferRange():
    byteOffset: int
    byteSize: int
    @overload
    def __init__(self: BufferRange) -> None: ...
    @overload
    def __init__(self: BufferRange, byteOffset: int, byteSize: int) -> None: ...

class BindingSetItem():
    @overload
    @staticmethod
    def Texture_UAV(slot: int, texture: Texture) -> BindingSetItem: ...
    # Overload with an explicit format, for typed UAV/SRV views that override the texture's
    # own (possibly typeless) format -- e.g. a shading-rate surface.
    @overload
    @staticmethod
    def Texture_UAV(slot: int, texture: Texture, format: Format) -> BindingSetItem: ...
    @overload
    @staticmethod
    def Texture_SRV(slot: int, texture: Texture) -> BindingSetItem: ...
    @overload
    @staticmethod
    def Texture_SRV(slot: int, texture: Texture, format: Format) -> BindingSetItem: ...
    @staticmethod
    def RayTracingAccelStruct(slot: int, accelStruct: AccelStruct) -> BindingSetItem: ...
    @overload
    @staticmethod
    def ConstantBuffer(slot: int, buffer: Buffer) -> BindingSetItem: ...
    # Binds one `range` slice of `buffer` -- e.g. one entry of an array of same-sized
    # constant buffer structs packed into a single larger buffer.
    @overload
    @staticmethod
    def ConstantBuffer(slot: int, buffer: Buffer, range: BufferRange) -> BindingSetItem: ...
    @staticmethod
    def StructuredBuffer_SRV(slot: int, buffer: Buffer) -> BindingSetItem: ...
    # Registers a ByteAddressBuffer SRV in the bindless descriptor table (see
    # DescriptorTableManager.CreateDescriptorHandle) -- rt_particles.py uses this for its
    # dynamic particle index/vertex buffers.
    @staticmethod
    def RawBuffer_SRV(slot: int, buffer: Buffer) -> BindingSetItem: ...
    @overload
    @staticmethod
    def TypedBuffer_SRV(slot: int, buffer: Buffer) -> BindingSetItem: ...
    # Overload with an explicit format and byte range, for viewing one slice of a larger buffer
    # through a specific typed format -- e.g. one mesh's slice of a shared index/vertex buffer.
    @overload
    @staticmethod
    def TypedBuffer_SRV(slot: int, buffer: Buffer, format: Format, range: BufferRange) -> BindingSetItem: ...
    @staticmethod
    def TypedBuffer_UAV(slot: int, buffer: Buffer) -> BindingSetItem: ...
    @staticmethod
    def StructuredBuffer_UAV(slot: int, buffer: Buffer) -> BindingSetItem: ...
    @staticmethod
    def Sampler(slot: int, sampler: Sampler) -> BindingSetItem: ...
    @staticmethod
    def PushConstants(slot: int, byteSize: int) -> BindingSetItem: ...

class BindingSetDesc():
    bindings: list[BindingSetItem]
    def __init__(self: BindingSetDesc) -> None: ...

# BindlessLayoutDesc.registerSpaces reuses BindingLayoutItem, but its slot argument means
# "register space index" here rather than a binding slot -- e.g. RawBuffer_SRV(1) assigns
# space 1 to a ByteAddressBuffer descriptor array.
class BindlessLayoutDesc():
    visibility: ShaderType
    firstSlot: int
    maxCapacity: int
    def __init__(self: BindlessLayoutDesc) -> None: ...
    def addRegisterSpace(self: BindlessLayoutDesc, item: BindingLayoutItem) -> None: ...

def CreateVolatileConstantBufferDesc(byteSize: int, debugName: str, maxVersions: int) -> BufferDesc: ...
def CreateStaticConstantBufferDesc(byteSize: int, debugName: str) -> BufferDesc: ...
def CreateBindingSetAndLayout(device: Device, visibility: ShaderType, registerSpace: int, bindingSetDesc: BindingSetDesc) -> tuple[BindingLayout, BindingSet]: ...
def ClearDepthStencilAttachment(commandList: CommandList, framebuffer: Framebuffer, depth: float, stencil: int) -> None: ...

class GeometryTriangles():
    indexBuffer: Optional[Buffer]
    vertexBuffer: Optional[Buffer]
    indexFormat: Format
    vertexFormat: Format
    # Byte offsets into indexBuffer/vertexBuffer -- 0 (default) for a geometry that owns its
    # whole buffer; non-zero when several geometries/meshes share one buffer.
    indexOffset: int
    vertexOffset: int
    indexCount: int
    vertexCount: int
    vertexStride: int
    def __init__(self: GeometryTriangles) -> None: ...

# Axis-aligned box geometry for procedural/intersection-shader primitives (e.g. the
# ray-traced particle billboards in rt_particles.py, which intersect an analytic quad
# inside a unit AABB rather than real triangles).
class GeometryAABB():
    minX: float
    minY: float
    minZ: float
    maxX: float
    maxY: float
    maxZ: float
    def __init__(self: GeometryAABB) -> None: ...

class GeometryAABBs():
    def __init__(self: GeometryAABBs) -> None: ...
    def setBuffer(self: GeometryAABBs, buffer: Buffer) -> GeometryAABBs: ...
    def setCount(self: GeometryAABBs, count: int) -> GeometryAABBs: ...

class GeometryDesc():
    flags: GeometryFlags
    def __init__(self: GeometryDesc) -> None: ...
    def setTriangles(self: GeometryDesc, triangles: GeometryTriangles) -> None: ...
    def setAABBs(self: GeometryDesc, aabbs: GeometryAABBs) -> None: ...

class AccelStructDesc():
    debugName: str
    buildFlags: AccelStructBuildFlags
    isTopLevel: bool
    topLevelMaxInstances: int
    bottomLevelGeometries: list[GeometryDesc]
    def __init__(self: AccelStructDesc) -> None: ...

# InstanceDesc packs bitfields + a union, so it's mutated through setter methods rather
# than plain properties. The default constructor already fills in the identity transform.
class InstanceDesc():
    def __init__(self: InstanceDesc) -> None: ...
    def setInstanceMask(self: InstanceDesc, value: int) -> None: ...
    def setInstanceID(self: InstanceDesc, value: int) -> None: ...
    def setInstanceContributionToHitGroupIndex(self: InstanceDesc, value: int) -> None: ...
    def setFlags(self: InstanceDesc, value: InstanceFlags) -> None: ...
    def setBLAS(self: InstanceDesc, value: AccelStruct) -> None: ...
    # Fills the row-major instance transform from a scene graph node's world transform --
    # math types aren't exposed to Python, so this hides the conversion behind one call.
    def setTransformFromNode(self: InstanceDesc, node: SceneGraphNode) -> None: ...
    # Fills the row-major instance transform as scale-then-translate, for instances with no
    # scene graph node of their own (e.g. rt_particles.py's one intersection-BLAS instance per
    # particle, scaled to its radius and translated to its position).
    def setTransformScaleTranslation(self: InstanceDesc, sx: float, sy: float, sz: float, tx: float, ty: float, tz: float) -> None: ...

class PipelineShaderDesc():
    def __init__(self: PipelineShaderDesc) -> None: ...
    def setShader(self: PipelineShaderDesc, shader: Shader) -> None: ...

class PipelineHitGroupDesc():
    def __init__(self: PipelineHitGroupDesc) -> None: ...
    def setExportName(self: PipelineHitGroupDesc, value: str) -> None: ...
    def setClosestHitShader(self: PipelineHitGroupDesc, shader: Shader) -> None: ...
    # A "local" binding layout for this hit group specifically, distinct from the pipeline's
    # global binding layout(s) -- e.g. per-geometry material bindings.
    def setBindingLayout(self: PipelineHitGroupDesc, layout: BindingLayout) -> None: ...

class RayTracingPipelineDesc():
    maxPayloadSize: int
    # Default 1 (no recursive TraceRay calls). Raise when a closest-hit/any-hit shader itself
    # calls TraceRay (e.g. tracing a shadow or reflection ray from within a hit shader).
    maxRecursionDepth: int
    def __init__(self: RayTracingPipelineDesc) -> None: ...
    def addShader(self: RayTracingPipelineDesc, shader: PipelineShaderDesc) -> None: ...
    def addHitGroup(self: RayTracingPipelineDesc, hitGroup: PipelineHitGroupDesc) -> None: ...
    def addBindingLayout(self: RayTracingPipelineDesc, layout: BindingLayout) -> None: ...

class RayTracingState():
    shaderTable: Optional[ShaderTable]
    def __init__(self: RayTracingState) -> None: ...
    def addBindingSet(self: RayTracingState, bindingSet: BindingSet) -> None: ...

class DispatchRaysArguments():
    width: int
    height: int
    depth: int
    def __init__(self: DispatchRaysArguments) -> None: ...

# Swap-chain resources: owned by the DeviceManager, never constructible from Python.
class Framebuffer():
    def getFramebufferInfo(self: Framebuffer) -> FramebufferInfo: ...
    def getDesc(self: Framebuffer) -> FramebufferDesc: ...

# Texture wraps both borrowed (swap-chain) and owned (Device.createTexture) instances.
class Texture():
    def getDesc(self: Texture) -> TextureDesc: ...

# Objects created through Device / ShaderFactory factory calls.
class Shader(): ...
class TimerQuery(): ...
class ShaderLibrary():
    def getShader(self: ShaderLibrary, entryName: str, shaderType: ShaderType) -> Optional[Shader]: ...
class InputLayout(): ...
class GraphicsPipeline(): ...
class MeshletPipeline(): ...
class ComputePipeline(): ...
class RayTracingPipeline():
    def createShaderTable(self: RayTracingPipeline) -> ShaderTable: ...
class ShaderTable():
    def setRayGenerationShader(self: ShaderTable, exportName: str, bindings: Optional[BindingSet] = None) -> None: ...
    def addHitGroup(self: ShaderTable, exportName: str, bindings: Optional[BindingSet] = None) -> int: ...
    def addMissShader(self: ShaderTable, exportName: str, bindings: Optional[BindingSet] = None) -> int: ...
class CommandListParameters():
    def __init__(self: CommandListParameters) -> None: ...
    # False (deferred) means the command list is recorded but not auto-submitted -- required
    # for command lists recorded on a thread other than the one that submits them.
    def setEnableImmediateExecution(self: CommandListParameters, value: bool) -> CommandListParameters: ...

class CommandList():
    def open(self: CommandList) -> None: ...
    def close(self: CommandList) -> None: ...
    def setGraphicsState(self: CommandList, state: GraphicsState) -> None: ...
    def draw(self: CommandList, args: DrawArguments) -> None: ...
    def drawIndexed(self: CommandList, args: DrawArguments) -> None: ...
    def setMeshletState(self: CommandList, state: MeshletState) -> None: ...
    def dispatchMesh(self: CommandList, groupsX: int, groupsY: int = 1, groupsZ: int = 1) -> None: ...
    def setComputeState(self: CommandList, state: ComputeState) -> None: ...
    def dispatch(self: CommandList, groupsX: int, groupsY: int = 1, groupsZ: int = 1) -> None: ...
    def writeBuffer(self: CommandList, buffer: Buffer, data: bytes, destOffsetBytes: int = 0) -> None: ...
    def copyBuffer(self: CommandList, dest: Buffer, destOffsetBytes: int, src: Buffer, srcOffsetBytes: int, dataSizeBytes: int) -> None: ...
    # Whole-resource texture-to-texture copy (plain byte copy, no shader/tonemap) -- unlike
    # CommonRenderPasses.BlitTexture, which samples through a shader.
    def copyTexture(self: CommandList, dest: Texture, src: Texture) -> None: ...
    # D3D12 Work Graphs interop prototype. Only present in Windows/D3D12 builds. Sets the
    # given work graph as the active program (initializing its backing memory on first use)
    # and dispatches it with a single, zero-size input record at entry point 0.
    # Note: nvrhi's cached compute state does not track this call; a subsequent setComputeState
    # with the same pipeline object will not re-bind it at the D3D12 level.
    def dispatchWorkGraph(
        self,
        pipeline: D3D12WorkGraphPipeline,
        backingMemoryBuffer: Buffer,
        initialize: bool,
        numRecords: int = 1,
    ) -> None: ...
    def buildTopLevelAccelStruct(self: CommandList, as_: AccelStruct, instances: list[InstanceDesc]) -> None: ...
    def setRayTracingState(self: CommandList, state: RayTracingState) -> None: ...
    def dispatchRays(self: CommandList, args: DispatchRaysArguments) -> None: ...
    def setPushConstants(self: CommandList, data: bytes) -> None: ...
    @overload
    def clearTextureFloat(self: CommandList, texture: Texture, clearColor: Color) -> None: ...
    # View-scoped: clears only the subresources `view` covers (e.g. one face of a shared cube
    # texture) instead of every subresource.
    @overload
    def clearTextureFloat(self: CommandList, texture: Texture, clearColor: Color, view: PlanarView) -> None: ...
    @overload
    def clearDepthStencilTexture(self: CommandList, texture: Texture, clearDepth: bool, depth: float, clearStencil: bool, stencil: int) -> None: ...
    @overload
    def clearDepthStencilTexture(self: CommandList, texture: Texture, clearDepth: bool, depth: float, clearStencil: bool, stencil: int, view: PlanarView) -> None: ...
    # Debug marker range, nestable; each beginMarker needs a matching endMarker. Names the
    # faulting scope in an NSight Aftermath crash dump.
    def beginMarker(self: CommandList, name: str) -> None: ...
    def endMarker(self: CommandList) -> None: ...
    # Resolves mip 0 / array slice 0 only; nvrhi::TextureSubresourceSet is not exposed to
    # Python, matching clearTextureFloat and clearDepthStencilTexture.
    def resolveTexture(self: CommandList, dest: Texture, src: Texture) -> None: ...
    # Disables nvrhi's automatic per-command-list resource-state tracking, needed when several
    # command lists are recorded concurrently against one shared resource. Pair with
    # setResourceStatesForFramebuffer + commitBarriers, then re-enable when done.
    def setEnableAutomaticBarriers(self: CommandList, enable: bool) -> None: ...
    def setResourceStatesForFramebuffer(self: CommandList, framebuffer: Framebuffer) -> None: ...
    # Explicit state transitions for resources nvrhi's automatic tracking wouldn't otherwise
    # catch in time -- e.g. a skinned mesh's vertex buffer/BLAS between the skinning compute
    # dispatch that just wrote new positions and the BLAS rebuild that reads them this same
    # frame (see rt_bindless.py's BuildTLAS, matching the C++ original's per-frame skinned BLAS
    # update). commitBarriers submits the resulting barriers.
    def setBufferState(self: CommandList, buffer: Buffer, stateBits: ResourceStates) -> None: ...
    def setAccelStructState(self: CommandList, as_: AccelStruct, stateBits: ResourceStates) -> None: ...
    def commitBarriers(self: CommandList) -> None: ...
    def beginTimerQuery(self: CommandList, query: TimerQuery) -> None: ...
    def endTimerQuery(self: CommandList, query: TimerQuery) -> None: ...
class Buffer(): ...
class BindingLayout(): ...
class BindingSet(): ...
class Sampler(): ...
class AccelStruct(): ...

class Device():
    def getGraphicsAPI(self: Device) -> GraphicsAPI: ...
    def createCommandList(self: Device, params: CommandListParameters = CommandListParameters()) -> CommandList: ...
    def createGraphicsPipeline(self: Device, desc: GraphicsPipelineDesc, framebufferInfo: FramebufferInfo) -> GraphicsPipeline: ...
    def createMeshletPipeline(self: Device, desc: MeshletPipelineDesc, framebufferInfo: FramebufferInfo) -> MeshletPipeline: ...
    def executeCommandList(self: Device, commandList: CommandList, executionQueue: CommandQueue = CommandQueue.Graphics) -> int: ...
    # Batched, atomic submission of multiple command lists in one call (e.g. several per-thread
    # command lists plus a composite one), as opposed to executeCommandList's one-at-a-time
    # submission.
    def executeCommandLists(self: Device, commandLists: list[CommandList], executionQueue: CommandQueue = CommandQueue.Graphics) -> int: ...
    def createShader(self: Device, bytecode: bytes, entryName: str, shaderType: ShaderType) -> Optional[Shader]: ...
    # Vulkan-only (nvrhi::Feature.ShaderSpecializations): bakes spec-constant overrides into a
    # new shader derived from baseShader.
    def createShaderSpecialization(self: Device, baseShader: Shader, constants: list[ShaderSpecialization]) -> Optional[Shader]: ...
    def queryFeatureSupport(self: Device, feature: Feature) -> bool: ...
    def createBuffer(self: Device, desc: BufferDesc) -> Buffer: ...
    # Combinator wrapping mapBuffer(Read)+memcpy+unmapBuffer into one safe call -- raw mapped
    # pointers are never exposed to Python. `buffer` must have been created with
    # cpuAccess=Read (or Write) and byteSize must not exceed its actual size.
    def readBuffer(self: Device, buffer: Buffer, byteSize: int) -> bytes: ...
    def createTexture(self: Device, desc: TextureDesc) -> Texture: ...
    def createFramebuffer(self: Device, desc: FramebufferDesc) -> Framebuffer: ...
    def createBindingLayout(self: Device, desc: BindingLayoutDesc) -> BindingLayout: ...
    def createBindingSet(self: Device, desc: BindingSetDesc, layout: BindingLayout) -> BindingSet: ...
    def createBindlessLayout(self: Device, desc: BindlessLayoutDesc) -> BindingLayout: ...
    def createInputLayout(self: Device, attributes: list[VertexAttributeDesc], vertexShader: Shader) -> InputLayout: ...
    def createComputePipeline(self: Device, desc: ComputePipelineDesc) -> ComputePipeline: ...
    # Wraps the queryFeatureSupport(Feature, void*, size_t) overload for VariableRateShading
    # specifically, which reports the hardware's shading-rate-image tile size.
    def queryVariableRateShadingInfo(self: Device) -> VariableRateShadingFeatureInfo: ...
    def createAccelStruct(self: Device, desc: AccelStructDesc) -> AccelStruct: ...
    def createRayTracingPipeline(self: Device, desc: RayTracingPipelineDesc) -> RayTracingPipeline: ...
    def createShaderLibrary(self: Device, bytecode: bytes) -> Optional[ShaderLibrary]: ...
    def waitForIdle(self: Device) -> None: ...
    def createTimerQuery(self: Device) -> TimerQuery: ...
    # Non-blocking: true once the query's result is ready to read.
    def pollTimerQuery(self: Device, query: TimerQuery) -> bool: ...
    # Elapsed time in seconds. Only valid after pollTimerQuery(query) returns True.
    def getTimerQueryTime(self: Device, query: TimerQuery) -> float: ...
    def resetTimerQuery(self: Device, query: TimerQuery) -> None: ...

def BuildBottomLevelAccelStruct(commandList: CommandList, as_: AccelStruct, desc: AccelStructDesc) -> None: ...

# Builds one BLAS per scene mesh and the scene's TLAS (one instance per MeshInstance,
# transformed by its node's world transform) in one call, returning just the finished TLAS --
# wraps the whole per-mesh/per-geometry/per-instance traversal rather than exposing it to
# Python (matches the existing convention of wrapping multi-step C++ procedures behind one
# call, see SceneLoaded()/CreateMaterialConstantBuffer()).
def BuildSceneAccelStructs(device: Device, commandList: CommandList, scene: Scene) -> AccelStruct: ...

class IFileSystem(): ...
class NativeFileSystem(IFileSystem):
    def __init__(self: NativeFileSystem) -> None: ...
class RootFileSystem(IFileSystem):
    def __init__(self: RootFileSystem) -> None: ...
    def mount(self: RootFileSystem, path: Path, nativePath: Path) -> None: ...

class ShaderFactory():
    def __init__(self: ShaderFactory, device: Device, fs: IFileSystem, basePath: Path) -> None: ...
    def CreateShader(self: ShaderFactory, fileName: str, entryName: str, shaderType: ShaderType) -> Optional[Shader]: ...
    def CreateShaderLibrary(self: ShaderFactory, fileName: str) -> Optional[ShaderLibrary]: ...
    # Drops the bytecode cache, so shaders created after it re-read their .bin blobs from
    # disk. Recreating the passes that hold the already-compiled pipelines is the caller's
    # job -- see feature_demo.py's ReloadShaders.
    def ClearCache(self: ShaderFactory) -> None: ...

class BindingCache():
    def __init__(self: BindingCache, device: Device) -> None: ...
    def Clear(self: BindingCache) -> None: ...

# Only the fields threaded_rendering.py needs are bound (targetBox/sourceBox/sourceMip/
# sourceFormat/sampler/blendState/blendConstantColor stay at their defaults).
class BlitParameters():
    def __init__(self: BlitParameters) -> None: ...
    targetFramebuffer: Optional[Framebuffer]
    targetViewport: Viewport
    sourceTexture: Optional[Texture]
    sourceArraySlice: int

class CommonRenderPasses():
    def __init__(self: CommonRenderPasses, device: Device, shaderFactory: ShaderFactory) -> None: ...
    @overload
    def BlitTexture(self: CommonRenderPasses, commandList: CommandList, targetFramebuffer: Framebuffer, sourceTexture: Texture, bindingCache: Optional[BindingCache] = None) -> None: ...
    # BlitParameters overload: composites one source array slice into one specific viewport
    # region of the target framebuffer, rather than the whole thing.
    @overload
    def BlitTexture(self: CommonRenderPasses, commandList: CommandList, params: BlitParameters, bindingCache: Optional[BindingCache] = None) -> None: ...
    m_AnisotropicWrapSampler: Sampler
    m_LinearWrapSampler: Sampler
    # Fallback textures for materials missing a given texture slot.
    m_WhiteTexture: Texture
    m_BlackTexture: Texture

# Movable-but-not-copyable in C++, so Python only ever holds it via a shared_ptr (produced
# by DescriptorTableManager.CreateDescriptorHandle below), never constructs one directly.
class DescriptorHandle():
    def Get(self: DescriptorHandle) -> int: ...

class DescriptorTableManager():
    def __init__(self: DescriptorTableManager, device: Device, layout: BindingLayout) -> None: ...
    def GetDescriptorTable(self: DescriptorTableManager) -> BindingSet: ...
    # Registers a resource (e.g. a raw buffer SRV) in the bindless descriptor table, returning
    # a handle whose Get() is the bindless index to embed in shader-visible per-instance data
    # (see rt_particles.py, which registers its dynamic particle index/vertex buffers this way).
    def CreateDescriptorHandle(self: DescriptorTableManager, item: BindingSetItem) -> DescriptorHandle: ...

class TextureCache():
    def __init__(self: TextureCache, device: Device, fs: IFileSystem, descriptorTable: DescriptorTableManager | None) -> None: ...
    def Reset(self: TextureCache) -> None: ...
    def ProcessRenderingThreadCommands(self: TextureCache, commonPasses: CommonRenderPasses, timeLimitMilliseconds: float) -> bool: ...
    def LoadingFinished(self: TextureCache) -> None: ...
    def LoadTextureFromFile(self: TextureCache, path: Path, sRGB: bool, passes: Optional[CommonRenderPasses], commandList: CommandList) -> LoadedTexture: ...
    # Synchronous read+decode, but the GPU upload/mip generation is deferred to the
    # TextureCache's own queue (drained by ProcessRenderingThreadCommands/SceneLoaded) --
    # for loading extra standalone textures outside the scene's own material set (see
    # rt_particles.py's particle/environment-map textures).
    def LoadTextureFromFileDeferred(self: TextureCache, path: Path, sRGB: bool) -> LoadedTexture: ...

class LoadedTexture():
    texture: Optional[Texture]
    # The bindless table index for this texture's SRV, to embed in shader-visible
    # per-instance/per-particle data (see rt_particles.py).
    bindlessDescriptorIndex: int

class VertexAttribute(Enum):
    Position = 0
    TexCoord1 = 2
    Normal = 4
    Tangent = 5

class BufferGroup():
    def __init__(self: BufferGroup) -> None: ...
    indexBuffer: Optional[Buffer]
    vertexBuffer: Optional[Buffer]
    instanceBuffer: Optional[Buffer]
    def setVertexBufferRange(self: BufferGroup, attr: VertexAttribute, byteOffset: int, byteSize: int) -> None: ...
    def getVertexBufferRange(self: BufferGroup, attr: VertexAttribute) -> BufferRange: ...
    # Bindless table entries for this buffer group's raw index/vertex buffers (see
    # DescriptorTableManager.CreateDescriptorHandle) -- needed for procedural geometry whose
    # shaders look up vertex data via a bindless buffer index rather than a directly-bound SRV
    # (see rt_particles.py).
    indexBufferDescriptor: Optional[DescriptorHandle]
    vertexBufferDescriptor: Optional[DescriptorHandle]

# Only the domains this module's samples actually set (rt_particles.py's procedural particle
# material) plus Opaque (the default) -- matching the "only bind what's needed" convention
# used throughout.
class MaterialDomain(Enum):
    Opaque = 0
    AlphaBlended = 2

class Material():
    def __init__(self: Material) -> None: ...
    name: str
    domain: MaterialDomain
    # Set by the app to make Scene.Refresh()/FinishedLoading() re-upload the material's
    # constant buffer -- e.g. after swapping baseOrDiffuseTexture (see rt_particles.py).
    dirty: bool
    useSpecularGlossModel: bool
    enableBaseOrDiffuseTexture: bool
    baseOrDiffuseTexture: Optional[LoadedTexture]
    metalRoughOrSpecularTexture: Optional[LoadedTexture]
    normalTexture: Optional[LoadedTexture]
    emissiveTexture: Optional[LoadedTexture]
    occlusionTexture: Optional[LoadedTexture]
    transmissionTexture: Optional[LoadedTexture]
    opacityTexture: Optional[LoadedTexture]
    materialConstants: Optional[Buffer]

# Wraps Material.FillConstantBuffer() -- the generated MaterialConstants shader-cbuffer
# struct isn't otherwise exposed to Python.
def CreateMaterialConstantBuffer(device: Device, commandList: CommandList, material: Material) -> Buffer: ...

class MeshGeometry():
    def __init__(self: MeshGeometry) -> None: ...
    material: Optional[Material]
    numIndices: int
    numVertices: int
    # Assigned by the scene graph when the mesh is added to the scene; used to compute a
    # stable per-geometry shader-table hit-group index.
    globalGeometryIndex: int
    # This geometry's index/vertex range within its owning mesh's shared index/vertex buffers --
    # combine with MeshInfo.indexOffset/vertexOffset to get the absolute range.
    indexOffsetInMesh: int
    vertexOffsetInMesh: int

class MeshInfo():
    def __init__(self: MeshInfo) -> None: ...
    name: str
    buffers: Optional[BufferGroup]
    totalIndices: int
    totalVertices: int
    indexOffset: int
    vertexOffset: int
    geometries: list[MeshGeometry]
    def SetObjectSpaceBounds(self: MeshInfo, minX: float, minY: float, minZ: float, maxX: float, maxY: float, maxZ: float) -> None: ...
    # "For use by applications" per the engine itself -- lets an app cache each mesh's bottom-
    # level acceleration structure directly on the mesh (build BLASes once, look them up per
    # instance when building the TLAS).
    accelStruct: Optional[AccelStruct]
    # Set on the template mesh a skinned instance was cloned from -- see
    # SceneGraph.GetSkinnedMeshInstances()/SkinnedMeshInstance.GetPrototypeMesh(). isSkinPrototype
    # marks that template itself (never instantiated/ray-traced directly; skip it when building
    # BLASes -- see rt_bindless.py's CreateAccelStructs).
    isSkinPrototype: bool
    skinPrototype: Optional[MeshInfo]

class SceneGraphLeaf():
    def SetName(self: SceneGraphLeaf, name: str) -> None: ...

class MeshInstance(SceneGraphLeaf):
    def __init__(self: MeshInstance, mesh: MeshInfo) -> None: ...
    def GetMesh(self: MeshInstance) -> MeshInfo: ...
    def GetNode(self: MeshInstance) -> SceneGraphNode: ...
    # Stable per-instance index assigned by the scene graph -- used as the RT instance ID so
    # shaders can look up per-instance data (see rt_particles.py).
    def GetInstanceIndex(self: MeshInstance) -> int: ...

# One instance of a skinned (animated) mesh -- see SceneGraph.GetSkinnedMeshInstances().
# GetMesh() (inherited from MeshInstance) returns this instance's own per-instance mesh
# (deformed vertex buffers), distinct from GetPrototypeMesh()'s shared bind-pose template.
# GetLastUpdateFrameIndex() tells the app which frame the skinning compute pass last wrote new
# vertex positions for this instance, so it knows when to rebuild the instance's BLAS (see
# rt_bindless.py's BuildTLAS, matching the C++ original).
class SkinnedMeshInstance(MeshInstance):
    def GetPrototypeMesh(self: SkinnedMeshInstance) -> MeshInfo: ...
    def GetLastUpdateFrameIndex(self: SkinnedMeshInstance) -> int: ...

# The interface a shadow map implements, registered as a polymorphic base only -- the interface
# itself exposes nothing to Python, though a concrete shadow map may re-expose some of its
# virtuals under its own type (see CascadedShadowMap). Not constructible; see CascadedShadowMap.
class IShadowMap():
    pass

class Light(SceneGraphLeaf):
    def SetDirection(self: Light, x: float, y: float, z: float) -> None: ...
    # Raw bytes of the engine's LightConstants struct, ready for CommandList.writeBuffer --
    # same pattern as PlanarView.FillPlanarViewConstants.
    def FillLightConstants(self: Light) -> bytes: ...
    # Assigning this is the entire shadow wiring -- both lighting passes read it themselves.
    # None means "this light casts no shadow", and is how a shadow toggle is implemented.
    shadowMap: Optional[IShadowMap]

class DirectionalLight(Light):
    def __init__(self: DirectionalLight) -> None: ...
    irradiance: float
    angularSize: float

# One baked animation clip attached to the scene graph (e.g. a glTF skinned character
# animation) -- see SceneGraph.GetAnimations(). Apply() drives every channel (node
# transforms, morph/material properties) to their sampled values at `time`; the caller
# loops/wraps time against GetDuration() itself (see rt_bindless.py's Animate()).
class SceneGraphAnimation(SceneGraphLeaf):
    def GetDuration(self: SceneGraphAnimation) -> float: ...
    def Apply(self: SceneGraphAnimation, time: float) -> bool: ...

class SceneGraphNode():
    def __init__(self: SceneGraphNode) -> None: ...
    def SetLeaf(self: SceneGraphNode, leaf: SceneGraphLeaf) -> None: ...
    def SetName(self: SceneGraphNode, name: str) -> None: ...
    # The world-space translation component of this node's world transform, as (x, y, z) --
    # math types aren't exposed to Python (see rt_particles.py's emitter-position lookup).
    def GetWorldPosition(self: SceneGraphNode) -> tuple[float, float, float]: ...

class SceneGraph():
    def __init__(self: SceneGraph) -> None: ...
    def SetRootNode(self: SceneGraph, root: SceneGraphNode) -> SceneGraphNode: ...
    def GetRootNode(self: SceneGraph) -> SceneGraphNode: ...
    def AttachLeafNode(self: SceneGraph, parent: SceneGraphNode, leaf: SceneGraphLeaf) -> SceneGraphNode: ...
    def Refresh(self: SceneGraph, frameIndex: int) -> None: ...
    def GetLights(self: SceneGraph) -> list[Light]: ...
    def GetMeshes(self: SceneGraph) -> list[MeshInfo]: ...
    def GetMeshInstances(self: SceneGraph) -> list[MeshInstance]: ...
    # Baked animation clips attached anywhere in the graph (see SceneGraphAnimation).
    def GetAnimations(self: SceneGraph) -> list[SceneGraphAnimation]: ...
    # Skinned (animated) mesh instances -- see SkinnedMeshInstance.
    def GetSkinnedMeshInstances(self: SceneGraph) -> list[SkinnedMeshInstance]: ...
    # Searches from the graph root (context is always null in this codebase).
    def FindNode(self: SceneGraph, path: Path) -> Optional[SceneGraphNode]: ...

class Scene():
    def __init__(self: Scene, device: Device, shaderFactory: ShaderFactory, fs: IFileSystem, textureCache: TextureCache, descriptorTable: Optional[DescriptorTableManager]) -> None: ...
    def Load(self: Scene, sceneFileName: Path) -> bool: ...
    def FinishedLoading(self: Scene, frameIndex: int) -> None: ...
    # Distinct from SceneGraph.Refresh(frameIndex): this also captures the scene graph's
    # pending structure/transform-change flags onto the Scene itself, which Scene.Refresh()'s
    # buffer rebuild depends on to notice a newly-attached mesh instance and rebuild GPU
    # buffers for it -- calling SceneGraph.Refresh() directly would skip that and silently
    # leave the new instance's data out of the GPU buffers. Needed right after attaching a
    # hand-built mesh instance to the graph, before the first Scene.Refresh() (see
    # rt_particles.py's procedural particle mesh).
    def RefreshSceneGraph(self: Scene, frameIndex: int) -> None: ...
    # Uploads any per-frame-dynamic scene GPU buffer changes (e.g. a mesh whose vertex/index
    # data or material was updated this frame) -- distinct from RefreshSceneGraph, which is
    # only for static scene-graph-transform bookkeeping. Needed by scenes with procedurally-
    # updated geometry (see rt_particles.py).
    def Refresh(self: Scene, commandList: CommandList, frameIndex: int) -> None: ...
    def GetInstanceBuffer(self: Scene) -> Buffer: ...
    def GetGeometryBuffer(self: Scene) -> Buffer: ...
    def GetMaterialBuffer(self: Scene) -> Buffer: ...
    # Flattened (instanceIndex, geometryIndexInMesh, numIndices) per drawable geometry.
    def GetDrawItems(self: Scene) -> list[tuple[int, int, int]]: ...
    # For samples that need to walk the graph directly (attach their own lights, use
    # RenderCompositeView with the real root node) rather than just driving simple draw calls
    # via GetDrawItems().
    def GetSceneGraph(self: Scene) -> SceneGraph: ...

# Mirrors ApplicationBase::SceneLoaded()'s synchronous-load finalization step. Call after
# Scene.Load() and before Scene.FinishedLoading().
def SceneLoaded(textureCache: TextureCache, commonPasses: CommonRenderPasses) -> None: ...

# Registered (opaque, no constructor -- Python never creates one directly) purely so
# FirstPersonCamera/ThirdPersonCamera can share it as a pybind11 base, letting
# PlanarView.SetMatricesFromCamera below accept either camera type uniformly. Matrices
# (dm::affine3/float4x4) aren't exposed to Python -- SetMatricesFromCamera consumes them
# internally instead.
class BaseCamera():
    def SetMoveSpeed(self: BaseCamera, value: float) -> None: ...
    # (x, y, z) -- math types aren't exposed to Python.
    def GetDir(self: BaseCamera) -> tuple[float, float, float]: ...
    def GetUp(self: BaseCamera) -> tuple[float, float, float]: ...

class FirstPersonCamera(BaseCamera):
    def __init__(self: FirstPersonCamera) -> None: ...
    def LookAt(self: FirstPersonCamera, posX: float, posY: float, posZ: float, targetX: float, targetY: float, targetZ: float) -> None: ...
    def Animate(self: FirstPersonCamera, deltaT: float) -> None: ...
    def KeyboardUpdate(self: FirstPersonCamera, key: int, scancode: int, action: int, mods: int) -> None: ...
    def MousePosUpdate(self: FirstPersonCamera, xpos: float, ypos: float) -> None: ...
    def MouseButtonUpdate(self: FirstPersonCamera, button: int, action: int, mods: int) -> None: ...

# Orbit camera used by rt_particles.py. SetView feeds the camera's projection/viewport back in
# (needed for its own mouse-drag translation math), matching the C++ original's
# m_Camera.SetView(m_View) call after PlanarView is updated each frame.
class ThirdPersonCamera(BaseCamera):
    def __init__(self: ThirdPersonCamera) -> None: ...
    def SetTargetPosition(self: ThirdPersonCamera, x: float, y: float, z: float) -> None: ...
    def SetDistance(self: ThirdPersonCamera, distance: float) -> None: ...
    def SetRotation(self: ThirdPersonCamera, yaw: float, pitch: float) -> None: ...
    def SetView(self: ThirdPersonCamera, view: PlanarView) -> None: ...
    def Animate(self: ThirdPersonCamera, deltaT: float) -> None: ...
    def KeyboardUpdate(self: ThirdPersonCamera, key: int, scancode: int, action: int, mods: int) -> None: ...
    def MousePosUpdate(self: ThirdPersonCamera, xpos: float, ypos: float) -> None: ...
    def MouseButtonUpdate(self: ThirdPersonCamera, button: int, action: int, mods: int) -> None: ...
    def MouseScrollUpdate(self: ThirdPersonCamera, xoffset: float, yoffset: float) -> None: ...

# Polymorphic bases for the view hierarchy (View.h:46, View.h:55). Not constructible from
# Python -- they exist so passes that take any view (SkyPass, SsaoPass, ToneMappingPass,
# BloomPass) can accept PlanarView or CubemapView interchangeably.
class ICompositeView(): ...

class IView(ICompositeView): ...

class PlanarView(IView):
    @overload
    def __init__(self: PlanarView) -> None: ...
    # Copy constructor: PlanarView has no Python-visible identity beyond its cached state, so
    # this is how Python takes a snapshot of "this frame's view" to keep around as "last
    # frame's view" (e.g. for TemporalAntiAliasingPass, which needs both).
    @overload
    def __init__(self: PlanarView, other: PlanarView) -> None: ...
    def SetViewport(self: PlanarView, viewport: Viewport) -> None: ...
    def SetVariableRateShadingState(self: PlanarView, state: VariableRateShadingState) -> None: ...
    # Flat (x, y) scalars rather than a dm::float2 -- pairs with
    # TemporalAntiAliasingPass.GetCurrentPixelOffset, which returns exactly that 2-tuple.
    def SetPixelOffset(self: PlanarView, x: float, y: float) -> None: ...
    # Builds the view/projection matrices from the camera internally (they aren't exposed
    # to Python) via perspProjD3DStyleReverse(verticalFovRadians, aspectRatio, zNear).
    def SetMatricesFromCamera(self: PlanarView, camera: BaseCamera, aspectRatio: float, verticalFovRadians: float = ..., zNear: float = 0.1) -> None: ...
    # Non-camera, non-reverse-Z view setup for static/orbiting subjects: a combined
    # yaw+pitch rotation pushed back `distance` along its own Z axis, with a regular
    # (not reversed) D3D-style perspective projection.
    def SetMatricesOrbit(self: PlanarView, yawRadians: float, pitchRadians: float, distance: float, aspectRatio: float, fovYRadians: float, zNear: float, zFar: float) -> None: ...
    # Explicit look-at + regular (non-reverse-Z), finite-far D3D-style perspective, for
    # subjects whose eye AND look-at target both move independently (see work_graphs.py).
    def SetMatricesLookAt(
        self: PlanarView,
        posX: float, posY: float, posZ: float,
        targetX: float, targetY: float, targetZ: float,
        upX: float, upY: float, upZ: float,
        aspectRatio: float, fovYRadians: float, zNear: float, zFar: float,
    ) -> None: ...
    # 128 raw bytes: viewProj (float4x4, 64 bytes) followed by viewProjInverse (float4x4, 64
    # bytes), both transposed from donut's native row-major storage to match scene_data.hlsli's
    # column-major (no row_major qualifier) cbuffer layout. work_graphs.py's own
    # SceneConstantBuffer layout, not donut's PlanarViewConstants (see FillPlanarViewConstants
    # above).
    def GetViewProjMatrixBytes(self: PlanarView) -> bytes: ...
    def UpdateCache(self: PlanarView) -> None: ...
    def GetViewportState(self: PlanarView) -> ViewportState: ...
    # Raw bytes of the engine's PlanarViewConstants struct, ready for CommandList.writeBuffer.
    def FillPlanarViewConstants(self: PlanarView) -> bytes: ...

# Splits one transform into 6 face view/proj matrices for cube-map/environment rendering. Its
# faces are plain PlanarView instances internally, so GetFaceView returns the existing
# PlanarView type rather than a new view hierarchy.
class CubemapView(IView):
    def __init__(self: CubemapView) -> None: ...
    def SetTransformFromCamera(self: CubemapView, camera: FirstPersonCamera, zNear: float, cullDistance: float, useReverseInfiniteProjections: bool = True) -> None: ...
    def SetArrayViewports(self: CubemapView, resolution: int, firstArraySlice: int) -> None: ...
    def UpdateCache(self: CubemapView) -> None: ...
    def GetFaceView(self: CubemapView, face: int) -> PlanarView: ...

# Standalone view*projection matrix computation for cases that don't go through PlanarView at
# all: rotate by `rotationRadians` around an arbitrary (auto-normalized) axis, tilt down by
# `pitchRadians`, push back `distance`, then apply a regular D3D-style perspective projection.
# Returns the resulting float4x4 as raw bytes, ready for CommandList.writeBuffer.
def ComputeRotatingViewProjMatrix(axisX: float, axisY: float, axisZ: float, rotationRadians: float, pitchRadians: float, distance: float, aspectRatio: float, fovYRadians: float, zNear: float, zFar: float) -> bytes: ...

# IDrawStrategy/IGeometryPass/GeometryPassContext are real polymorphic bases -- RenderView and
# RenderCompositeView accept any strategy/pass/context derived from these, rather than one
# fixed concrete overload per combination.
class IDrawStrategy(): ...
class IGeometryPass(): ...
class GeometryPassContext(): ...

class GBufferRenderTargets():
    def __init__(self: GBufferRenderTargets) -> None: ...
    def Init(self: GBufferRenderTargets, device: Device, width: int, height: int, sampleCount: int, enableMotionVectors: bool, useReverseProjection: bool) -> None: ...
    def Clear(self: GBufferRenderTargets, commandList: CommandList) -> None: ...
    width: int
    height: int
    def GetFramebuffer(self: GBufferRenderTargets, view: PlanarView) -> Framebuffer: ...
    # Public texture handles from GBuffer.h. All None until Init() has been called.
    Depth: Optional[Texture]
    GBufferDiffuse: Optional[Texture]
    GBufferSpecular: Optional[Texture]
    GBufferNormals: Optional[Texture]
    GBufferEmissive: Optional[Texture]
    MotionVectors: Optional[Texture]
    GBufferFramebuffer: Optional[FramebufferFactory]
    def GetSampleCount(self: GBufferRenderTargets) -> int: ...
    def GetUseReverseProjection(self: GBufferRenderTargets) -> bool: ...

class GBufferFillPassCreateParameters():
    def __init__(self: GBufferFillPassCreateParameters) -> None: ...

class GBufferFillPassContext(GeometryPassContext):
    def __init__(self: GBufferFillPassContext) -> None: ...

class GBufferFillPass(IGeometryPass):
    def __init__(self: GBufferFillPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: GBufferFillPass, shaderFactory: ShaderFactory, params: GBufferFillPassCreateParameters) -> None: ...
    def ResetBindingCache(self: GBufferFillPass) -> None: ...

# Depth-only geometry pass. Its consumer here is the shadow map, which is why the depth bias
# fields are exposed -- they are applied at Init(), so changing one means a new pass.
# materialBindings is intentionally unbound: the pass creates its own when it is null.
class DepthPassCreateParameters():
    def __init__(self: DepthPassCreateParameters) -> None: ...
    depthBias: int
    depthBiasClamp: float
    slopeScaledDepthBias: float
    trackLiveness: bool
    useInputAssembler: bool
    numConstantBufferVersions: int

class DepthPassContext(GeometryPassContext):
    def __init__(self: DepthPassContext) -> None: ...

class DepthPass(IGeometryPass):
    def __init__(self: DepthPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: DepthPass, shaderFactory: ShaderFactory, params: DepthPassCreateParameters) -> None: ...
    def ResetBindingCache(self: DepthPass) -> None: ...

class PassthroughDrawStrategy(IDrawStrategy):
    def __init__(self: PassthroughDrawStrategy) -> None: ...
    def SetSingleItem(self: PassthroughDrawStrategy, instance: MeshInstance, mesh: MeshInfo, geometry: MeshGeometry, material: Material, buffers: BufferGroup, distanceToCamera: float, cullMode: RasterCullMode) -> None: ...

# Walks a real scene graph (as opposed to PassthroughDrawStrategy's single fixed item),
# batching opaque geometry for RenderView/RenderCompositeView.
class InstancedOpaqueDrawStrategy(IDrawStrategy):
    def __init__(self: InstancedOpaqueDrawStrategy) -> None: ...

class TransparentDrawStrategy(IDrawStrategy):
    def __init__(self: TransparentDrawStrategy) -> None: ...

class DeferredLightingPassInputs():
    def __init__(self: DeferredLightingPassInputs) -> None: ...
    def SetGBuffer(self: DeferredLightingPassInputs, targets: GBufferRenderTargets) -> None: ...
    def SetAmbientColors(self: DeferredLightingPassInputs, topR: float, topG: float, topB: float, bottomR: float, bottomG: float, bottomB: float) -> None: ...
    def SetLights(self: DeferredLightingPassInputs, lights: list[Light]) -> None: ...
    output: Optional[Texture]
    # None disables the SSAO term. Only ever set when sampleCount == 1 -- SsaoPass does not
    # exist under MSAA.
    ambientOcclusion: Optional[Texture]

class DeferredLightingPass():
    def __init__(self: DeferredLightingPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: DeferredLightingPass, shaderFactory: ShaderFactory) -> None: ...
    def Render(self: DeferredLightingPass, commandList: CommandList, view: PlanarView, inputs: DeferredLightingPassInputs) -> None: ...
    def ResetBindingCache(self: DeferredLightingPass) -> None: ...

class ForwardShadingPassCreateParameters():
    def __init__(self: ForwardShadingPassCreateParameters) -> None: ...
    # Default 16; raise for multi-threaded recording (each concurrently-recorded command list
    # consumes its own volatile constant buffer version).
    numConstantBufferVersions: int

class ForwardShadingPassContext(GeometryPassContext):
    def __init__(self: ForwardShadingPassContext) -> None: ...

class ForwardShadingPass(IGeometryPass):
    def __init__(self: ForwardShadingPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: ForwardShadingPass, shaderFactory: ShaderFactory, params: ForwardShadingPassCreateParameters) -> None: ...
    def ResetBindingCache(self: ForwardShadingPass) -> None: ...
    # lightProbes is always empty here -- not otherwise exposed to Python.
    def PrepareLights(self: ForwardShadingPass, context: ForwardShadingPassContext, commandList: CommandList, lights: list[Light], topR: float, topG: float, topB: float, bottomR: float, bottomG: float, bottomB: float) -> None: ...

# Sub-pixel jitter pattern. Held by the pass, not by TemporalAntiAliasingParameters: set it
# with SetJitter, read the resulting per-frame offset with GetCurrentPixelOffset.
class TemporalAntiAliasingJitter(Enum):
    MSAA = 0
    Halton = 1
    R2 = 2
    WhiteNoise = 3

class TemporalAntiAliasingParameters():
    newFrameWeight: float
    clampingFactor: float
    maxRadiance: float
    enableHistoryClamping: bool
    useHistoryClampRelax: bool
    def __init__(self: TemporalAntiAliasingParameters) -> None: ...

# historyClampRelax is intentionally left unbound: nothing in this codebase builds the mask
# texture it expects, matching useHistoryClampRelax always false.
class TemporalAntiAliasingCreateParameters():
    sourceDepth: Optional[Texture]
    motionVectors: Optional[Texture]
    unresolvedColor: Optional[Texture]
    resolvedColor: Optional[Texture]
    feedback1: Optional[Texture]
    feedback2: Optional[Texture]
    useCatmullRomFilter: bool
    motionVectorStencilMask: int
    numConstantBufferVersions: int
    def __init__(self: TemporalAntiAliasingCreateParameters) -> None: ...

class TemporalAntiAliasingPass():
    def __init__(self: TemporalAntiAliasingPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, compositeView: PlanarView, params: TemporalAntiAliasingCreateParameters) -> None: ...
    def RenderMotionVectors(self: TemporalAntiAliasingPass, commandList: CommandList, compositeView: PlanarView, compositeViewPrevious: PlanarView) -> None: ...
    def TemporalResolve(self: TemporalAntiAliasingPass, commandList: CommandList, params: TemporalAntiAliasingParameters, feedbackIsValid: bool, compositeViewInput: PlanarView, compositeViewOutput: PlanarView) -> None: ...
    def SetJitter(self: TemporalAntiAliasingPass, jitter: TemporalAntiAliasingJitter) -> None: ...
    # The current frame's sub-pixel offset as (x, y), both in [-0.5, 0.5] -- dm::float2
    # decomposed, since math types are not exposed to Python. Feed to PlanarView.SetPixelOffset.
    def GetCurrentPixelOffset(self: TemporalAntiAliasingPass) -> tuple[float, float]: ...
    # Call once per frame, after TemporalResolve: this also ping-pongs the two resolve binding
    # sets, which is what swaps the feedback pair's history and output roles.
    def AdvanceFrame(self: TemporalAntiAliasingPass) -> None: ...

# The four dm::float3 fields (skyColor, horizonColor, groundColor, directionUp) are set
# through flat-scalar methods -- donut math types are not exposed to Python.
class SkyParameters():
    brightness: float
    horizonSize: float
    glowSize: float
    glowIntensity: float
    glowSharpness: float
    maxLightRadiance: float
    def __init__(self: SkyParameters) -> None: ...
    def SetSkyColor(self: SkyParameters, r: float, g: float, b: float) -> None: ...
    def SetHorizonColor(self: SkyParameters, r: float, g: float, b: float) -> None: ...
    def SetGroundColor(self: SkyParameters, r: float, g: float, b: float) -> None: ...
    def SetDirectionUp(self: SkyParameters, x: float, y: float, z: float) -> None: ...

# FillShaderParameters is intentionally left unbound -- see _pydonut.cpp.
class SkyPass():
    def __init__(self: SkyPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, framebufferFactory: FramebufferFactory, compositeView: IView) -> None: ...
    def Render(self: SkyPass, commandList: CommandList, compositeView: IView, light: DirectionalLight, params: SkyParameters) -> None: ...

class SsaoParameters():
    amount: float
    backgroundViewDepth: float
    radiusWorld: float
    surfaceBias: float
    powerExponent: float
    enableBlur: bool
    blurSharpness: float
    def __init__(self: SsaoParameters) -> None: ...

# The CreateParameters constructor and CreateBindingSet are intentionally left unbound --
# see _pydonut.cpp. Render's bindingSetIndex is fixed at 0.
class SsaoPass():
    def __init__(self: SsaoPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, gbufferDepth: Texture, gbufferNormals: Texture, destinationTexture: Texture) -> None: ...
    def Render(self: SsaoPass, commandList: CommandList, params: SsaoParameters, compositeView: IView) -> None: ...

class ToneMappingParameters():
    histogramLowPercentile: float
    histogramHighPercentile: float
    eyeAdaptationSpeedUp: float
    eyeAdaptationSpeedDown: float
    minAdaptedLuminance: float
    maxAdaptedLuminance: float
    exposureBias: float
    whitePoint: float
    enableColorLUT: bool
    def __init__(self: ToneMappingParameters) -> None: ...

# colorLUT is intentionally left unbound. exposureBufferOverride carries eye adaptation
# across a resize -- hand it the outgoing pass's GetExposureBuffer(), whose Buffer owns a
# reference of its own and so stays valid after the pass it came from is released.
class ToneMappingPassCreateParameters():
    isTextureArray: bool
    histogramBins: int
    numConstantBufferVersions: int
    exposureBufferOverride: Optional[Buffer]
    def __init__(self: ToneMappingPassCreateParameters) -> None: ...

# Render/ResetHistogram/AddFrameToHistogram/ComputeExposure are intentionally left unbound --
# SimpleRender performs those steps internally.
class ToneMappingPass():
    def __init__(self: ToneMappingPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, framebufferFactory: FramebufferFactory, compositeView: IView, params: ToneMappingPassCreateParameters) -> None: ...
    def SimpleRender(self: ToneMappingPass, commandList: CommandList, params: ToneMappingParameters, compositeView: IView, sourceTexture: Texture) -> None: ...
    def AdvanceFrame(self: ToneMappingPass, frameTime: float) -> None: ...
    def ResetExposure(self: ToneMappingPass, commandList: CommandList, initialExposure: float = 0.0) -> None: ...
    def GetExposureBuffer(self: ToneMappingPass) -> Buffer: ...

# The FramebufferFactory is supplied both at construction and per Render call -- they differ
# between the TAA and MSAA paths. sourceDestTexture is read and written in place.
class BloomPass():
    def __init__(self: BloomPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, framebufferFactory: FramebufferFactory, compositeView: IView) -> None: ...
    def Render(self: BloomPass, commandList: CommandList, framebufferFactory: FramebufferFactory, compositeView: IView, sourceDestTexture: Texture, sigmaInPixels: float, blendFactor: float) -> None: ...

# A directional light's shadow map, as an array of cascade slices. The cascade count is fixed at
# construction: the composite view GetView() returns is built once in the constructor and never
# rebuilt, so changing the count means constructing a new CascadedShadowMap.
#
# Both setup calls take the PlanarView rather than a frustum -- donut math types never cross into
# Python, and the two fits want different frustums off it (view frustum for the tight fit,
# projection frustum plus inverse view matrix for the stable one). Both return True if any
# cascade's view changed. numCascades must be in [1, 4] and exponent must be > 1, both asserted
# in C++.
class CascadedShadowMap(IShadowMap):
    def __init__(self: CascadedShadowMap, device: Device, resolution: int, numCascades: int, numPerObjectShadows: int, format: Format, isUAV: bool = False) -> None: ...
    def SetupForPlanarView(self: CascadedShadowMap, light: DirectionalLight, view: PlanarView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
    def SetupForPlanarViewStable(self: CascadedShadowMap, light: DirectionalLight, view: PlanarView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
    def Clear(self: CascadedShadowMap, commandList: CommandList) -> None: ...
    # An ICompositeView, not an IView: one PlanarView per allocated cascade. Pass it to
    # RenderCompositeView to fill every cascade in a single call.
    def GetView(self: CascadedShadowMap) -> ICompositeView: ...
    def GetCascadeView(self: CascadedShadowMap, cascade: int) -> PlanarView: ...
    def GetTexture(self: CascadedShadowMap) -> Texture: ...
    # 0 until one of the setup calls has run -- the constructor allocates cascades but does not
    # activate them.
    def GetNumberOfCascades(self: CascadedShadowMap) -> int: ...
    def SetLitOutOfBounds(self: CascadedShadowMap, litOutOfBounds: bool) -> None: ...
    def SetFalloffDistance(self: CascadedShadowMap, distance: float) -> None: ...

class FramebufferFactory():
    def __init__(self: FramebufferFactory, device: Device) -> None: ...
    def SetRenderTargets(self: FramebufferFactory, targets: list[Texture]) -> None: ...
    depthTarget: Optional[Texture]
    shadingRateSurface: Optional[Texture]
    def GetFramebuffer(self: FramebufferFactory, view: PlanarView) -> Framebuffer: ...

def RenderView(commandList: CommandList, view: IView, viewPrev: Optional[IView], framebuffer: Framebuffer, drawStrategy: IDrawStrategy, pass_: IGeometryPass, context: GeometryPassContext, materialEvents: bool = False) -> None: ...
# view is an ICompositeView, one step wider than RenderView's IView: CascadedShadowMap.GetView()
# returns a CompositeView, which derives from ICompositeView directly and is not an IView.
# passEvent names the pass in a graphics capture. It sits after materialEvents rather than in the
# C++ parameter order because existing callers pass materialEvents positionally.
def RenderCompositeView(commandList: CommandList, view: ICompositeView, viewPrev: Optional[ICompositeView], framebufferFactory: FramebufferFactory, rootNode: SceneGraphNode, drawStrategy: IDrawStrategy, pass_: IGeometryPass, passContext: GeometryPassContext, materialEvents: bool = False, passEvent: Optional[str] = None) -> None: ...

class AdapterInfo():
    name: str
    vendorID: int
    deviceID: int
    dedicatedVideoMemory: int
    uuid: Optional[list[int]]
    luid: Optional[list[int]]

class IRenderPass():
    def __init__(self: IRenderPass, deviceManager: DeviceManager) -> None: ...
    def SetLatewarpOptions(self: IRenderPass) -> None: ...
    def ShouldAnimateUnfocused(self: IRenderPass) -> bool: ...
    def ShouldRenderUnfocused(self: IRenderPass) -> bool: ...
    def SupportsDepthBuffer(self: IRenderPass) -> bool: ...
    def Render(self: IRenderPass, framebuffer: Framebuffer) -> None: ...
    def Animate(self: IRenderPass, elapsedTimeSeconds: float) -> None: ...
    def BackBufferResizing(self: IRenderPass) -> None: ...
    def BackBufferResized(self: IRenderPass, width: int, height: int, sampleCount: int) -> None: ...
    def DisplayScaleChanged(self: IRenderPass, scaleX: float, scaleY: float) -> None: ...
    def KeyboardUpdate(self: IRenderPass, key: int, scancode: int, action: int, mods: int) -> bool: ...
    def KeyboardCharInput(self: IRenderPass, unicode: int, mods: int) -> bool: ...
    def MousePosUpdate(self: IRenderPass, xpos: float, ypos: float) -> bool: ...
    def MouseScrollUpdate(self: IRenderPass, xoffset: float, yoffset: float) -> bool: ...
    def MouseButtonUpdate(self: IRenderPass, button: int, action: int, mods: int) -> bool: ...
    def JoystickButtonUpdate(self: IRenderPass, button: int, pressed: bool) -> bool: ...
    def JoystickAxisUpdate(self: IRenderPass, axis: int, value: float) -> bool: ...
    def GetDeviceManager(self: IRenderPass) -> DeviceManager: ...
    def GetDevice(self: IRenderPass) -> Device: ...
    def GetFrameIndex(self: IRenderPass) -> int: ...

class ApplicationBase(IRenderPass):
    def __init__(self: ApplicationBase, deviceManager: DeviceManager) -> None: ...
    def RenderScene(self: ApplicationBase, framebuffer: Framebuffer) -> None: ...
    def RenderSplashScreen(self: ApplicationBase, framebuffer: Framebuffer) -> None: ...
    def BeginLoadingScene(self: ApplicationBase, fs: IFileSystem, sceneFileName: Path) -> None: ...
    def LoadScene(self: ApplicationBase, fs: IFileSystem, sceneFileName: Path) -> bool: ...
    def SceneUnloading(self: ApplicationBase) -> None: ...
    def SceneLoaded(self: ApplicationBase) -> None: ...
    def SetAsynchronousLoadingEnabled(self: ApplicationBase, enabled: bool) -> None: ...
    def IsSceneLoading(self: ApplicationBase) -> bool: ...
    def IsSceneLoaded(self: ApplicationBase) -> bool: ...
    def GetCommonPasses(self: ApplicationBase) -> CommonRenderPasses: ...
    # Wire a Python-created TextureCache/CommonRenderPasses into the base so the inherited
    # SceneLoaded() finalizes it correctly, instead of a null cache doing nothing.
    m_TextureCache: TextureCache
    m_CommonPasses: CommonRenderPasses
    m_IsAsyncLoad: bool

# base class to build IRenderPass-based UIs using ImGui through NVRHI. Subclass and implement
# buildUI() (see rt_particles.py's UserInterface) -- everything else (input routing, Render(),
# Animate()) is already implemented by the base and isn't meant to be overridden.
class ImGui_Renderer(IRenderPass):
    def __init__(self: ImGui_Renderer, deviceManager: DeviceManager) -> None: ...
    def Init(self: ImGui_Renderer, shaderFactory: ShaderFactory) -> bool: ...

# Only the ImGui:: entry points rt_particles.py's UserInterface.buildUI() actually calls.
# Out-params (bool*, float*, int*) become (changed, newValue...) return tuples -- Python has
# no pointers, so the caller re-assigns its own state from the tuple, e.g.
# changed, ui.enableAnimations = pyd.ImGui.Checkbox("...", ui.enableAnimations).
class ImGui():
    # Disables ImGui's automatic imgui.ini window-layout persistence, which would otherwise
    # write that file into the process's working directory on exit (see rt_particles.py's
    # UserInterface, matching the C++ original's ImGui::GetIO().IniFilename = nullptr).
    @staticmethod
    def DisableIniFile() -> None: ...
    @staticmethod
    def SetNextWindowPos(x: float, y: float, cond: int = 0) -> None: ...
    # p_open is always null in this codebase's usage (no closable windows).
    @staticmethod
    def Begin(name: str, flags: int = 0) -> bool: ...
    @staticmethod
    def End() -> None: ...
    @staticmethod
    def Checkbox(label: str, value: bool) -> tuple[bool, bool]: ...
    @staticmethod
    def Separator() -> None: ...
    # TextUnformatted, not Text -- Text() parses its argument as a printf format string, which
    # would let arbitrary Python string content control formatting.
    @staticmethod
    def Text(text: str) -> None: ...
    @staticmethod
    def Indent() -> None: ...
    @staticmethod
    def Unindent() -> None: ...
    @staticmethod
    def Combo(label: str, currentItem: int, items: list[str]) -> tuple[bool, int]: ...
    @staticmethod
    def PushItemWidth(width: float) -> None: ...
    @staticmethod
    def PopItemWidth() -> None: ...
    @staticmethod
    def BeginCombo(label: str, previewValue: str) -> bool: ...
    @staticmethod
    def Selectable(label: str, selected: bool = False) -> bool: ...
    @staticmethod
    def EndCombo() -> None: ...
    @staticmethod
    def DragFloat3(label: str, x: float, y: float, z: float, speed: float = 1.0) -> tuple[bool, float, float, float]: ...
    @staticmethod
    def Button(label: str) -> bool: ...
    @staticmethod
    def SliderFloat(label: str, value: float, vMin: float, vMax: float) -> tuple[bool, float]: ...
    @staticmethod
    def DragFloat(label: str, value: float, speed: float = 1.0, vMin: float = 0.0, vMax: float = 0.0) -> tuple[bool, float]: ...
    @staticmethod
    def CollapsingHeader(label: str) -> bool: ...
    @staticmethod
    def SameLine() -> None: ...
    @staticmethod
    def SetItemDefaultFocus() -> None: ...

class PipelineCallbacks():
    beforeFrame: Optional[Callable[[DeviceManager, int], None]]
    beforeAnimate: Optional[Callable[[DeviceManager, int], None]]
    afterAnimate: Optional[Callable[[DeviceManager, int], None]]
    beforeRender: Optional[Callable[[DeviceManager, int], None]]
    afterRender: Optional[Callable[[DeviceManager, int], None]]
    beforePresent: Optional[Callable[[DeviceManager, int], None]]
    afterPresent: Optional[Callable[[DeviceManager, int], None]]

class DeviceCreationParameters():
    # InstanceParameters (base class)
    enableDebugRuntime: bool
    enableWarningsAsErrors: bool
    enableGPUValidation: bool
    headlessDevice: bool
    logBufferLifetime: bool
    enableHeapDirectlyIndexed: bool
    enablePerMonitorDPI: bool
    infoLogSeverity: LogSeverity
    vulkanLibraryName: str
    requiredVulkanInstanceExtensions: list[str]
    requiredVulkanLayers: list[str]
    optionalVulkanInstanceExtensions: list[str]
    optionalVulkanLayers: list[str]

    # DeviceCreationParameters
    startMaximized: bool
    startFullscreen: bool
    startBorderless: bool
    fullscreenAlwaysOnTop: bool
    windowPosX: int
    windowPosY: int
    backBufferWidth: int
    backBufferHeight: int
    refreshRate: int
    swapChainBufferCount: int
    swapChainFormat: Format
    swapChainSampleCount: int
    swapChainSampleQuality: int
    depthBufferFormat: Format
    maxFramesInFlight: int
    enableNvrhiValidationLayer: bool
    enableRayTracingValidation: bool
    vsyncEnabled: bool
    enableRayTracingExtensions: bool
    enableComputeQueue: bool
    enableCopyQueue: bool
    enableJoystickInput: bool
    # Present ONLY when AFTERMATH_AVAILABLE is True (built with -DPYDONUT_WITH_AFTERMATH=ON).
    # Guard every access on that flag; this attribute does not exist in a default build.
    enableAftermath: bool
    adapterIndex: int
    supportExplicitDisplayScaling: bool
    resizeWindowWithDisplayScale: bool
    swapChainUsage: int
    featureLevel: int
    requiredVulkanDeviceExtensions: list[str]
    optionalVulkanDeviceExtensions: list[str]
    ignoredVulkanValidationMessageLocations: list[int]

class DeviceManager():
    callbacks: PipelineCallbacks

    @staticmethod
    def Create(api: GraphicsAPI = GraphicsAPI.Vulkan) -> DeviceManager: ...
    def CreateHeadlessDevice(self: DeviceManager, params: DeviceCreationParameters) -> bool: ...
    def CreateWindowDeviceAndSwapChain(self: DeviceManager, params: DeviceCreationParameters, windowTitle: str = "") -> bool: ...
    def CreateInstance(self: DeviceManager, params: DeviceCreationParameters) -> bool: ...
    def EnumerateAdapters(self: DeviceManager) -> tuple[bool, list[AdapterInfo]]: ...
    def AddRenderPassToFront(self: DeviceManager, renderPass: IRenderPass) -> None: ...
    def AddRenderPassToBack(self: DeviceManager, renderPass: IRenderPass) -> None: ...
    def RemoveRenderPass(self: DeviceManager, renderPass: IRenderPass) -> None: ...
    def RunMessageLoop(self: DeviceManager) -> None: ...
    def GetWindowDimensions(self: DeviceManager) -> tuple[int, int]: ...
    def GetDPIScaleInfo(self: DeviceManager) -> tuple[float, float]: ...
    def GetDeviceParams(self: DeviceManager) -> DeviceCreationParameters: ...
    def GetAverageFrameTimeSeconds(self: DeviceManager) -> float: ...
    def GetPreviousFrameTimestamp(self: DeviceManager) -> float: ...
    def SetFrameTimeUpdateInterval(self: DeviceManager, seconds: float) -> None: ...
    def IsVsyncEnabled(self: DeviceManager) -> bool: ...
    def SetVsyncEnabled(self: DeviceManager, enabled: bool) -> None: ...
    def ReportLiveObjects(self: DeviceManager) -> None: ...
    def SetEnableRenderDuringWindowMovement(self: DeviceManager, val: bool) -> None: ...
    def IsWindowFocused(self: DeviceManager) -> bool: ...
    def IsWindowVisible(self: DeviceManager) -> bool: ...
    def RenderNextFrameWhileUnfocused(self: DeviceManager) -> None: ...
    def GetFrameIndex(self: DeviceManager) -> int: ...
    def GetCurrentBackBuffer(self: DeviceManager) -> Texture: ...
    def GetBackBuffer(self: DeviceManager, index: int) -> Texture: ...
    def GetCurrentBackBufferIndex(self: DeviceManager) -> int: ...
    def GetBackBufferCount(self: DeviceManager) -> int: ...
    def GetCurrentFramebuffer(self: DeviceManager, withDepth: bool = True) -> Framebuffer: ...
    def GetFramebuffer(self: DeviceManager, index: int, withDepth: bool = True) -> Framebuffer: ...
    def GetDepthBuffer(self: DeviceManager) -> Texture: ...
    def GetDevice(self: DeviceManager) -> Device: ...
    def GetRendererString(self: DeviceManager) -> str: ...
    def GetGraphicsAPI(self: DeviceManager) -> GraphicsAPI: ...
    def SetWindowTitle(self: DeviceManager, title: str) -> None: ...
    def SetInformativeWindowTitle(self: DeviceManager, applicationName: str, includeFramerate: bool = True, extraInfo: Optional[str] = None) -> None: ...
    def GetWindowTitle(self: DeviceManager) -> str: ...
    def IsVulkanInstanceExtensionEnabled(self: DeviceManager, extensionName: str) -> bool: ...
    def IsVulkanDeviceExtensionEnabled(self: DeviceManager, extensionName: str) -> bool: ...
    def IsVulkanLayerEnabled(self: DeviceManager, layerName: str) -> bool: ...
    def GetEnabledVulkanInstanceExtensions(self: DeviceManager) -> list[str]: ...
    def GetEnabledVulkanDeviceExtensions(self: DeviceManager) -> list[str]: ...
    def GetEnabledVulkanLayers(self: DeviceManager) -> list[str]: ...
    def Shutdown(self: DeviceManager) -> None: ...
