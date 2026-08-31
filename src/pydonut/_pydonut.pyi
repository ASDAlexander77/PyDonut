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
# Walks `path` and its direct subdirectories for .scene.json/.gltf/.glb files, returning
# absolute paths as strings -- for samples offering a scene picker (feature_demo.py).
def FindScenes(fs: IFileSystem, path: Path) -> list[str]: ...
# Picks the entry of `available` whose filename is `preferred`, falling back to the first
# entry when it isn't present (and to "" when `available` is empty).
def FindPreferredScene(available: list[str], preferred: str) -> str: ...
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

# NGX DLSS integration. Only present when donut was built with DONUT_WITH_DLSS=ON (which
# fetches the DLSS SDK); pydonut re-exports these as None otherwise, so test
# `if pyd.DLSS is not None` before use.
class DLSSInitParameters:
    def __init__(self) -> None: ...
    inputWidth: int
    inputHeight: int
    # Equal to the input size for DLAA (native-resolution antialiasing); larger than the
    # input for upscaling.
    outputWidth: int
    outputHeight: int
    useLinearDepth: bool
    useAutoExposure: bool
    useRayReconstruction: bool

class DLSSEvaluateParameters:
    def __init__(self) -> None: ...
    depthTexture: Texture | None
    motionVectorsTexture: Texture | None
    inputColorTexture: Texture | None
    outputColorTexture: Texture | None
    # Optional; ToneMappingPass.GetExposureBuffer(). Ignored when useAutoExposure is set.
    exposureBuffer: Buffer | None
    # DLSS Ray Reconstruction only -- leave unset for plain DLSS.
    diffuseAlbedo: Texture | None
    specularAlbedo: Texture | None
    normalRoughness: Texture | None
    exposureScale: float
    sharpness: float
    resetHistory: bool

class DLSS:
    # Returns None when NGX cannot initialise on this machine (no driver support, missing
    # nvngx_dlss.dll). directoryWithExecutable is where the DLL is looked up -- pass
    # GetDirectoryWithExecutable().
    @staticmethod
    def Create(
        device: Device,
        shaderFactory: ShaderFactory,
        directoryWithExecutable: str,
        applicationID: int = ...,
    ) -> DLSS | None: ...
    # (instanceExtensions, deviceExtensions) that must be added to
    # DeviceCreationParameters BEFORE CreateWindowDeviceAndSwapChain, or DLSS cannot
    # initialise on Vulkan. Unlike the C++ out-parameter form, this returns new lists.
    @staticmethod
    def GetRequiredVulkanExtensions() -> tuple[list[str], list[str]]: ...
    def IsDlssSupported(self) -> bool: ...
    # False until Init() has run successfully; this is the flag to gate Evaluate on.
    def IsDlssInitialized(self) -> bool: ...
    def IsRayReconstructionSupported(self) -> bool: ...
    def IsRayReconstructionInitialized(self) -> bool: ...
    def Init(self, params: DLSSInitParameters) -> None: ...
    def Evaluate(
        self,
        commandList: CommandList,
        params: DLSSEvaluateParameters,
        view: PlanarView,
    ) -> None: ...

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
    VS: Shader | None
    PS: Shader | None
    inputLayout: InputLayout | None
    def __init__(self: GraphicsPipelineDesc) -> None: ...
    def addBindingLayout(self: GraphicsPipelineDesc, layout: BindingLayout) -> None: ...

class GraphicsState():
    viewport: ViewportState
    pipeline: GraphicsPipeline | None
    framebuffer: Framebuffer | None
    def __init__(self: GraphicsState) -> None: ...
    def addBindingSet(self: GraphicsState, bindingSet: BindingSet) -> None: ...
    # vertexBuffers is a fixed-capacity static_vector in nvrhi -- appended to via this method
    # rather than exposed as a plain read-write list.
    def addVertexBuffer(self: GraphicsState, buffer: Buffer, slot: int, offset: int = 0) -> None: ...
    def setIndexBuffer(self: GraphicsState, buffer: Buffer, format: Format, offset: int = 0) -> None: ...

class MeshletPipelineDesc():
    primType: PrimitiveType
    renderState: RenderState
    AS: Shader | None
    MS: Shader | None
    PS: Shader | None
    def __init__(self: MeshletPipelineDesc) -> None: ...

class MeshletState():
    viewport: ViewportState
    pipeline: MeshletPipeline | None
    framebuffer: Framebuffer | None
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
    CS: Shader | None
    def __init__(self: ComputePipelineDesc) -> None: ...
    def addBindingLayout(self: ComputePipelineDesc, layout: BindingLayout) -> None: ...

class ComputeState():
    pipeline: ComputePipeline | None
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
    texture: Texture | None

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
    indexBuffer: Buffer | None
    vertexBuffer: Buffer | None
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
    shaderTable: ShaderTable | None
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
    def getShader(self: ShaderLibrary, entryName: str, shaderType: ShaderType) -> Shader | None: ...
class InputLayout(): ...
class GraphicsPipeline(): ...
class MeshletPipeline(): ...
class ComputePipeline(): ...
class RayTracingPipeline():
    def createShaderTable(self: RayTracingPipeline) -> ShaderTable: ...
class ShaderTable():
    def setRayGenerationShader(self: ShaderTable, exportName: str, bindings: BindingSet | None = None) -> None: ...
    def addHitGroup(self: ShaderTable, exportName: str, bindings: BindingSet | None = None) -> int: ...
    def addMissShader(self: ShaderTable, exportName: str, bindings: BindingSet | None = None) -> int: ...
# Per-queue command list lifetime tracker (nvrhi.h:3157). Each thread that submits work to a
# queue should own one for that queue: after a submission, the internal command lists and the
# resources they reference are held here until the GPU has finished with them. Constructed only
# by Device.createCommandListLifetimeTracker -- there is no Python constructor.
class CommandListLifetimeTracker():
    # Releases command lists that have finished executing on the GPU. Call it frequently, e.g.
    # once per simulation step. Releases the GIL -- it polls the GPU.
    def runGarbageCollection(self: CommandListLifetimeTracker) -> None: ...
