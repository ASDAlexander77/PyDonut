from enum import Enum
from typing import Callable, Optional

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

def GetGraphicsAPIFromCommandLine(args: list[str]) -> GraphicsAPI: ...

# Opaque nvrhi resource handles: not constructible from Python, only obtained from
# and passed back into DeviceManager / IRenderPass calls.
class Framebuffer(): ...
class Texture(): ...
class Device(): ...

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