class CommandListParameters():
    def __init__(self: CommandListParameters) -> None: ...
    # False (deferred) means the command list is recorded but not auto-submitted -- required
    # for command lists recorded on a thread other than the one that submits them.
    def setEnableImmediateExecution(self: CommandListParameters, value: bool) -> CommandListParameters: ...
    # Which queue a command list built from these parameters submits to. Requires the device to
    # have been created with DeviceCreationParameters.enableComputeQueue for CommandQueue.Compute.
    def setQueueType(self: CommandListParameters, value: CommandQueue) -> CommandListParameters: ...
    # WARNING: this stores a RAW, NON-OWNING pointer (nvrhi.h:3135). Keep your own reference to
    # the tracker for as long as any command list created from these parameters is alive --
    # letting it be collected is a use-after-free, not a Python exception. None means "use the
    # device's own internal trackers", which is the default.
    def setLifetimeTracker(self: CommandListParameters, value: CommandListLifetimeTracker | None) -> CommandListParameters: ...

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
    def clearTextureFloat(self: CommandList, texture: Texture, clearColor: Color, view: IView) -> None: ...
    # Integer-texture counterpart of clearTextureFloat. Picking clears its RG16_UINT target to
    # 0xffff so "nothing hit" is distinguishable from material 0.
    @overload
    def clearTextureUInt(self: CommandList, texture: Texture, clearValue: int) -> None: ...
    @overload
    def clearTextureUInt(self: CommandList, texture: Texture, clearValue: int, view: IView) -> None: ...
    @overload
    def clearDepthStencilTexture(self: CommandList, texture: Texture, clearDepth: bool, depth: float, clearStencil: bool, stencil: int) -> None: ...
    @overload
    def clearDepthStencilTexture(self: CommandList, texture: Texture, clearDepth: bool, depth: float, clearStencil: bool, stencil: int, view: IView) -> None: ...
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
    def createCommandListLifetimeTracker(self: Device, executionQueue: CommandQueue) -> CommandListLifetimeTracker: ...
    def createGraphicsPipeline(self: Device, desc: GraphicsPipelineDesc, framebufferInfo: FramebufferInfo) -> GraphicsPipeline: ...
    def createMeshletPipeline(self: Device, desc: MeshletPipelineDesc, framebufferInfo: FramebufferInfo) -> MeshletPipeline: ...
    def executeCommandList(self: Device, commandList: CommandList, executionQueue: CommandQueue = CommandQueue.Graphics) -> int: ...
    # Batched, atomic submission of multiple command lists in one call (e.g. several per-thread
    # command lists plus a composite one), as opposed to executeCommandList's one-at-a-time
    # submission.
    def executeCommandLists(self: Device, commandLists: list[CommandList], executionQueue: CommandQueue = CommandQueue.Graphics) -> int: ...
    # Makes waitQueue block until submission `instance` on executionQueue has completed.
    # `instance` is the value executeCommandList returned for that submission.
    def queueWaitForCommandList(self: Device, waitQueue: CommandQueue, executionQueue: CommandQueue, instance: int) -> None: ...
    def createShader(self: Device, bytecode: bytes, entryName: str, shaderType: ShaderType) -> Shader | None: ...
    # Vulkan-only (nvrhi::Feature.ShaderSpecializations): bakes spec-constant overrides into a
    # new shader derived from baseShader.
    def createShaderSpecialization(self: Device, baseShader: Shader, constants: list[ShaderSpecialization]) -> Shader | None: ...
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
    def createShaderLibrary(self: Device, bytecode: bytes) -> ShaderLibrary | None: ...
    def waitForIdle(self: Device) -> None: ...
    def runGarbageCollection(self: Device) -> None: ...
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
    def CreateShader(self: ShaderFactory, fileName: str, entryName: str, shaderType: ShaderType) -> Shader | None: ...
    def CreateShaderLibrary(self: ShaderFactory, fileName: str) -> ShaderLibrary | None: ...
    # Drops the bytecode cache, so shaders created after it re-read their .bin blobs from
    # disk. Recreating the passes that hold the already-compiled pipelines is the caller's
    # job -- see feature_demo.py's ReloadShaders.
    def ClearCache(self: ShaderFactory) -> None: ...

# Maps binding set descriptors to binding set objects, creating them on demand. All methods are
# thread-safe (BindingCache.h:38), so one cache can serve several threads -- though a cache per
# thread avoids lock contention entirely, which is what async_compute.py does.
class BindingCache():
    def __init__(self: BindingCache, device: Device) -> None: ...
    def GetOrCreateBindingSet(self: BindingCache, desc: BindingSetDesc, layout: BindingLayout) -> BindingSet: ...
    def Clear(self: BindingCache) -> None: ...

# Only the fields threaded_rendering.py needs are bound (targetBox/sourceBox/sourceMip/
# sourceFormat/sampler/blendState/blendConstantColor stay at their defaults).
class BlitParameters():
    def __init__(self: BlitParameters) -> None: ...
    targetFramebuffer: Framebuffer | None
    targetViewport: Viewport
    sourceTexture: Texture | None
    sourceArraySlice: int

class CommonRenderPasses():
    def __init__(self: CommonRenderPasses, device: Device, shaderFactory: ShaderFactory) -> None: ...
    @overload
    def BlitTexture(self: CommonRenderPasses, commandList: CommandList, targetFramebuffer: Framebuffer, sourceTexture: Texture, bindingCache: BindingCache | None = None) -> None: ...
    # BlitParameters overload: composites one source array slice into one specific viewport
    # region of the target framebuffer, rather than the whole thing.
    @overload
    def BlitTexture(self: CommonRenderPasses, commandList: CommandList, params: BlitParameters, bindingCache: BindingCache | None = None) -> None: ...
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
    # Loading-screen progress counters, written by the loading thread while a scene loads:
    # "requested" counts textures queued, "loaded" counts those whose pixels are decoded.
    def GetNumberOfLoadedTextures(self: TextureCache) -> int: ...
    def GetNumberOfRequestedTextures(self: TextureCache) -> int: ...
    def LoadTextureFromFile(self: TextureCache, path: Path, sRGB: bool, passes: CommonRenderPasses | None, commandList: CommandList) -> LoadedTexture: ...
    # Synchronous read+decode, but the GPU upload/mip generation is deferred to the
    # TextureCache's own queue (drained by ProcessRenderingThreadCommands/SceneLoaded) --
    # for loading extra standalone textures outside the scene's own material set (see
    # rt_particles.py's particle/environment-map textures).
    def LoadTextureFromFileDeferred(self: TextureCache, path: Path, sRGB: bool) -> LoadedTexture: ...

class LoadedTexture():
    texture: Texture | None
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
    indexBuffer: Buffer | None
    vertexBuffer: Buffer | None
    instanceBuffer: Buffer | None
    def setVertexBufferRange(self: BufferGroup, attr: VertexAttribute, byteOffset: int, byteSize: int) -> None: ...
    def getVertexBufferRange(self: BufferGroup, attr: VertexAttribute) -> BufferRange: ...
    # Bindless table entries for this buffer group's raw index/vertex buffers (see
    # DescriptorTableManager.CreateDescriptorHandle) -- needed for procedural geometry whose
    # shaders look up vertex data via a bindless buffer index rather than a directly-bound SRV
    # (see rt_particles.py).
    indexBufferDescriptor: DescriptorHandle | None
    vertexBufferDescriptor: DescriptorHandle | None

# All six of Donut's real domains (SceneTypes.h:171-181) -- Count is a sentinel, not a real
# domain, and stays unbound.
class MaterialDomain(Enum):
    Opaque = 0
    AlphaTested = 1
    AlphaBlended = 2
    Transmissive = 3
    TransmissiveAlphaTested = 4
    TransmissiveAlphaBlended = 5

class Material():
    def __init__(self: Material) -> None: ...
    name: str
    domain: MaterialDomain
    # Read-only: assigned by the scene graph, and only read back for the material editor
    # window's header. Stage 3's MaterialID pass resolves picking to this value.
    materialID: int
    # Set by the app to make Scene.Refresh()/FinishedLoading() re-upload the material's
    # constant buffer -- e.g. after swapping baseOrDiffuseTexture (see rt_particles.py).
    dirty: bool
    useSpecularGlossModel: bool
    enableBaseOrDiffuseTexture: bool
    baseOrDiffuseTexture: LoadedTexture | None
    metalRoughOrSpecularTexture: LoadedTexture | None
    normalTexture: LoadedTexture | None
    emissiveTexture: LoadedTexture | None
    occlusionTexture: LoadedTexture | None
    transmissionTexture: LoadedTexture | None
    opacityTexture: LoadedTexture | None
    materialConstants: Buffer | None

# Wraps Material.FillConstantBuffer() -- the generated MaterialConstants shader-cbuffer
# struct isn't otherwise exposed to Python.
def CreateMaterialConstantBuffer(device: Device, commandList: CommandList, material: Material) -> Buffer: ...

class MeshGeometry():
    def __init__(self: MeshGeometry) -> None: ...
    material: Material | None
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
    buffers: BufferGroup | None
    totalIndices: int
    totalVertices: int
    indexOffset: int
    vertexOffset: int
    geometries: list[MeshGeometry]
    def SetObjectSpaceBounds(self: MeshInfo, minX: float, minY: float, minZ: float, maxX: float, maxY: float, maxZ: float) -> None: ...
    # "For use by applications" per the engine itself -- lets an app cache each mesh's bottom-
    # level acceleration structure directly on the mesh (build BLASes once, look them up per
    # instance when building the TLAS).
    accelStruct: AccelStruct | None
    # Set on the template mesh a skinned instance was cloned from -- see
    # SceneGraph.GetSkinnedMeshInstances()/SkinnedMeshInstance.GetPrototypeMesh(). isSkinPrototype
    # marks that template itself (never instantiated/ray-traced directly; skip it when building
    # BLASes -- see rt_bindless.py's CreateAccelStructs).
    isSkinPrototype: bool
    skinPrototype: MeshInfo | None

class SceneGraphLeaf():
    # Only takes effect once this leaf is attached to a scene-graph node (SceneGraph.cpp:40-47)
    # -- SceneGraphLeaf::SetName silently no-ops before that, and with asserts compiled out in
    # this project's Release build there is nothing to catch the mistake at the call site.
    def SetName(self: SceneGraphLeaf, name: str) -> None: ...
    # Read back by feature_demo.py's light dropdown to label each entry. Same attach-first
    # requirement as SetName: returns "" if the leaf isn't attached yet.
    def GetName(self: SceneGraphLeaf) -> str: ...
    # The node this leaf is attached to, as an owning handle -- None if it is not attached.
    # MeshInstance.GetNode() returns a raw non-owning pointer; use this one to store a node
    # across frames, as picking does.
    def GetNodeSharedPtr(self: SceneGraphLeaf) -> SceneGraphNode | None: ...

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
    # Flat scalars, like SetDirection -- donut math types never cross into Python. Both require
    # the light to be attached to a scene graph first: Light::SetPosition and SetDirection
    # assert when the light has no node (SceneTypes.cpp:82, :100). They do not clobber each
    # other; SetDirection writes only rotation and scaling.
    def SetPosition(self: Light, x: float, y: float, z: float) -> None: ...
    # Setter only, matching SkyParameters' float3 fields -- nothing reads a colour back, and
    # LightEditor writes the field from C++.
    def SetColor(self: Light, r: float, g: float, b: float) -> None: ...
    # Raw bytes of the engine's LightConstants struct, ready for CommandList.writeBuffer --
    # same pattern as PlanarView.FillPlanarViewConstants.
    def FillLightConstants(self: Light) -> bytes: ...
    # Assigning this is the entire shadow wiring -- both lighting passes read it themselves.
    # None means "this light casts no shadow", and is how a shadow toggle is implemented.
    shadowMap: IShadowMap | None

class DirectionalLight(Light):
    def __init__(self: DirectionalLight) -> None: ...
    irradiance: float
    angularSize: float

# A cone light. Angles are in degrees (Donut converts to radians when filling the light
# constants); range = 0 means infinite range. Position and direction come from the owning
# scene-graph node -- set them with Light.SetPosition/SetDirection *after* attaching.
class SpotLight(Light):
    def __init__(self: SpotLight) -> None: ...
    intensity: float
    radius: float
    range: float
    innerAngle: float
    outerAngle: float

# An omnidirectional light. range = 0 means infinite range. Position comes from the owning
# scene-graph node -- set it with Light.SetPosition *after* attaching.
class PointLight(Light):
    def __init__(self: PointLight) -> None: ...
    intensity: float
    radius: float
    range: float

# A camera stored in the scene graph. Abstract (SceneGraphLeaf.Clone is pure and SceneCamera
# does not override it), so it cannot be constructed -- it exists so GetCameras() can return
# concrete subtypes and SwitchableCamera.SwitchToSceneCamera can accept them. Its position and
# orientation come from the owning scene-graph node.
class SceneCamera(SceneGraphLeaf):
    # The camera's WORLD position, taken from the view-to-world translation. FeatureDemo.cpp:1351
    # reads the world-to-VIEW translation for the same purpose, which is -R*p and therefore wrong
    # for any rotated camera; this is the deliberate correction.
    def GetPosition(self: SceneCamera) -> tuple[float, float, float]: ...

# A perspective scene camera. verticalFov is in RADIANS, unlike SpotLight's degrees. zFar and
# aspectRatio are left unbound, so the projection is reverse-infinite and takes the viewport's
# aspect ratio. Position and direction come from the owning scene-graph node: place it with
# SceneGraphNode.SetPositionAndDirection on the node AttachLeafNode returns. Light's own
# SetPosition/SetDirection are declared on Light, so a camera does not inherit them.
class PerspectiveCamera(SceneCamera):
    def __init__(self: PerspectiveCamera) -> None: ...
    zNear: float
    verticalFov: float

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
    # Marks this node's subtree as needing its content re-evaluated -- called on the root when
    # a material changes domain, since that moves its geometry between draw lists.
    def InvalidateContent(self: SceneGraphNode) -> None: ...
    # Places the node at a world position, oriented along a world direction -- what
    # Light.SetPosition/SetDirection do, lifted to the node because those two are declared on
    # Light and so are unavailable on a SceneCamera. Call it *after* attaching the node: it
    # reads the parent's transform to convert world space to parent-local.
    def SetPositionAndDirection(self: SceneGraphNode, px: float, py: float, pz: float, dx: float, dy: float, dz: float) -> None: ...
    # The world-space translation component of this node's world transform, as (x, y, z) --
    # math types aren't exposed to Python (see rt_particles.py's emitter-position lookup).
    def GetWorldPosition(self: SceneGraphNode) -> tuple[float, float, float]: ...
    # World-space bounding box as (minX, minY, minZ, maxX, maxY, maxZ) -- dm::box3 is not
    # exposed. A node with no content carries box3::empty(): mins = FLT_MAX, maxs = -FLT_MAX,
    # so mins > maxs. Check for that before deriving a radius from it.
    def GetGlobalBoundingBox(self: SceneGraphNode) -> tuple[float, float, float, float, float, float]: ...
    # Slash-separated path from the scene-graph root, on every platform.
    def GetPath(self: SceneGraphNode) -> str: ...

class SceneGraph():
    def __init__(self: SceneGraph) -> None: ...
    # Returns the *previous* root node (None on a fresh graph), not the node just passed in --
    # use GetRootNode() to retrieve the node you just set. (SceneGraph.cpp:670-679)
    def SetRootNode(self: SceneGraph, root: SceneGraphNode) -> SceneGraphNode | None: ...
    def GetRootNode(self: SceneGraph) -> SceneGraphNode: ...
    # If `leaf` is already attached to a node elsewhere, this clones it (SceneGraph.cpp:844-847)
    # instead of moving it, so the returned node does not always wrap the same Python `leaf`
    # object passed in -- fine as long as each leaf is only ever attached once.
    def AttachLeafNode(self: SceneGraph, parent: SceneGraphNode, leaf: SceneGraphLeaf) -> SceneGraphNode: ...
    def Refresh(self: SceneGraph, frameIndex: int) -> None: ...
    def GetLights(self: SceneGraph) -> list[Light]: ...
    # Scene cameras attached anywhere in the graph -- populated by AttachLeafNode, the same
    # way GetLights is.
    def GetCameras(self: SceneGraph) -> list[SceneCamera]: ...
    def GetMeshes(self: SceneGraph) -> list[MeshInfo]: ...
    # Materials referenced by the graph's meshes. Empty on a graph with no meshes: materials
    # register through mesh geometry, not as scene-graph leaves.
    def GetMaterials(self: SceneGraph) -> list[Material]: ...
    def GetMeshInstances(self: SceneGraph) -> list[MeshInstance]: ...
    # Baked animation clips attached anywhere in the graph (see SceneGraphAnimation).
    def GetAnimations(self: SceneGraph) -> list[SceneGraphAnimation]: ...
    # Skinned (animated) mesh instances -- see SkinnedMeshInstance.
    def GetSkinnedMeshInstances(self: SceneGraph) -> list[SkinnedMeshInstance]: ...
    # Searches from the graph root (context is always null in this codebase).
    def FindNode(self: SceneGraph, path: Path) -> SceneGraphNode | None: ...

# Live progress counters shared by every in-flight scene load, from Scene.GetLoadingStats().
# Read from the render thread while the loading thread writes them.
class SceneLoadingStats():
    @property
    def ObjectsTotal(self: SceneLoadingStats) -> int: ...
    @property
    def ObjectsLoaded(self: SceneLoadingStats) -> int: ...

class Scene():
    def __init__(self: Scene, device: Device, shaderFactory: ShaderFactory, fs: IFileSystem, textureCache: TextureCache, descriptorTable: DescriptorTableManager | None) -> None: ...
    # Releases the GIL while loading, so this can run on ApplicationBase's scene-loading
    # thread (BeginLoadingScene) without blocking the render thread's splash screen.
    def Load(self: Scene, sceneFileName: Path) -> bool: ...
    @staticmethod
    def GetLoadingStats() -> SceneLoadingStats: ...
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
    # (x, y, z) -- math types aren't exposed to Python. A light probe captures at the active
    # camera's position.
    def GetPosition(self: BaseCamera) -> tuple[float, float, float]: ...

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

# Bundles a first-person camera, a third-person camera and an optional scene camera, owning the
# switching between them, the copy-the-view-across-a-switch behaviour, and the routing of input
# to whichever user camera is active. The *Update methods return False when a scene camera is
# active, which is how the example gates input without tracking the active camera itself.
#
# NOTE: a fresh SwitchableCamera is in THIRD person. Call SwitchToFirstPerson(copyView=False)
# to start first-person -- with copyView=True it would copy from the default-constructed
# third-person camera and overwrite whatever LookAt follows.
class SwitchableCamera:
    def __init__(self: SwitchableCamera) -> None: ...
    def SwitchToFirstPerson(self: SwitchableCamera, copyView: bool = True) -> None: ...
    def SwitchToThirdPerson(self: SwitchableCamera, copyView: bool = True) -> None: ...
    # Raises ValueError on None: the C++ guards it with an assert that compiles out in this
    # project's Release build.
    def SwitchToSceneCamera(self: SwitchableCamera, sceneCamera: SceneCamera) -> None: ...
    def IsFirstPersonActive(self: SwitchableCamera) -> bool: ...
    def IsThirdPersonActive(self: SwitchableCamera) -> bool: ...
    def IsSceneCameraActive(self: SwitchableCamera) -> bool: ...
    def GetSceneCamera(self: SwitchableCamera) -> SceneCamera | None: ...
    # Both return the camera owned by this SwitchableCamera, not a copy -- writes through the
    # returned object stick.
    def GetFirstPersonCamera(self: SwitchableCamera) -> FirstPersonCamera: ...
    def GetThirdPersonCamera(self: SwitchableCamera) -> ThirdPersonCamera: ...
    def KeyboardUpdate(self: SwitchableCamera, key: int, scancode: int, action: int, mods: int) -> bool: ...
    def MousePosUpdate(self: SwitchableCamera, xpos: float, ypos: float) -> bool: ...
    def MouseButtonUpdate(self: SwitchableCamera, button: int, action: int, mods: int) -> bool: ...
    def MouseScrollUpdate(self: SwitchableCamera, xoffset: float, yoffset: float) -> bool: ...
    def Animate(self: SwitchableCamera, deltaT: float) -> None: ...
    # The owned first- or third-person camera, whichever is active -- a live reference, not a
    # copy. Returns the last-active USER camera even when a scene camera is active; check
    # IsSceneCameraActive() first if that matters.
    def GetActiveUserCamera(self: SwitchableCamera) -> BaseCamera: ...

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
    # Like SetMatricesFromCamera, but for a SwitchableCamera, which may be driving a scene
    # camera rather than a BaseCamera. When a perspective scene camera is active its own
    # verticalFov and zNear override the arguments passed here.
    def SetMatricesFromSwitchableCamera(self: PlanarView, camera: SwitchableCamera, aspectRatio: float, verticalFovRadians: float = ..., zNear: float = 0.1) -> None: ...
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

# Two PlanarViews side by side, with the composite-view interface fanning out over both. Used
# for the split-viewport stereo mode; no stereo hardware involved.
#
# Most IView matrix accessors are assert(false) + identity on this type and are deliberately
# not bound -- asserts compile out in this project's Release build, so they would fail silently.
# GetViewFrustum and GetProjectionFrustum ARE meaningfully overridden and reach C++ through the
# pass signatures.
class StereoPlanarView(IView):
    @overload
    def __init__(self: StereoPlanarView) -> None: ...
    # Copy constructor, mirroring PlanarView's: how Python snapshots this frame's view as next
    # frame's previous view.
    @overload
    def __init__(self: StereoPlanarView, other: StereoPlanarView) -> None: ...
    # Live references into the stereo view, not copies -- writes through them persist.
    @property
    def LeftView(self: StereoPlanarView) -> PlanarView: ...
    @property
    def RightView(self: StereoPlanarView) -> PlanarView: ...
    # One shared projection; the right eye's view matrix is the left's translated along X.
    # `aspectRatio` is the PER-EYE ratio -- pass width / height * 0.5, since each eye owns half
    # the framebuffer width. Call UpdateCache() on each eye afterwards: StereoPlanarView has
    # none of its own.
    def SetMatricesFromSwitchableCamera(self: StereoPlanarView, camera: SwitchableCamera, aspectRatio: float, eyeSeparation: float = 0.2, verticalFovRadians: float = ..., zNear: float = 0.1) -> None: ...

# Splits one transform into 6 face view/proj matrices for cube-map/environment rendering. Its
# faces are plain PlanarView instances internally, so GetFaceView returns the existing
# PlanarView type rather than a new view hierarchy.
class CubemapView(IView):
    def __init__(self: CubemapView) -> None: ...
    def SetTransformFromCamera(self: CubemapView, camera: FirstPersonCamera, zNear: float, cullDistance: float, useReverseInfiniteProjections: bool = True) -> None: ...
    # The probe-capture form: builds dm::translation(-position) internally, since CubemapView.
    # SetTransform takes a dm::affine3 and the only one the caller ever wants is that.
    def SetTransformFromPosition(self: CubemapView, x: float, y: float, z: float, zNear: float, cullDistance: float, useReverseInfiniteProjections: bool = True) -> None: ...
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
    def GetFramebuffer(self: GBufferRenderTargets, view: IView) -> Framebuffer: ...
    # Public texture handles from GBuffer.h. All None until Init() has been called.
    Depth: Texture | None
    GBufferDiffuse: Texture | None
    GBufferSpecular: Texture | None
    GBufferNormals: Texture | None
    GBufferEmissive: Texture | None
    MotionVectors: Texture | None
    GBufferFramebuffer: FramebufferFactory | None
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

# Writes material and instance IDs instead of a full gbuffer -- the pass right-click picking
# renders through. Derives from GBufferFillPass and reuses its create-parameters and context
# types; the C++ declares none of its own.
class MaterialIDPass(GBufferFillPass):
    def __init__(self: MaterialIDPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: MaterialIDPass, shaderFactory: ShaderFactory, params: GBufferFillPassCreateParameters) -> None: ...

# Copies one pixel into a readback buffer. Capture records the copy; the Read* methods are only
# valid once that command list has executed. `format` is the readback buffer's layout, NOT the
# source texture's -- FeatureDemo pairs an RG16_UINT texture with an RGBA32_UINT readback.
class PixelReadbackPass():
    def __init__(self: PixelReadbackPass, device: Device, shaderFactory: ShaderFactory, inputTexture: Texture, format: Format, arraySlice: int = 0, mipLevel: int = 0) -> None: ...
    # dm::uint2 flattened to two ints, matching PlanarView.SetPixelOffset.
    def Capture(self: PixelReadbackPass, commandList: CommandList, x: int, y: int) -> None: ...
    def ReadUInts(self: PixelReadbackPass) -> tuple[int, int, int, int]: ...
    def ReadFloats(self: PixelReadbackPass) -> tuple[float, float, float, float]: ...
    def ReadInts(self: PixelReadbackPass) -> tuple[int, int, int, int]: ...

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

# engine::LightProbe (SceneTypes.h:356-371) -- image-based ambient light captured from a point
# in the scene. Held by shared_ptr in C++; both lighting passes take a list of them.
#
# `bounds` (a dm::frustum) is not a property: donut math types never cross into Python, and the
# only uses are constructions, never reads. The three SetBounds* methods cover them. Bounds are
# load-bearing -- IsActive() rejects an empty frustum, so an uncaptured probe stays dark.
class LightProbe():
    def __init__(self: LightProbe) -> None: ...
    name: str
    diffuseMap: Texture | None
    specularMap: Texture | None
    environmentBrdf: Texture | None
    # Slice indices into the shared cube-map ARRAYS. The pass multiplies by 6 at the call site.
    diffuseArrayIndex: int
    specularArrayIndex: int
    diffuseScale: float
    specularScale: float
    enabled: bool
    # enabled AND non-empty bounds AND at least one map with a non-zero scale.
    def IsActive(self: LightProbe) -> bool: ...
    def SetBoundsEmpty(self: LightProbe) -> None: ...
    def SetBoundsInfinite(self: LightProbe) -> None: ...
    def SetBoundsFromBox(self: LightProbe, minX: float, minY: float, minZ: float, maxX: float, maxY: float, maxZ: float) -> None: ...

class DeferredLightingPassInputs():
    def __init__(self: DeferredLightingPassInputs) -> None: ...
    def SetGBuffer(self: DeferredLightingPassInputs, targets: GBufferRenderTargets) -> None: ...
    def SetAmbientColors(self: DeferredLightingPassInputs, topR: float, topG: float, topB: float, bottomR: float, bottomG: float, bottomB: float) -> None: ...
    def SetLights(self: DeferredLightingPassInputs, lights: list[Light]) -> None: ...
    # Every probe in one call must share diffuseMap, specularMap and environmentBrdf --
    # DeferredLightingPass::Render logs an error and returns without rendering otherwise
    # (DeferredLightingPass.cpp:246-253). An empty list is the off switch.
    def SetLightProbes(self: DeferredLightingPassInputs, lightProbes: list[LightProbe]) -> None: ...
    output: Texture | None
    # None disables the SSAO term. Only ever set when sampleCount == 1 -- SsaoPass does not
    # exist under MSAA.
    ambientOcclusion: Texture | None

class DeferredLightingPass():
    def __init__(self: DeferredLightingPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: DeferredLightingPass, shaderFactory: ShaderFactory) -> None: ...
    def Render(self: DeferredLightingPass, commandList: CommandList, view: ICompositeView, inputs: DeferredLightingPassInputs) -> None: ...
    def ResetBindingCache(self: DeferredLightingPass) -> None: ...

class ForwardShadingPassCreateParameters():
    def __init__(self: ForwardShadingPassCreateParameters) -> None: ...
    # Default 16; raise for multi-threaded recording (each concurrently-recorded command list
    # consumes its own volatile constant buffer version).
    numConstantBufferVersions: int
    # Renders all six cube faces in one geometry-shader pass instead of six draws. Only
    # meaningful when the device reports Feature.FastGeometryShader.
    singlePassCubemap: bool

class ForwardShadingPassContext(GeometryPassContext):
    def __init__(self: ForwardShadingPassContext) -> None: ...

class ForwardShadingPass(IGeometryPass):
    def __init__(self: ForwardShadingPass, device: Device, commonPasses: CommonRenderPasses) -> None: ...
    def Init(self: ForwardShadingPass, shaderFactory: ShaderFactory, params: ForwardShadingPassCreateParameters) -> None: ...
    def ResetBindingCache(self: ForwardShadingPass) -> None: ...
    # lightProbes is trailing and defaulted: the nine-argument form used by variable_shading.py,
    # threaded_rendering.py, and rt_reflections.py still works.
    def PrepareLights(self: ForwardShadingPass, context: ForwardShadingPassContext, commandList: CommandList, lights: list[Light], topR: float, topG: float, topB: float, bottomR: float, bottomG: float, bottomB: float, lightProbes: list[LightProbe] = ...) -> None: ...

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
    sourceDepth: Texture | None
    motionVectors: Texture | None
    unresolvedColor: Texture | None
    resolvedColor: Texture | None
    feedback1: Texture | None
    feedback2: Texture | None
    useCatmullRomFilter: bool
    motionVectorStencilMask: int
    numConstantBufferVersions: int
    def __init__(self: TemporalAntiAliasingCreateParameters) -> None: ...

class TemporalAntiAliasingPass():
    def __init__(self: TemporalAntiAliasingPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, compositeView: ICompositeView, params: TemporalAntiAliasingCreateParameters) -> None: ...
    def RenderMotionVectors(self: TemporalAntiAliasingPass, commandList: CommandList, compositeView: ICompositeView, compositeViewPrevious: ICompositeView) -> None: ...
    def TemporalResolve(self: TemporalAntiAliasingPass, commandList: CommandList, params: TemporalAntiAliasingParameters, feedbackIsValid: bool, compositeViewInput: ICompositeView, compositeViewOutput: ICompositeView) -> None: ...
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

# MipMapGenPass::Mode, flattened to module scope. All four values bind -- a partial enum
# binding raises ValueError when C++ hands back an unbound one.
class MipMapGenPassMode(Enum):
    MODE_COLOR = 0
    MODE_MIN = 1
    MODE_MAX = 2
    MODE_MINMAX = 3

# Compute-shader mip-chain reduction. `texture` must already have been allocated with mip
# levels -- the pass binds one UAV per level at construction.
class MipMapGenPass():
    def __init__(self: MipMapGenPass, device: Device, shaderFactory: ShaderFactory, texture: Texture, mode: MipMapGenPassMode = ...) -> None: ...
    # Reads LOD 0 and populates LOD 1 and up. maxLOD = -1 means every level.
    def Dispatch(self: MipMapGenPass, commandList: CommandList, maxLOD: int = -1) -> None: ...
    # Debug only: blits the levels in a spiral over `target`, which must be large enough.
    def Display(self: MipMapGenPass, commonPasses: CommonRenderPasses, commandList: CommandList, target: Framebuffer) -> None: ...

# Turns a rendered environment cube map into the two maps a LightProbe samples -- a diffuse
# irradiance cube and a roughness-filtered specular cube -- plus the split-sum environment BRDF
# LUT shared by every probe (LightProbeProcessingPass.h:93-137).
#
# RenderDiffuseMap and RenderSpecularMap take no subresource-set argument: nvrhi::
# TextureSubresourceSet is not exposed to Python and both call sites want AllSubresources, which
# they pass internally. Same fold as clearTextureFloat and resolveTexture.
class LightProbeProcessingPass():
    def __init__(self: LightProbeProcessingPass, device: Device, shaderFactory: ShaderFactory, commonPasses: CommonRenderPasses, intermediateTextureSize: int = 1024, intermediateTextureFormat: Format = ...) -> None: ...
    # Bound for completeness; nothing in this repo calls it.
    def BlitCubemap(self: LightProbeProcessingPass, commandList: CommandList, inCubeMap: Texture, inBaseArraySlice: int, inMipLevel: int, outCubeMap: Texture, outBaseArraySlice: int, outMipLevel: int) -> None: ...
    def GenerateCubemapMips(self: LightProbeProcessingPass, commandList: CommandList, cubeMap: Texture, baseArraySlice: int, sourceMipLevel: int, levelsToGenerate: int) -> None: ...
    def RenderDiffuseMap(self: LightProbeProcessingPass, commandList: CommandList, inEnvironmentMap: Texture, outDiffuseMap: Texture, outBaseArraySlice: int, outMipLevel: int) -> None: ...
    # roughness precedes the source map, as in C++. The caller loops the specular mip chain,
    # computing roughness per level.
    def RenderSpecularMap(self: LightProbeProcessingPass, commandList: CommandList, roughness: float, inEnvironmentMap: Texture, outSpecularMap: Texture, outBaseArraySlice: int, outMipLevel: int) -> None: ...
    def RenderEnvironmentBrdfTexture(self: LightProbeProcessingPass, commandList: CommandList) -> None: ...
    # Owned by the pass -- it dies with the pass, which is why recreating the pass means
    # invalidating every probe holding this handle as its environmentBrdf.
    def GetEnvironmentBrdfTexture(self: LightProbeProcessingPass) -> Texture: ...
    def ResetCaches(self: LightProbeProcessingPass) -> None: ...

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
    exposureBufferOverride: Buffer | None
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
# Both setup calls take an IView rather than a frustum -- donut math types never cross into
# Python, and the two fits want different frustums off it (view frustum for the tight fit,
# projection frustum plus inverse view matrix for the stable one). Both return True if any
# cascade's view changed.
#
# numCascades must be in [1, 4] and exponent must be > 1. Donut only asserts both, and asserts
# are compiled out of the build this repo ships, so the bindings raise ValueError instead: an
# out-of-range cascade count makes the lighting passes write past LightConstants.shadowCascades
# (an int4), and exponent <= 1 breaks the cascade split solver -- both silently, in the image.
class CascadedShadowMap(IShadowMap):
    def __init__(self: CascadedShadowMap, device: Device, resolution: int, numCascades: int, numPerObjectShadows: int, format: Format, isUAV: bool = False) -> None: ...
    def SetupForPlanarView(self: CascadedShadowMap, light: DirectionalLight, view: IView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
    # Takes its inverse view matrix from a planar child view, not from `view` itself: a stereo
    # view's own GetInverseViewMatrix is assert(false) + identity, which is silent in Release.
    def SetupForPlanarViewStable(self: CascadedShadowMap, light: DirectionalLight, view: IView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
    # Cascades all centred on one point, for an omnidirectional view. Takes the view rather than
    # a centre and reads GetViewOrigin() off it, matching the two planar variants above.
    def SetupForCubemapView(self: CascadedShadowMap, light: DirectionalLight, view: IView, maxShadowDistance: float, lightSpaceZUp: float, lightSpaceZDown: float, exponent: float = 4.0) -> bool: ...
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
    depthTarget: Texture | None
    shadingRateSurface: Texture | None
    def GetFramebuffer(self: FramebufferFactory, view: IView) -> Framebuffer: ...

def RenderView(commandList: CommandList, view: IView, viewPrev: IView | None, framebuffer: Framebuffer, drawStrategy: IDrawStrategy, pass_: IGeometryPass, context: GeometryPassContext, materialEvents: bool = False) -> None: ...
# view is an ICompositeView, one step wider than RenderView's IView: CascadedShadowMap.GetView()
# returns a CompositeView, which derives from ICompositeView directly and is not an IView.
# passEvent names the pass in a graphics capture. It sits after materialEvents rather than in the
# C++ parameter order because existing callers pass materialEvents positionally.
def RenderCompositeView(commandList: CommandList, view: ICompositeView, viewPrev: ICompositeView | None, framebufferFactory: FramebufferFactory, rootNode: SceneGraphNode, drawStrategy: IDrawStrategy, pass_: IGeometryPass, passContext: GeometryPassContext, materialEvents: bool = False, passEvent: str | None = None) -> None: ...

# Writes slice 0, mip 0 of a texture to an image file; the format comes from the extension
# (BMP, PNG, JPG, TGA). Requires that no immediate command list be open, and creates and
# destroys temporary resources internally -- call it after executeCommandList, not per frame.
def SaveTextureToFile(device: Device, commonPasses: CommonRenderPasses, texture: Texture, textureState: ResourceStates, fileName: str, saveAlphaChannel: bool = True) -> bool: ...

# Native modal save/open dialog. Takes (description, pattern) pairs -- the C++ wants a
# double-NUL-terminated buffer, which cannot survive a str conversion -- and returns None when
# the user cancels. On Linux this shells out to `zenity`, so None also means "no dialog
# available"; callers needing a file regardless must supply their own fallback path.
# Blocking and modal: never call it from a test.
def FileDialog(bOpen: bool, filters: list[tuple[str, str]]) -> str | None: ...

class AdapterInfo():
    name: str
    vendorID: int
    deviceID: int
    dedicatedVideoMemory: int
    uuid: list[int] | None
    luid: list[int] | None

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
    # An undecorated, input-transparent window covering the whole viewport, for loading
    # screens and other overlays. Call only from buildUI(); Begin/End must be paired.
    def BeginFullScreenWindow(self: ImGui_Renderer) -> None: ...
    # Draws `text` centered in the full-screen window. Multi-line text is centered as one
    # block (its lines stay left-aligned within that block), not line by line.
    def DrawScreenCenteredText(self: ImGui_Renderer, text: str) -> None: ...
    def EndFullScreenWindow(self: ImGui_Renderer) -> None: ...

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
    # pivot places that point of the window at (x, y): (0, 0) is its top-left corner, (1, 0)
    # its top-right, which is how the material editor window right-aligns itself.
    @staticmethod
    def SetNextWindowPos(x: float, y: float, cond: int = 0, pivotX: float = 0.0, pivotY: float = 0.0) -> None: ...
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
    # CollapsingHeader does not push an ID scope (ImGuiTreeNodeFlags_CollapsingHeader includes
    # NoTreePushOnOpen), so two sections with same-named widgets (e.g. two "Radius" sliders)
    # share one ImGui ID and can drive each other's value while both are open. Wrap a section in
    # PushID/PopID to give its widgets a distinct ID namespace.
    @staticmethod
    def PushID(str_id: str) -> None: ...
    @staticmethod
    def PopID() -> None: ...

# Donut's built-in light editor: emits the controls appropriate to the light's concrete type
# and returns whether anything changed. It draws into the current ImGui window, so call it from
# inside a buildUI() override, between ImGui.Begin and ImGui.End.
def LightEditor(light: Light) -> bool: ...

# Donut's built-in material editor: emits the controls for the material's texture slots and
# constants and returns whether anything changed. Draws into the current ImGui window, so call
# it from inside a buildUI() override between ImGui.Begin and ImGui.End. When
# allowMaterialDomainChanges is True the editor may change material.domain, and the caller must
# then call InvalidateContent() on the scene graph's root node.
def MaterialEditor(material: Material, allowMaterialDomainChanges: bool) -> bool: ...

class PipelineCallbacks():
    beforeFrame: Callable[[DeviceManager, int], None] | None
    beforeAnimate: Callable[[DeviceManager, int], None] | None
    afterAnimate: Callable[[DeviceManager, int], None] | None
    beforeRender: Callable[[DeviceManager, int], None] | None
    afterRender: Callable[[DeviceManager, int], None] | None
    beforePresent: Callable[[DeviceManager, int], None] | None
    afterPresent: Callable[[DeviceManager, int], None] | None

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
    def SetInformativeWindowTitle(self: DeviceManager, applicationName: str, includeFramerate: bool = True, extraInfo: str | None = None) -> None: ...
    def GetWindowTitle(self: DeviceManager) -> str: ...
    def IsVulkanInstanceExtensionEnabled(self: DeviceManager, extensionName: str) -> bool: ...
    def IsVulkanDeviceExtensionEnabled(self: DeviceManager, extensionName: str) -> bool: ...
    def IsVulkanLayerEnabled(self: DeviceManager, layerName: str) -> bool: ...
    def GetEnabledVulkanInstanceExtensions(self: DeviceManager) -> list[str]: ...
    def GetEnabledVulkanDeviceExtensions(self: DeviceManager) -> list[str]: ...
    def GetEnabledVulkanLayers(self: DeviceManager) -> list[str]: ...
    def Shutdown(self: DeviceManager) -> None: ...
