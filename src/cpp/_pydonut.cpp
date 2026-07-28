#include <string>
#include <vector>
#include <memory>
#include <optional>
#include <filesystem>

#include <pybind11/pybind11.h>
#include <pybind11/native_enum.h>
#include <pybind11/stl.h>
#include <pybind11/stl/filesystem.h>
#include <pybind11/complex.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>

#include <donut/app/DeviceManager.h>
#include <donut/app/ApplicationBase.h>
#include <donut/app/Camera.h>
#include <donut/core/log.h>
#include <donut/core/vfs/VFS.h>
#include <donut/core/math/math.h>
#include <donut/engine/ShaderFactory.h>
#include <donut/engine/CommonRenderPasses.h>
#include <donut/engine/BindingCache.h>
#include <donut/engine/View.h>
#include <donut/engine/Scene.h>
#include <donut/engine/SceneGraph.h>
#include <donut/engine/TextureCache.h>
#include <donut/engine/DescriptorTableManager.h>
#include <nvrhi/utils.h>

#if PYDONUT_HAVE_DXC
#include <dxcapi.h>
#endif

// view_cb.h is a shared C++/HLSL header: its field types (float4x4, float2, ...) are
// donut::math types used unqualified, exactly as donut's own View.cpp includes it. Its
// PlanarViewConstants is forward-declared at GLOBAL scope in View.h (see the `struct
// PlanarViewConstants;` there), so this include -- and the using-directive it needs --
// must also sit at global scope for the two declarations to refer to the same type.
using namespace donut::math;
#include <donut/shaders/view_cb.h>

namespace py = pybind11;

namespace {

// Trampoline class so Python subclasses of IRenderPass can override its virtual methods.
class PyIRenderPass : public donut::app::IRenderPass {
public:
    using IRenderPass::IRenderPass;

    void SetLatewarpOptions() override {
        PYBIND11_OVERRIDE(void, IRenderPass, SetLatewarpOptions);
    }
    bool ShouldAnimateUnfocused() override {
        PYBIND11_OVERRIDE(bool, IRenderPass, ShouldAnimateUnfocused);
    }
    bool ShouldRenderUnfocused() override {
        PYBIND11_OVERRIDE(bool, IRenderPass, ShouldRenderUnfocused);
    }
    bool SupportsDepthBuffer() override {
        PYBIND11_OVERRIDE(bool, IRenderPass, SupportsDepthBuffer);
    }
    void Render(nvrhi::IFramebuffer* framebuffer) override {
        PYBIND11_OVERRIDE(void, IRenderPass, Render, framebuffer);
    }
    void Animate(float fElapsedTimeSeconds) override {
        PYBIND11_OVERRIDE(void, IRenderPass, Animate, fElapsedTimeSeconds);
    }
    void BackBufferResizing() override {
        PYBIND11_OVERRIDE(void, IRenderPass, BackBufferResizing);
    }
    void BackBufferResized(const uint32_t width, const uint32_t height, const uint32_t sampleCount) override {
        PYBIND11_OVERRIDE(void, IRenderPass, BackBufferResized, width, height, sampleCount);
    }
    void DisplayScaleChanged(float scaleX, float scaleY) override {
        PYBIND11_OVERRIDE(void, IRenderPass, DisplayScaleChanged, scaleX, scaleY);
    }
    bool KeyboardUpdate(int key, int scancode, int action, int mods) override {
        PYBIND11_OVERRIDE(bool, IRenderPass, KeyboardUpdate, key, scancode, action, mods);
    }
    bool KeyboardCharInput(unsigned int unicode, int mods) override {
        PYBIND11_OVERRIDE(bool, IRenderPass, KeyboardCharInput, unicode, mods);
    }
    bool MousePosUpdate(double xpos, double ypos) override {
        PYBIND11_OVERRIDE(bool, IRenderPass, MousePosUpdate, xpos, ypos);
    }
    bool MouseScrollUpdate(double xoffset, double yoffset) override {
        PYBIND11_OVERRIDE(bool, IRenderPass, MouseScrollUpdate, xoffset, yoffset);
    }
    bool MouseButtonUpdate(int button, int action, int mods) override {
        PYBIND11_OVERRIDE(bool, IRenderPass, MouseButtonUpdate, button, action, mods);
    }
    bool JoystickButtonUpdate(int button, bool pressed) override {
        PYBIND11_OVERRIDE(bool, IRenderPass, JoystickButtonUpdate, button, pressed);
    }
    bool JoystickAxisUpdate(int axis, float value) override {
        PYBIND11_OVERRIDE(bool, IRenderPass, JoystickAxisUpdate, axis, value);
    }
};

// Transfers ownership of an nvrhi RefCountPtr's single reference into a std::shared_ptr,
// releasing via nvrhi's own AddRef/Release rather than `delete` (nvrhi resources are refcounted).
template <typename T>
std::shared_ptr<T> DetachToShared(nvrhi::RefCountPtr<T> handle) {
    T* raw = handle.Detach();
    return std::shared_ptr<T>(raw, [](T* p) { if (p) p->Release(); });
}

#if PYDONUT_HAVE_DXC

// Minimal COM smart pointer, standing in for Microsoft::WRL::ComPtr (Windows-only,
// part of the Windows SDK) so this compiles against DXC's cross-platform COM-lite
// layer (WinAdapter.h) on Linux too -- DXC ships IUnknown/HRESULT/IID_PPV_ARGS etc.
// there, just not <wrl/client.h> itself.
template <typename T>
class ComPtr {
public:
    ComPtr() noexcept : ptr_(nullptr) {}
    ComPtr(const ComPtr &) = delete;
    ComPtr &operator=(const ComPtr &) = delete;
    ~ComPtr() { if (ptr_) ptr_->Release(); }

    T **operator&() noexcept {
        if (ptr_) { ptr_->Release(); ptr_ = nullptr; }
        return &ptr_;
    }
    T *operator->() const noexcept { return ptr_; }
    T *Get() const noexcept { return ptr_; }
    explicit operator bool() const noexcept { return ptr_ != nullptr; }

private:
    T *ptr_;
};

std::wstring ToWide(const std::string &s) {
    return std::wstring(s.begin(), s.end());
}

const wchar_t* HlslProfilePrefix(nvrhi::ShaderType shaderType) {
    switch (shaderType) {
        case nvrhi::ShaderType::Vertex:        return L"vs";
        case nvrhi::ShaderType::Hull:           return L"hs";
        case nvrhi::ShaderType::Domain:          return L"ds";
        case nvrhi::ShaderType::Geometry:        return L"gs";
        case nvrhi::ShaderType::Pixel:            return L"ps";
        case nvrhi::ShaderType::Compute:          return L"cs";
        case nvrhi::ShaderType::Amplification:    return L"as";
        case nvrhi::ShaderType::Mesh:              return L"ms";
        default:
            throw std::invalid_argument(
                "CompileShader: shaderType must be one of Vertex, Hull, Domain, Geometry, Pixel, Compute, Amplification or Mesh");
    }
}

// Shared DXC invocation: runs the compiler with the given command-line args over `source`
// and returns the resulting object blob, or throws with DXC's diagnostic text on failure.
py::bytes RunDXC(const std::string &source, std::vector<LPCWSTR> args)
{
    ComPtr<IDxcUtils> utils;
    ComPtr<IDxcCompiler3> compiler;
    if (FAILED(DxcCreateInstance(CLSID_DxcUtils, IID_PPV_ARGS(&utils))) ||
        FAILED(DxcCreateInstance(CLSID_DxcCompiler, IID_PPV_ARGS(&compiler))))
        throw std::runtime_error("CompileShader: failed to create the DXC compiler instance");

    ComPtr<IDxcIncludeHandler> includeHandler;
    utils->CreateDefaultIncludeHandler(&includeHandler);

    DxcBuffer sourceBuffer{};
    sourceBuffer.Ptr = source.data();
    sourceBuffer.Size = source.size();
    sourceBuffer.Encoding = DXC_CP_UTF8;

    ComPtr<IDxcResult> result;
    HRESULT hr = compiler->Compile(&sourceBuffer, args.data(), (UINT32)args.size(), includeHandler.Get(), IID_PPV_ARGS(&result));
    if (FAILED(hr) || !result)
        throw std::runtime_error("CompileShader: the DXC Compile() call itself failed");

    ComPtr<IDxcBlobUtf8> errors;
    result->GetOutput(DXC_OUT_ERRORS, IID_PPV_ARGS(&errors), nullptr);

    HRESULT status = S_OK;
    result->GetStatus(&status);
    if (FAILED(status)) {
        std::string message = "CompileShader: shader compilation failed";
        if (errors && errors->GetStringLength() > 0)
            message = std::string(errors->GetStringPointer(), errors->GetStringLength());
        throw std::runtime_error(message);
    }

    ComPtr<IDxcBlob> object;
    result->GetOutput(DXC_OUT_OBJECT, IID_PPV_ARGS(&object), nullptr);
    if (!object || object->GetBufferSize() == 0)
        throw std::runtime_error("CompileShader: DXC produced no output object");

    return py::bytes(reinterpret_cast<const char*>(object->GetBufferPointer()), object->GetBufferSize());
}

// NVRHI's default VulkanBindingOffsets (see nvrhi::BindingLayoutDesc::bindingOffsets in
// nvrhi.h) place HLSL's separate t/s/b/u register spaces into disjoint Vulkan binding
// number ranges -- Vulkan has one flat binding namespace per descriptor set, unlike
// DX's separate SRV/Sampler/CBV/UAV register classes. DXC must be told to apply the same
// shifts when cross-compiling to SPIR-V, or e.g. t0 and u0 both land on binding 0 and
// collide (this is exactly what the Vulkan validation layer flags if omitted).
void AddVulkanBindingShiftArgs(std::vector<LPCWSTR> &args) {
    args.push_back(L"-fvk-t-shift"); args.push_back(L"0");   args.push_back(L"0");
    args.push_back(L"-fvk-s-shift"); args.push_back(L"128"); args.push_back(L"0");
    args.push_back(L"-fvk-b-shift"); args.push_back(L"256"); args.push_back(L"0");
    args.push_back(L"-fvk-u-shift"); args.push_back(L"384"); args.push_back(L"0");
}

// Appends "-I <path>" for each entry so #include <...> in the source can resolve
// against donut's shared C++/HLSL header directories (e.g. donut/shaders/*.h). The
// wstring conversions are appended to `storage` so their backing memory outlives `args`.
void AddIncludePathArgs(std::vector<LPCWSTR> &args, const std::vector<std::string> &includePaths, std::vector<std::wstring> &storage) {
    for (const auto &path : includePaths) {
        storage.push_back(ToWide(path));
        args.push_back(L"-I");
        args.push_back(storage.back().c_str());
    }
}

// Compiles HLSL source to DXIL (D3D12) or SPIR-V (Vulkan) in-process via DXC, entirely
// in memory -- no ShaderMake, no external process, no filesystem round-trip.
py::bytes CompileShaderWithDXC(
    const std::string &source,
    const std::string &entryPoint,
    nvrhi::ShaderType shaderType,
    nvrhi::GraphicsAPI api,
    const std::string &sourceName,
    const std::string &shaderModel,
    const std::vector<std::string> &includePaths)
{
    std::wstring wEntryPoint = ToWide(entryPoint);
    std::wstring wProfile = std::wstring(HlslProfilePrefix(shaderType)) + L"_" + ToWide(shaderModel);
    std::wstring wSourceName = ToWide(sourceName);

    std::vector<LPCWSTR> args = {
        wSourceName.c_str(),
        L"-E", wEntryPoint.c_str(),
        L"-T", wProfile.c_str(),
    };
    if (api == nvrhi::GraphicsAPI::VULKAN) {
        args.push_back(L"-spirv");
        AddVulkanBindingShiftArgs(args);
    }
    std::vector<std::wstring> includePathStorage;
    AddIncludePathArgs(args, includePaths, includePathStorage);

    return RunDXC(source, args);
}

// Compiles an HLSL shader library (multiple [shader("...")]-annotated exports, e.g. a
// DXR raygen/closesthit/miss set) to a single DXIL or SPIR-V library blob via DXC. Unlike
// CompileShaderWithDXC, there's no single entry point -- DXC exports whatever [shader(...)]
// functions the source defines, which nvrhi::IDevice::createShaderLibrary then wraps.
py::bytes CompileShaderLibraryWithDXC(
    const std::string &source,
    nvrhi::GraphicsAPI api,
    const std::string &sourceName,
    const std::string &shaderModel,
    const std::vector<std::string> &includePaths)
{
    std::wstring wProfile = L"lib_" + ToWide(shaderModel);
    std::wstring wSourceName = ToWide(sourceName);

    std::vector<LPCWSTR> args = {
        wSourceName.c_str(),
        L"-T", wProfile.c_str(),
    };
    if (api == nvrhi::GraphicsAPI::VULKAN) {
        // Ray tracing needs SPIR-V 1.4+ / Vulkan 1.1+, above DXC's default target env.
        args.push_back(L"-spirv");
        args.push_back(L"-fspv-target-env=vulkan1.2");
        AddVulkanBindingShiftArgs(args);
    }
    std::vector<std::wstring> includePathStorage;
    AddIncludePathArgs(args, includePaths, includePathStorage);

    return RunDXC(source, args);
}

#endif // PYDONUT_HAVE_DXC

// Static wrapper around the donut::log free functions, exposed to Python as a class of
// static methods (Log.info(...), Log.SetMinSeverity(...)) rather than one flat module
// function per call. The message/debug/info/warning/error/fatal functions take
// printf-style varargs in C++; Python callers already have a formatted string, so it's
// passed through as a literal "%s" argument rather than exposing raw varargs.
struct Log {
    Log() = delete;

    static void SetMinSeverity(donut::log::Severity severity) { donut::log::SetMinSeverity(severity); }
    static void SetCallback(donut::log::Callback callback) { donut::log::SetCallback(std::move(callback)); }
    static void ResetCallback() { donut::log::ResetCallback(); }
    static void EnableOutputToMessageBox(bool enable) { donut::log::EnableOutputToMessageBox(enable); }
    static void EnableOutputToConsole(bool enable) { donut::log::EnableOutputToConsole(enable); }
    static void EnableOutputToDebug(bool enable) { donut::log::EnableOutputToDebug(enable); }
    static void SetErrorMessageCaption(const std::string &caption) { donut::log::SetErrorMessageCaption(caption.c_str()); }
    static void ConsoleApplicationMode() { donut::log::ConsoleApplicationMode(); }
    static void message(donut::log::Severity severity, const std::string &msg) { donut::log::message(severity, "%s", msg.c_str()); }
    static void debug(const std::string &msg) { donut::log::debug("%s", msg.c_str()); }
    static void info(const std::string &msg) { donut::log::info("%s", msg.c_str()); }
    static void warning(const std::string &msg) { donut::log::warning("%s", msg.c_str()); }
    static void error(const std::string &msg) { donut::log::error("%s", msg.c_str()); }
    // Aborts the process by default (Donut's DefaultCallback behavior) after logging;
    // install a custom callback via Log.SetCallback first if that's not desired.
    static void fatal(const std::string &msg) { donut::log::fatal("%s", msg.c_str()); }
};

} // namespace

PYBIND11_MODULE(_pydonut, m) {
    m.doc() = "pybind11 donut module";

    pybind11::native_enum<nvrhi::GraphicsAPI>(m, "GraphicsAPI", "enum.Enum")
        .value("D3D11", nvrhi::GraphicsAPI::D3D11)
        .value("D3D12", nvrhi::GraphicsAPI::D3D12)
        .value("Vulkan", nvrhi::GraphicsAPI::VULKAN)
        .finalize();

    pybind11::native_enum<nvrhi::Format>(m, "Format", "enum.Enum")
        .value("UNKNOWN", nvrhi::Format::UNKNOWN)
        .value("R8_UINT", nvrhi::Format::R8_UINT)
        .value("R8_SINT", nvrhi::Format::R8_SINT)
        .value("R8_UNORM", nvrhi::Format::R8_UNORM)
        .value("R8_SNORM", nvrhi::Format::R8_SNORM)
        .value("RG8_UINT", nvrhi::Format::RG8_UINT)
        .value("RG8_SINT", nvrhi::Format::RG8_SINT)
        .value("RG8_UNORM", nvrhi::Format::RG8_UNORM)
        .value("RG8_SNORM", nvrhi::Format::RG8_SNORM)
        .value("R16_UINT", nvrhi::Format::R16_UINT)
        .value("R16_SINT", nvrhi::Format::R16_SINT)
        .value("R16_UNORM", nvrhi::Format::R16_UNORM)
        .value("R16_SNORM", nvrhi::Format::R16_SNORM)
        .value("R16_FLOAT", nvrhi::Format::R16_FLOAT)
        .value("BGRA4_UNORM", nvrhi::Format::BGRA4_UNORM)
        .value("B5G6R5_UNORM", nvrhi::Format::B5G6R5_UNORM)
        .value("B5G5R5A1_UNORM", nvrhi::Format::B5G5R5A1_UNORM)
        .value("RGBA8_UINT", nvrhi::Format::RGBA8_UINT)
        .value("RGBA8_SINT", nvrhi::Format::RGBA8_SINT)
        .value("RGBA8_UNORM", nvrhi::Format::RGBA8_UNORM)
        .value("RGBA8_SNORM", nvrhi::Format::RGBA8_SNORM)
        .value("BGRA8_UNORM", nvrhi::Format::BGRA8_UNORM)
        .value("BGRX8_UNORM", nvrhi::Format::BGRX8_UNORM)
        .value("SRGBA8_UNORM", nvrhi::Format::SRGBA8_UNORM)
        .value("SBGRA8_UNORM", nvrhi::Format::SBGRA8_UNORM)
        .value("SBGRX8_UNORM", nvrhi::Format::SBGRX8_UNORM)
        .value("R10G10B10A2_UNORM", nvrhi::Format::R10G10B10A2_UNORM)
        .value("R11G11B10_FLOAT", nvrhi::Format::R11G11B10_FLOAT)
        .value("RG16_UINT", nvrhi::Format::RG16_UINT)
        .value("RG16_SINT", nvrhi::Format::RG16_SINT)
        .value("RG16_UNORM", nvrhi::Format::RG16_UNORM)
        .value("RG16_SNORM", nvrhi::Format::RG16_SNORM)
        .value("RG16_FLOAT", nvrhi::Format::RG16_FLOAT)
        .value("R32_UINT", nvrhi::Format::R32_UINT)
        .value("R32_SINT", nvrhi::Format::R32_SINT)
        .value("R32_FLOAT", nvrhi::Format::R32_FLOAT)
        .value("RGBA16_UINT", nvrhi::Format::RGBA16_UINT)
        .value("RGBA16_SINT", nvrhi::Format::RGBA16_SINT)
        .value("RGBA16_FLOAT", nvrhi::Format::RGBA16_FLOAT)
        .value("RGBA16_UNORM", nvrhi::Format::RGBA16_UNORM)
        .value("RGBA16_SNORM", nvrhi::Format::RGBA16_SNORM)
        .value("RG32_UINT", nvrhi::Format::RG32_UINT)
        .value("RG32_SINT", nvrhi::Format::RG32_SINT)
        .value("RG32_FLOAT", nvrhi::Format::RG32_FLOAT)
        .value("RGB32_UINT", nvrhi::Format::RGB32_UINT)
        .value("RGB32_SINT", nvrhi::Format::RGB32_SINT)
        .value("RGB32_FLOAT", nvrhi::Format::RGB32_FLOAT)
        .value("RGBA32_UINT", nvrhi::Format::RGBA32_UINT)
        .value("RGBA32_SINT", nvrhi::Format::RGBA32_SINT)
        .value("RGBA32_FLOAT", nvrhi::Format::RGBA32_FLOAT)
        .value("D16", nvrhi::Format::D16)
        .value("D24S8", nvrhi::Format::D24S8)
        .value("X24G8_UINT", nvrhi::Format::X24G8_UINT)
        .value("D32", nvrhi::Format::D32)
        .value("D32S8", nvrhi::Format::D32S8)
        .value("X32G8_UINT", nvrhi::Format::X32G8_UINT)
        .value("BC1_UNORM", nvrhi::Format::BC1_UNORM)
        .value("BC1_UNORM_SRGB", nvrhi::Format::BC1_UNORM_SRGB)
        .value("BC2_UNORM", nvrhi::Format::BC2_UNORM)
        .value("BC2_UNORM_SRGB", nvrhi::Format::BC2_UNORM_SRGB)
        .value("BC3_UNORM", nvrhi::Format::BC3_UNORM)
        .value("BC3_UNORM_SRGB", nvrhi::Format::BC3_UNORM_SRGB)
        .value("BC4_UNORM", nvrhi::Format::BC4_UNORM)
        .value("BC4_SNORM", nvrhi::Format::BC4_SNORM)
        .value("BC5_UNORM", nvrhi::Format::BC5_UNORM)
        .value("BC5_SNORM", nvrhi::Format::BC5_SNORM)
        .value("BC6H_UFLOAT", nvrhi::Format::BC6H_UFLOAT)
        .value("BC6H_SFLOAT", nvrhi::Format::BC6H_SFLOAT)
        .value("BC7_UNORM", nvrhi::Format::BC7_UNORM)
        .value("BC7_UNORM_SRGB", nvrhi::Format::BC7_UNORM_SRGB)
        .value("COUNT", nvrhi::Format::COUNT)
        .finalize();

    pybind11::native_enum<donut::log::Severity>(m, "LogSeverity", "enum.Enum")
        .value("None_", donut::log::Severity::None)
        .value("Debug", donut::log::Severity::Debug)
        .value("Info", donut::log::Severity::Info)
        .value("Warning", donut::log::Severity::Warning)
        .value("Error", donut::log::Severity::Error)
        .value("Fatal", donut::log::Severity::Fatal)
        .finalize();

    pybind11::native_enum<nvrhi::ShaderType>(m, "ShaderType", "enum.Enum")
        .value("None_", nvrhi::ShaderType::None)
        .value("Compute", nvrhi::ShaderType::Compute)
        .value("Vertex", nvrhi::ShaderType::Vertex)
        .value("Hull", nvrhi::ShaderType::Hull)
        .value("Domain", nvrhi::ShaderType::Domain)
        .value("Geometry", nvrhi::ShaderType::Geometry)
        .value("Pixel", nvrhi::ShaderType::Pixel)
        .value("Amplification", nvrhi::ShaderType::Amplification)
        .value("Mesh", nvrhi::ShaderType::Mesh)
        .value("AllGraphics", nvrhi::ShaderType::AllGraphics)
        .value("RayGeneration", nvrhi::ShaderType::RayGeneration)
        .value("AnyHit", nvrhi::ShaderType::AnyHit)
        .value("ClosestHit", nvrhi::ShaderType::ClosestHit)
        .value("Miss", nvrhi::ShaderType::Miss)
        .value("Intersection", nvrhi::ShaderType::Intersection)
        .value("Callable", nvrhi::ShaderType::Callable)
        .value("AllRayTracing", nvrhi::ShaderType::AllRayTracing)
        .value("All", nvrhi::ShaderType::All)
        .finalize();

    pybind11::native_enum<nvrhi::PrimitiveType>(m, "PrimitiveType", "enum.Enum")
        .value("PointList", nvrhi::PrimitiveType::PointList)
        .value("LineList", nvrhi::PrimitiveType::LineList)
        .value("LineStrip", nvrhi::PrimitiveType::LineStrip)
        .value("TriangleList", nvrhi::PrimitiveType::TriangleList)
        .value("TriangleStrip", nvrhi::PrimitiveType::TriangleStrip)
        .value("TriangleFan", nvrhi::PrimitiveType::TriangleFan)
        .value("TriangleListWithAdjacency", nvrhi::PrimitiveType::TriangleListWithAdjacency)
        .value("TriangleStripWithAdjacency", nvrhi::PrimitiveType::TriangleStripWithAdjacency)
        .value("PatchList", nvrhi::PrimitiveType::PatchList)
        .finalize();

    pybind11::native_enum<nvrhi::ComparisonFunc>(m, "ComparisonFunc", "enum.Enum")
        .value("Never", nvrhi::ComparisonFunc::Never)
        .value("Less", nvrhi::ComparisonFunc::Less)
        .value("Equal", nvrhi::ComparisonFunc::Equal)
        .value("LessOrEqual", nvrhi::ComparisonFunc::LessOrEqual)
        .value("Greater", nvrhi::ComparisonFunc::Greater)
        .value("NotEqual", nvrhi::ComparisonFunc::NotEqual)
        .value("GreaterOrEqual", nvrhi::ComparisonFunc::GreaterOrEqual)
        .value("Always", nvrhi::ComparisonFunc::Always)
        .finalize();

    pybind11::native_enum<nvrhi::RasterCullMode>(m, "RasterCullMode", "enum.Enum")
        .value("Back", nvrhi::RasterCullMode::Back)
        .value("Front", nvrhi::RasterCullMode::Front)
        .value("None_", nvrhi::RasterCullMode::None)
        .finalize();

    pybind11::native_enum<nvrhi::CommandQueue>(m, "CommandQueue", "enum.Enum")
        .value("Graphics", nvrhi::CommandQueue::Graphics)
        .value("Compute", nvrhi::CommandQueue::Compute)
        .value("Copy", nvrhi::CommandQueue::Copy)
        .finalize();

    pybind11::native_enum<nvrhi::Feature>(m, "Feature", "enum.Enum")
        .value("ComputeQueue", nvrhi::Feature::ComputeQueue)
        .value("ConservativeRasterization", nvrhi::Feature::ConservativeRasterization)
        .value("ConstantBufferRanges", nvrhi::Feature::ConstantBufferRanges)
        .value("CopyQueue", nvrhi::Feature::CopyQueue)
        .value("DeferredCommandLists", nvrhi::Feature::DeferredCommandLists)
        .value("FastGeometryShader", nvrhi::Feature::FastGeometryShader)
        .value("HeapDirectlyIndexed", nvrhi::Feature::HeapDirectlyIndexed)
        .value("HlslExtensionUAV", nvrhi::Feature::HlslExtensionUAV)
        .value("LinearSweptSpheres", nvrhi::Feature::LinearSweptSpheres)
        .value("Meshlets", nvrhi::Feature::Meshlets)
        .value("RayQuery", nvrhi::Feature::RayQuery)
        .value("RayTracingAccelStruct", nvrhi::Feature::RayTracingAccelStruct)
        .value("RayTracingClusters", nvrhi::Feature::RayTracingClusters)
        .value("RayTracingOpacityMicromap", nvrhi::Feature::RayTracingOpacityMicromap)
        .value("RayTracingPipeline", nvrhi::Feature::RayTracingPipeline)
        .value("SamplerFeedback", nvrhi::Feature::SamplerFeedback)
        .value("ShaderExecutionReordering", nvrhi::Feature::ShaderExecutionReordering)
        .value("ShaderSpecializations", nvrhi::Feature::ShaderSpecializations)
        .value("SinglePassStereo", nvrhi::Feature::SinglePassStereo)
        .value("Spheres", nvrhi::Feature::Spheres)
        .value("VariableRateShading", nvrhi::Feature::VariableRateShading)
        .value("VirtualResources", nvrhi::Feature::VirtualResources)
        .value("WaveLaneCountMinMax", nvrhi::Feature::WaveLaneCountMinMax)
        .value("CooperativeVectorInferencing", nvrhi::Feature::CooperativeVectorInferencing)
        .value("CooperativeVectorTraining", nvrhi::Feature::CooperativeVectorTraining)
        .value("EnhancedBarriers", nvrhi::Feature::EnhancedBarriers)
        .finalize();

    pybind11::native_enum<nvrhi::ResourceStates>(m, "ResourceStates", "enum.Enum")
        .value("Unknown", nvrhi::ResourceStates::Unknown)
        .value("Common", nvrhi::ResourceStates::Common)
        .value("ConstantBuffer", nvrhi::ResourceStates::ConstantBuffer)
        .value("VertexBuffer", nvrhi::ResourceStates::VertexBuffer)
        .value("IndexBuffer", nvrhi::ResourceStates::IndexBuffer)
        .value("IndirectArgument", nvrhi::ResourceStates::IndirectArgument)
        .value("PixelShaderResource", nvrhi::ResourceStates::PixelShaderResource)
        .value("NonPixelShaderResource", nvrhi::ResourceStates::NonPixelShaderResource)
        .value("ShaderResource", nvrhi::ResourceStates::ShaderResource)
        .value("UnorderedAccess", nvrhi::ResourceStates::UnorderedAccess)
        .value("RenderTarget", nvrhi::ResourceStates::RenderTarget)
        .value("DepthWrite", nvrhi::ResourceStates::DepthWrite)
        .value("DepthRead", nvrhi::ResourceStates::DepthRead)
        .value("StreamOut", nvrhi::ResourceStates::StreamOut)
        .value("CopyDest", nvrhi::ResourceStates::CopyDest)
        .value("CopySource", nvrhi::ResourceStates::CopySource)
        .value("ResolveDest", nvrhi::ResourceStates::ResolveDest)
        .value("ResolveSource", nvrhi::ResourceStates::ResolveSource)
        .value("Present", nvrhi::ResourceStates::Present)
        .value("AccelStructRead", nvrhi::ResourceStates::AccelStructRead)
        .value("AccelStructWrite", nvrhi::ResourceStates::AccelStructWrite)
        .value("AccelStructBuildInput", nvrhi::ResourceStates::AccelStructBuildInput)
        .value("AccelStructBuildBlas", nvrhi::ResourceStates::AccelStructBuildBlas)
        .value("ShadingRateSurface", nvrhi::ResourceStates::ShadingRateSurface)
        .value("OpacityMicromapWrite", nvrhi::ResourceStates::OpacityMicromapWrite)
        .value("OpacityMicromapBuildInput", nvrhi::ResourceStates::OpacityMicromapBuildInput)
        .value("ConvertCoopVecMatrixInput", nvrhi::ResourceStates::ConvertCoopVecMatrixInput)
        .value("ConvertCoopVecMatrixOutput", nvrhi::ResourceStates::ConvertCoopVecMatrixOutput)
        .finalize();

    pybind11::native_enum<nvrhi::rt::GeometryFlags>(m, "GeometryFlags", "enum.Enum")
        .value("None_", nvrhi::rt::GeometryFlags::None)
        .value("Opaque", nvrhi::rt::GeometryFlags::Opaque)
        .value("NoDuplicateAnyHitInvocation", nvrhi::rt::GeometryFlags::NoDuplicateAnyHitInvocation)
        .finalize();

    pybind11::native_enum<nvrhi::rt::InstanceFlags>(m, "InstanceFlags", "enum.Enum")
        .value("None_", nvrhi::rt::InstanceFlags::None)
        .value("TriangleCullDisable", nvrhi::rt::InstanceFlags::TriangleCullDisable)
        .value("TriangleFrontCounterclockwise", nvrhi::rt::InstanceFlags::TriangleFrontCounterclockwise)
        .value("ForceOpaque", nvrhi::rt::InstanceFlags::ForceOpaque)
        .value("ForceNonOpaque", nvrhi::rt::InstanceFlags::ForceNonOpaque)
        .value("ForceOMM2State", nvrhi::rt::InstanceFlags::ForceOMM2State)
        .value("DisableOMMs", nvrhi::rt::InstanceFlags::DisableOMMs)
        .finalize();

    m.def(
        "GetGraphicsAPIFromCommandLine",
        [](std::vector<std::string> args) {
            // Create a parallel vector of const char* pointers
            std::vector<const char*> cstrs;
            cstrs.reserve(args.size());

            for (const auto& s : args)
                cstrs.push_back(s.c_str());

            // Convert to const char* const*
            const char* const* argv = cstrs.data();
            size_t argc = cstrs.size();

            return donut::app::GetGraphicsAPIFromCommandLine(static_cast<int>(argc), argv);
        }, R"pbdoc(
        // TODO:
    )pbdoc");

    // nvrhi swap-chain resources: owned by the DeviceManager, never by Python. py::nodelete
    // keeps pybind11 from ever trying to destroy an object it doesn't own.
    py::class_<nvrhi::IFramebuffer, std::unique_ptr<nvrhi::IFramebuffer, py::nodelete>> framebuffer(m, "Framebuffer");
    py::class_<nvrhi::IDevice, std::unique_ptr<nvrhi::IDevice, py::nodelete>> device(m, "Device");

    // ITexture instances can be either borrowed (swap-chain textures, returned by raw pointer
    // with return_value_policy::reference below) or owned (created via Device.createTexture,
    // via DetachToShared); shared_ptr as the holder supports both without conflating lifetimes.
    py::class_<nvrhi::ITexture, std::shared_ptr<nvrhi::ITexture>> texture(m, "Texture");

    // nvrhi objects created through factory calls below: each create*() call returns one
    // owning reference, handed to Python as a std::shared_ptr that Releases() on collection.
    py::class_<nvrhi::IShader, std::shared_ptr<nvrhi::IShader>>(m, "Shader");
    py::class_<nvrhi::IGraphicsPipeline, std::shared_ptr<nvrhi::IGraphicsPipeline>>(m, "GraphicsPipeline");
    py::class_<nvrhi::IMeshletPipeline, std::shared_ptr<nvrhi::IMeshletPipeline>>(m, "MeshletPipeline");
    py::class_<nvrhi::ICommandList, std::shared_ptr<nvrhi::ICommandList>> commandList(m, "CommandList");
    py::class_<nvrhi::IBuffer, std::shared_ptr<nvrhi::IBuffer>> buffer(m, "Buffer");
    py::class_<nvrhi::IBindingLayout, std::shared_ptr<nvrhi::IBindingLayout>> bindingLayout(m, "BindingLayout");
    py::class_<nvrhi::IBindingSet, std::shared_ptr<nvrhi::IBindingSet>> bindingSet(m, "BindingSet");
    py::class_<nvrhi::ISampler, std::shared_ptr<nvrhi::ISampler>>(m, "Sampler");
    py::class_<nvrhi::rt::IAccelStruct, std::shared_ptr<nvrhi::rt::IAccelStruct>> accelStruct(m, "AccelStruct");
    py::class_<nvrhi::rt::IShaderTable, std::shared_ptr<nvrhi::rt::IShaderTable>> shaderTable(m, "ShaderTable");
    py::class_<nvrhi::rt::IPipeline, std::shared_ptr<nvrhi::rt::IPipeline>> rtPipeline(m, "RayTracingPipeline");
    py::class_<nvrhi::IShaderLibrary, std::shared_ptr<nvrhi::IShaderLibrary>> shaderLibrary(m, "ShaderLibrary");

    py::class_<nvrhi::Color>(m, "Color")
        .def(py::init<>())
        .def(py::init<float>(), py::arg("c"))
        .def(py::init<float, float, float, float>(), py::arg("r"), py::arg("g"), py::arg("b"), py::arg("a"))
        .def_readwrite("r", &nvrhi::Color::r)
        .def_readwrite("g", &nvrhi::Color::g)
        .def_readwrite("b", &nvrhi::Color::b)
        .def_readwrite("a", &nvrhi::Color::a);

    py::class_<nvrhi::Viewport>(m, "Viewport")
        .def(py::init<>())
        .def(py::init<float, float>(), py::arg("width"), py::arg("height"))
        .def(py::init<float, float, float, float, float, float>(),
            py::arg("minX"), py::arg("maxX"), py::arg("minY"), py::arg("maxY"), py::arg("minZ"), py::arg("maxZ"))
        .def_readwrite("minX", &nvrhi::Viewport::minX)
        .def_readwrite("maxX", &nvrhi::Viewport::maxX)
        .def_readwrite("minY", &nvrhi::Viewport::minY)
        .def_readwrite("maxY", &nvrhi::Viewport::maxY)
        .def_readwrite("minZ", &nvrhi::Viewport::minZ)
        .def_readwrite("maxZ", &nvrhi::Viewport::maxZ)
        .def("width", &nvrhi::Viewport::width)
        .def("height", &nvrhi::Viewport::height);

    py::class_<nvrhi::ViewportState>(m, "ViewportState")
        .def(py::init<>())
        .def("addViewportAndScissorRect", [](nvrhi::ViewportState &self, const nvrhi::Viewport &v) {
            self.addViewportAndScissorRect(v);
        }, py::arg("viewport"));

    // Bound as "FramebufferInfo": IFramebuffer::getFramebufferInfo() always returns the
    // extended (with width/height/arraySize) form, so there is no need for the plain base too.
    py::class_<nvrhi::FramebufferInfoEx>(m, "FramebufferInfo")
        .def_readonly("depthFormat", &nvrhi::FramebufferInfoEx::depthFormat)
        .def_readonly("sampleCount", &nvrhi::FramebufferInfoEx::sampleCount)
        .def_readonly("sampleQuality", &nvrhi::FramebufferInfoEx::sampleQuality)
        .def_readonly("width", &nvrhi::FramebufferInfoEx::width)
        .def_readonly("height", &nvrhi::FramebufferInfoEx::height)
        .def_readonly("arraySize", &nvrhi::FramebufferInfoEx::arraySize)
        .def("getViewport", &nvrhi::FramebufferInfoEx::getViewport, py::arg("minZ") = 0.f, py::arg("maxZ") = 1.f);

    py::class_<nvrhi::DepthStencilState>(m, "DepthStencilState")
        .def(py::init<>())
        .def_readwrite("depthTestEnable", &nvrhi::DepthStencilState::depthTestEnable)
        .def_readwrite("depthFunc", &nvrhi::DepthStencilState::depthFunc);

    py::class_<nvrhi::RasterState>(m, "RasterState")
        .def(py::init<>())
        .def_readwrite("cullMode", &nvrhi::RasterState::cullMode)
        .def_readwrite("frontCounterClockwise", &nvrhi::RasterState::frontCounterClockwise);

    py::class_<nvrhi::RenderState>(m, "RenderState")
        .def(py::init<>())
        .def_readwrite("depthStencilState", &nvrhi::RenderState::depthStencilState)
        .def_readwrite("rasterState", &nvrhi::RenderState::rasterState);

    py::class_<nvrhi::DrawArguments>(m, "DrawArguments")
        .def(py::init<>())
        .def_readwrite("vertexCount", &nvrhi::DrawArguments::vertexCount)
        .def_readwrite("instanceCount", &nvrhi::DrawArguments::instanceCount)
        .def_readwrite("startIndexLocation", &nvrhi::DrawArguments::startIndexLocation)
        .def_readwrite("startVertexLocation", &nvrhi::DrawArguments::startVertexLocation)
        .def_readwrite("startInstanceLocation", &nvrhi::DrawArguments::startInstanceLocation);

    py::class_<nvrhi::GraphicsPipelineDesc>(m, "GraphicsPipelineDesc")
        .def(py::init<>())
        .def_readwrite("primType", &nvrhi::GraphicsPipelineDesc::primType)
        .def_readwrite("renderState", &nvrhi::GraphicsPipelineDesc::renderState)
        .def_property("VS",
            [](const nvrhi::GraphicsPipelineDesc &d) -> nvrhi::IShader* { return d.VS.Get(); },
            [](nvrhi::GraphicsPipelineDesc &d, nvrhi::IShader* shader) { d.VS = shader; },
            py::return_value_policy::reference)
        .def_property("PS",
            [](const nvrhi::GraphicsPipelineDesc &d) -> nvrhi::IShader* { return d.PS.Get(); },
            [](nvrhi::GraphicsPipelineDesc &d, nvrhi::IShader* shader) { d.PS = shader; },
            py::return_value_policy::reference)
        .def("addBindingLayout", [](nvrhi::GraphicsPipelineDesc &self, nvrhi::IBindingLayout* layout) {
            self.addBindingLayout(layout);
        }, py::arg("layout"));

    py::class_<nvrhi::GraphicsState>(m, "GraphicsState")
        .def(py::init<>())
        .def_readwrite("viewport", &nvrhi::GraphicsState::viewport)
        .def_property("pipeline",
            [](const nvrhi::GraphicsState &s) -> nvrhi::IGraphicsPipeline* { return s.pipeline; },
            [](nvrhi::GraphicsState &s, nvrhi::IGraphicsPipeline* p) { s.pipeline = p; },
            py::return_value_policy::reference)
        .def_property("framebuffer",
            [](const nvrhi::GraphicsState &s) -> nvrhi::IFramebuffer* { return s.framebuffer; },
            [](nvrhi::GraphicsState &s, nvrhi::IFramebuffer* fb) { s.framebuffer = fb; },
            py::return_value_policy::reference)
        .def("addBindingSet", [](nvrhi::GraphicsState &self, nvrhi::IBindingSet* set) {
            self.addBindingSet(set);
        }, py::arg("bindingSet"));

    py::class_<nvrhi::MeshletPipelineDesc>(m, "MeshletPipelineDesc")
        .def(py::init<>())
        .def_readwrite("primType", &nvrhi::MeshletPipelineDesc::primType)
        .def_readwrite("renderState", &nvrhi::MeshletPipelineDesc::renderState)
        .def_property("AS",
            [](const nvrhi::MeshletPipelineDesc &d) -> nvrhi::IShader* { return d.AS.Get(); },
            [](nvrhi::MeshletPipelineDesc &d, nvrhi::IShader* shader) { d.AS = shader; },
            py::return_value_policy::reference)
        .def_property("MS",
            [](const nvrhi::MeshletPipelineDesc &d) -> nvrhi::IShader* { return d.MS.Get(); },
            [](nvrhi::MeshletPipelineDesc &d, nvrhi::IShader* shader) { d.MS = shader; },
            py::return_value_policy::reference)
        .def_property("PS",
            [](const nvrhi::MeshletPipelineDesc &d) -> nvrhi::IShader* { return d.PS.Get(); },
            [](nvrhi::MeshletPipelineDesc &d, nvrhi::IShader* shader) { d.PS = shader; },
            py::return_value_policy::reference);

    py::class_<nvrhi::MeshletState>(m, "MeshletState")
        .def(py::init<>())
        .def_readwrite("viewport", &nvrhi::MeshletState::viewport)
        .def_property("pipeline",
            [](const nvrhi::MeshletState &s) -> nvrhi::IMeshletPipeline* { return s.pipeline; },
            [](nvrhi::MeshletState &s, nvrhi::IMeshletPipeline* p) { s.pipeline = p; },
            py::return_value_policy::reference)
        .def_property("framebuffer",
            [](const nvrhi::MeshletState &s) -> nvrhi::IFramebuffer* { return s.framebuffer; },
            [](nvrhi::MeshletState &s, nvrhi::IFramebuffer* fb) { s.framebuffer = fb; },
            py::return_value_policy::reference);

    py::class_<nvrhi::BufferDesc>(m, "BufferDesc")
        .def(py::init<>())
        .def_readwrite("byteSize", &nvrhi::BufferDesc::byteSize)
        .def_readwrite("structStride", &nvrhi::BufferDesc::structStride)
        .def_readwrite("maxVersions", &nvrhi::BufferDesc::maxVersions)
        .def_readwrite("debugName", &nvrhi::BufferDesc::debugName)
        .def_readwrite("format", &nvrhi::BufferDesc::format)
        .def_readwrite("canHaveUAVs", &nvrhi::BufferDesc::canHaveUAVs)
        .def_readwrite("canHaveTypedViews", &nvrhi::BufferDesc::canHaveTypedViews)
        .def_readwrite("canHaveRawViews", &nvrhi::BufferDesc::canHaveRawViews)
        .def_readwrite("isVertexBuffer", &nvrhi::BufferDesc::isVertexBuffer)
        .def_readwrite("isIndexBuffer", &nvrhi::BufferDesc::isIndexBuffer)
        .def_readwrite("isConstantBuffer", &nvrhi::BufferDesc::isConstantBuffer)
        .def_readwrite("isDrawIndirectArgs", &nvrhi::BufferDesc::isDrawIndirectArgs)
        .def_readwrite("isAccelStructBuildInput", &nvrhi::BufferDesc::isAccelStructBuildInput)
        .def_readwrite("isAccelStructStorage", &nvrhi::BufferDesc::isAccelStructStorage)
        .def_readwrite("isShaderBindingTable", &nvrhi::BufferDesc::isShaderBindingTable)
        .def_readwrite("isVolatile", &nvrhi::BufferDesc::isVolatile)
        .def_readwrite("initialState", &nvrhi::BufferDesc::initialState)
        .def_readwrite("keepInitialState", &nvrhi::BufferDesc::keepInitialState);

    py::class_<nvrhi::TextureDesc>(m, "TextureDesc")
        .def(py::init<>())
        .def_readwrite("width", &nvrhi::TextureDesc::width)
        .def_readwrite("height", &nvrhi::TextureDesc::height)
        .def_readwrite("depth", &nvrhi::TextureDesc::depth)
        .def_readwrite("arraySize", &nvrhi::TextureDesc::arraySize)
        .def_readwrite("mipLevels", &nvrhi::TextureDesc::mipLevels)
        .def_readwrite("sampleCount", &nvrhi::TextureDesc::sampleCount)
        .def_readwrite("format", &nvrhi::TextureDesc::format)
        .def_readwrite("debugName", &nvrhi::TextureDesc::debugName)
        .def_readwrite("isShaderResource", &nvrhi::TextureDesc::isShaderResource)
        .def_readwrite("isRenderTarget", &nvrhi::TextureDesc::isRenderTarget)
        .def_readwrite("isUAV", &nvrhi::TextureDesc::isUAV)
        .def_readwrite("clearValue", &nvrhi::TextureDesc::clearValue)
        .def_readwrite("useClearValue", &nvrhi::TextureDesc::useClearValue)
        .def_readwrite("initialState", &nvrhi::TextureDesc::initialState)
        .def_readwrite("keepInitialState", &nvrhi::TextureDesc::keepInitialState);

    py::class_<nvrhi::FramebufferAttachment>(m, "FramebufferAttachment")
        .def_property_readonly("texture", [](const nvrhi::FramebufferAttachment &a) -> nvrhi::ITexture* { return a.texture; },
            py::return_value_policy::reference);

    py::class_<nvrhi::FramebufferDesc>(m, "FramebufferDesc")
        .def("getColorAttachment", [](const nvrhi::FramebufferDesc &self, size_t index) { return self.colorAttachments[index]; },
            py::arg("index"));

    // BindingLayoutItem/BindingSetItem pack a bitfield + union that pybind11 can't expose as
    // plain properties; Python only ever obtains instances through these static factories,
    // matching how nvrhi's own C++ call sites are expected to construct them.
    py::class_<nvrhi::BindingLayoutItem>(m, "BindingLayoutItem")
        .def_static("Texture_UAV", &nvrhi::BindingLayoutItem::Texture_UAV, py::arg("slot"))
        .def_static("Texture_SRV", &nvrhi::BindingLayoutItem::Texture_SRV, py::arg("slot"))
        .def_static("RawBuffer_SRV", &nvrhi::BindingLayoutItem::RawBuffer_SRV, py::arg("slot"))
        .def_static("RayTracingAccelStruct", &nvrhi::BindingLayoutItem::RayTracingAccelStruct, py::arg("slot"));

    py::class_<nvrhi::BindingLayoutDesc>(m, "BindingLayoutDesc")
        .def(py::init<>())
        .def_readwrite("visibility", &nvrhi::BindingLayoutDesc::visibility)
        .def_readwrite("bindings", &nvrhi::BindingLayoutDesc::bindings);

    py::class_<nvrhi::BindingSetItem>(m, "BindingSetItem")
        .def_static("Texture_UAV", [](uint32_t slot, nvrhi::ITexture* texture) {
            return nvrhi::BindingSetItem::Texture_UAV(slot, texture);
        }, py::arg("slot"), py::arg("texture"))
        .def_static("RayTracingAccelStruct", [](uint32_t slot, nvrhi::rt::IAccelStruct* accelStruct) {
            return nvrhi::BindingSetItem::RayTracingAccelStruct(slot, accelStruct);
        }, py::arg("slot"), py::arg("accelStruct"))
        .def_static("ConstantBuffer", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::ConstantBuffer(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
        .def_static("StructuredBuffer_SRV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::StructuredBuffer_SRV(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
        .def_static("Sampler", [](uint32_t slot, nvrhi::ISampler* sampler) {
            return nvrhi::BindingSetItem::Sampler(slot, sampler);
        }, py::arg("slot"), py::arg("sampler"))
        .def_static("PushConstants", &nvrhi::BindingSetItem::PushConstants, py::arg("slot"), py::arg("byteSize"));

    py::class_<nvrhi::BindingSetDesc>(m, "BindingSetDesc")
        .def(py::init<>())
        .def_readwrite("bindings", &nvrhi::BindingSetDesc::bindings);

    // BindlessLayoutDesc.registerSpaces reuses BindingLayoutItem, but its `slot` means
    // "register space index" here rather than a binding slot (see nvrhi.h's comment on
    // BindlessLayoutDesc) -- RawBuffer_SRV(1)/Texture_SRV(2) below assign spaces 1 and 2.
    py::class_<nvrhi::BindlessLayoutDesc>(m, "BindlessLayoutDesc")
        .def(py::init<>())
        .def_readwrite("visibility", &nvrhi::BindlessLayoutDesc::visibility)
        .def_readwrite("firstSlot", &nvrhi::BindlessLayoutDesc::firstSlot)
        .def_readwrite("maxCapacity", &nvrhi::BindlessLayoutDesc::maxCapacity)
        .def("addRegisterSpace", [](nvrhi::BindlessLayoutDesc &self, const nvrhi::BindingLayoutItem &item) {
            self.addRegisterSpace(item);
        }, py::arg("item"));

    // Mirrors nvrhi::utils::CreateBindingSetAndLayout: derives a matching BindingLayoutDesc
    // from the BindingSetDesc's items and creates both in one call.
    m.def("CreateBindingSetAndLayout", [](nvrhi::IDevice* device, nvrhi::ShaderType visibility, uint32_t registerSpace, const nvrhi::BindingSetDesc &bindingSetDesc) {
        nvrhi::BindingLayoutHandle layout;
        nvrhi::BindingSetHandle set;
        nvrhi::utils::CreateBindingSetAndLayout(device, visibility, registerSpace, bindingSetDesc, layout, set);
        return py::make_tuple(DetachToShared(std::move(layout)), DetachToShared(std::move(set)));
    }, py::arg("device"), py::arg("visibility"), py::arg("registerSpace"), py::arg("bindingSetDesc"));

    m.def("ClearDepthStencilAttachment", &nvrhi::utils::ClearDepthStencilAttachment,
        py::arg("commandList"), py::arg("framebuffer"), py::arg("depth"), py::arg("stencil"));

    py::class_<nvrhi::rt::GeometryTriangles>(m, "GeometryTriangles")
        .def(py::init<>())
        .def_property("indexBuffer",
            [](const nvrhi::rt::GeometryTriangles &g) -> nvrhi::IBuffer* { return g.indexBuffer; },
            [](nvrhi::rt::GeometryTriangles &g, nvrhi::IBuffer* b) { g.indexBuffer = b; },
            py::return_value_policy::reference)
        .def_property("vertexBuffer",
            [](const nvrhi::rt::GeometryTriangles &g) -> nvrhi::IBuffer* { return g.vertexBuffer; },
            [](nvrhi::rt::GeometryTriangles &g, nvrhi::IBuffer* b) { g.vertexBuffer = b; },
            py::return_value_policy::reference)
        .def_readwrite("indexFormat", &nvrhi::rt::GeometryTriangles::indexFormat)
        .def_readwrite("vertexFormat", &nvrhi::rt::GeometryTriangles::vertexFormat)
        .def_readwrite("indexCount", &nvrhi::rt::GeometryTriangles::indexCount)
        .def_readwrite("vertexCount", &nvrhi::rt::GeometryTriangles::vertexCount)
        .def_readwrite("vertexStride", &nvrhi::rt::GeometryTriangles::vertexStride);

    py::class_<nvrhi::rt::GeometryDesc>(m, "GeometryDesc")
        .def(py::init<>())
        .def_readwrite("flags", &nvrhi::rt::GeometryDesc::flags)
        .def("setTriangles", [](nvrhi::rt::GeometryDesc &self, const nvrhi::rt::GeometryTriangles &triangles) {
            self.setTriangles(triangles);
        }, py::arg("triangles"));

    py::class_<nvrhi::rt::AccelStructDesc>(m, "AccelStructDesc")
        .def(py::init<>())
        .def_readwrite("isTopLevel", &nvrhi::rt::AccelStructDesc::isTopLevel)
        .def_readwrite("topLevelMaxInstances", &nvrhi::rt::AccelStructDesc::topLevelMaxInstances)
        .def_readwrite("bottomLevelGeometries", &nvrhi::rt::AccelStructDesc::bottomLevelGeometries);

    // InstanceDesc packs bitfields + a union (like BindingLayoutItem/BindingSetItem above),
    // so it's mutated through its setter methods rather than plain properties. The default
    // constructor already fills in the identity transform.
    py::class_<nvrhi::rt::InstanceDesc>(m, "InstanceDesc")
        .def(py::init<>())
        .def("setInstanceMask", [](nvrhi::rt::InstanceDesc &self, uint32_t value) { self.setInstanceMask(value); }, py::arg("value"))
        .def("setInstanceID", [](nvrhi::rt::InstanceDesc &self, uint32_t value) { self.setInstanceID(value); }, py::arg("value"))
        .def("setInstanceContributionToHitGroupIndex", [](nvrhi::rt::InstanceDesc &self, uint32_t value) {
            self.setInstanceContributionToHitGroupIndex(value);
        }, py::arg("value"))
        .def("setFlags", [](nvrhi::rt::InstanceDesc &self, nvrhi::rt::InstanceFlags value) { self.setFlags(value); }, py::arg("value"))
        .def("setBLAS", [](nvrhi::rt::InstanceDesc &self, nvrhi::rt::IAccelStruct* value) { self.setBLAS(value); }, py::arg("value"));

    py::class_<nvrhi::rt::PipelineShaderDesc>(m, "PipelineShaderDesc")
        .def(py::init<>())
        .def("setShader", [](nvrhi::rt::PipelineShaderDesc &self, nvrhi::IShader* shader) { self.setShader(shader); }, py::arg("shader"));

    py::class_<nvrhi::rt::PipelineHitGroupDesc>(m, "PipelineHitGroupDesc")
        .def(py::init<>())
        .def("setExportName", [](nvrhi::rt::PipelineHitGroupDesc &self, const std::string &value) { self.setExportName(value); }, py::arg("value"))
        .def("setClosestHitShader", [](nvrhi::rt::PipelineHitGroupDesc &self, nvrhi::IShader* shader) { self.setClosestHitShader(shader); }, py::arg("shader"));

    py::class_<nvrhi::rt::PipelineDesc>(m, "RayTracingPipelineDesc")
        .def(py::init<>())
        .def_readwrite("maxPayloadSize", &nvrhi::rt::PipelineDesc::maxPayloadSize)
        .def("addShader", [](nvrhi::rt::PipelineDesc &self, const nvrhi::rt::PipelineShaderDesc &shader) { self.addShader(shader); }, py::arg("shader"))
        .def("addHitGroup", [](nvrhi::rt::PipelineDesc &self, const nvrhi::rt::PipelineHitGroupDesc &hitGroup) { self.addHitGroup(hitGroup); }, py::arg("hitGroup"))
        .def("addBindingLayout", [](nvrhi::rt::PipelineDesc &self, nvrhi::IBindingLayout* layout) { self.addBindingLayout(layout); }, py::arg("layout"));

    py::class_<nvrhi::rt::State>(m, "RayTracingState")
        .def(py::init<>())
        .def_property("shaderTable",
            [](const nvrhi::rt::State &s) -> nvrhi::rt::IShaderTable* { return s.shaderTable; },
            [](nvrhi::rt::State &s, nvrhi::rt::IShaderTable* t) { s.shaderTable = t; },
            py::return_value_policy::reference)
        .def("addBindingSet", [](nvrhi::rt::State &self, nvrhi::IBindingSet* set) { self.addBindingSet(set); }, py::arg("bindingSet"));

    py::class_<nvrhi::rt::DispatchRaysArguments>(m, "DispatchRaysArguments")
        .def(py::init<>())
        .def_readwrite("width", &nvrhi::rt::DispatchRaysArguments::width)
        .def_readwrite("height", &nvrhi::rt::DispatchRaysArguments::height)
        .def_readwrite("depth", &nvrhi::rt::DispatchRaysArguments::depth);

    framebuffer.def("getFramebufferInfo", &nvrhi::IFramebuffer::getFramebufferInfo, py::return_value_policy::reference_internal);
    framebuffer.def("getDesc", [](nvrhi::IFramebuffer &self) { return self.getDesc(); });

    texture.def("getDesc", [](nvrhi::ITexture &self) { return self.getDesc(); });

    device.def("getGraphicsAPI", &nvrhi::IDevice::getGraphicsAPI);
    device.def("createCommandList", [](nvrhi::IDevice &self) {
        return DetachToShared(self.createCommandList());
    });
    device.def("createGraphicsPipeline", [](nvrhi::IDevice &self, const nvrhi::GraphicsPipelineDesc &desc, const nvrhi::FramebufferInfoEx &framebufferInfo) {
        return DetachToShared(self.createGraphicsPipeline(desc, framebufferInfo));
    }, py::arg("desc"), py::arg("framebufferInfo"));
    device.def("createMeshletPipeline", [](nvrhi::IDevice &self, const nvrhi::MeshletPipelineDesc &desc, const nvrhi::FramebufferInfoEx &framebufferInfo) {
        return DetachToShared(self.createMeshletPipeline(desc, framebufferInfo));
    }, py::arg("desc"), py::arg("framebufferInfo"));
    device.def("executeCommandList", [](nvrhi::IDevice &self, nvrhi::ICommandList* cmdList, nvrhi::CommandQueue executionQueue) {
        return self.executeCommandList(cmdList, executionQueue);
    }, py::arg("commandList"), py::arg("executionQueue") = nvrhi::CommandQueue::Graphics);
    device.def("createShader", [](nvrhi::IDevice &self, const std::string &bytecode, const std::string &entryName, nvrhi::ShaderType shaderType) {
        nvrhi::ShaderDesc desc;
        desc.shaderType = shaderType;
        desc.entryName = entryName;
        return DetachToShared(self.createShader(desc, bytecode.data(), bytecode.size()));
    }, py::arg("bytecode"), py::arg("entryName"), py::arg("shaderType"));
    device.def("queryFeatureSupport", [](nvrhi::IDevice &self, nvrhi::Feature feature) {
        return self.queryFeatureSupport(feature);
    }, py::arg("feature"));
    device.def("createBuffer", [](nvrhi::IDevice &self, const nvrhi::BufferDesc &desc) {
        return DetachToShared(self.createBuffer(desc));
    }, py::arg("desc"));
    device.def("createTexture", [](nvrhi::IDevice &self, const nvrhi::TextureDesc &desc) {
        return DetachToShared(self.createTexture(desc));
    }, py::arg("desc"));
    device.def("createBindingLayout", [](nvrhi::IDevice &self, const nvrhi::BindingLayoutDesc &desc) {
        return DetachToShared(self.createBindingLayout(desc));
    }, py::arg("desc"));
    device.def("createBindingSet", [](nvrhi::IDevice &self, const nvrhi::BindingSetDesc &desc, nvrhi::IBindingLayout* layout) {
        return DetachToShared(self.createBindingSet(desc, layout));
    }, py::arg("desc"), py::arg("layout"));
    device.def("createAccelStruct", [](nvrhi::IDevice &self, const nvrhi::rt::AccelStructDesc &desc) {
        return DetachToShared(self.createAccelStruct(desc));
    }, py::arg("desc"));
    device.def("createRayTracingPipeline", [](nvrhi::IDevice &self, const nvrhi::rt::PipelineDesc &desc) {
        return DetachToShared(self.createRayTracingPipeline(desc));
    }, py::arg("desc"));
    device.def("createBindlessLayout", [](nvrhi::IDevice &self, const nvrhi::BindlessLayoutDesc &desc) {
        return DetachToShared(self.createBindlessLayout(desc));
    }, py::arg("desc"));
    device.def("waitForIdle", &nvrhi::IDevice::waitForIdle);

    commandList.def("open", &nvrhi::ICommandList::open);
    commandList.def("close", &nvrhi::ICommandList::close);
    commandList.def("setGraphicsState", &nvrhi::ICommandList::setGraphicsState, py::arg("state"));
    commandList.def("draw", &nvrhi::ICommandList::draw, py::arg("args"));
    commandList.def("setMeshletState", &nvrhi::ICommandList::setMeshletState, py::arg("state"));
    commandList.def("dispatchMesh", &nvrhi::ICommandList::dispatchMesh,
        py::arg("groupsX"), py::arg("groupsY") = 1, py::arg("groupsZ") = 1);
    commandList.def("writeBuffer", [](nvrhi::ICommandList &self, nvrhi::IBuffer* buffer, py::buffer data, uint64_t destOffsetBytes) {
        py::buffer_info info = data.request();
        self.writeBuffer(buffer, info.ptr, static_cast<size_t>(info.size * info.itemsize), destOffsetBytes);
    }, py::arg("buffer"), py::arg("data"), py::arg("destOffsetBytes") = 0);
    commandList.def("buildTopLevelAccelStruct", [](nvrhi::ICommandList &self, nvrhi::rt::IAccelStruct* as, const std::vector<nvrhi::rt::InstanceDesc> &instances) {
        self.buildTopLevelAccelStruct(as, instances.data(), instances.size());
    }, py::arg("as"), py::arg("instances"));
    commandList.def("setRayTracingState", &nvrhi::ICommandList::setRayTracingState, py::arg("state"));
    commandList.def("dispatchRays", &nvrhi::ICommandList::dispatchRays, py::arg("args"));
    commandList.def("setPushConstants", [](nvrhi::ICommandList &self, py::buffer data) {
        py::buffer_info info = data.request();
        self.setPushConstants(info.ptr, static_cast<size_t>(info.size * info.itemsize));
    }, py::arg("data"));

    m.def("ClearColorAttachment", &nvrhi::utils::ClearColorAttachment,
        py::arg("commandList"), py::arg("framebuffer"), py::arg("attachmentIndex"), py::arg("color"));

    m.def("BuildBottomLevelAccelStruct", &nvrhi::utils::BuildBottomLevelAccelStruct,
        py::arg("commandList"), py::arg("as"), py::arg("desc"));

    rtPipeline.def("createShaderTable", [](nvrhi::rt::IPipeline &self) {
        return DetachToShared(self.createShaderTable());
    });

    shaderTable.def("setRayGenerationShader", [](nvrhi::rt::IShaderTable &self, const std::string &exportName, nvrhi::IBindingSet* bindings) {
        self.setRayGenerationShader(exportName.c_str(), bindings);
    }, py::arg("exportName"), py::arg("bindings") = nullptr);
    shaderTable.def("addHitGroup", [](nvrhi::rt::IShaderTable &self, const std::string &exportName, nvrhi::IBindingSet* bindings) {
        return self.addHitGroup(exportName.c_str(), bindings);
    }, py::arg("exportName"), py::arg("bindings") = nullptr);
    shaderTable.def("addMissShader", [](nvrhi::rt::IShaderTable &self, const std::string &exportName, nvrhi::IBindingSet* bindings) {
        return self.addMissShader(exportName.c_str(), bindings);
    }, py::arg("exportName"), py::arg("bindings") = nullptr);

    shaderLibrary.def("getShader", [](nvrhi::IShaderLibrary &self, const std::string &entryName, nvrhi::ShaderType shaderType) {
        return DetachToShared(self.getShader(entryName.c_str(), shaderType));
    }, py::arg("entryName"), py::arg("shaderType"));

    m.def("GetDirectoryWithExecutable", &donut::app::GetDirectoryWithExecutable);
    m.def("GetShaderTypeName", &donut::app::GetShaderTypeName, py::arg("api"));

    py::class_<Log>(m, "log")
        .def_static("SetMinSeverity", &Log::SetMinSeverity, py::arg("severity"))
        .def_static("SetCallback", &Log::SetCallback, py::arg("callback"))
        .def_static("ResetCallback", &Log::ResetCallback)
        .def_static("EnableOutputToMessageBox", &Log::EnableOutputToMessageBox, py::arg("enable"))
        .def_static("EnableOutputToConsole", &Log::EnableOutputToConsole, py::arg("enable"))
        .def_static("EnableOutputToDebug", &Log::EnableOutputToDebug, py::arg("enable"))
        .def_static("SetErrorMessageCaption", &Log::SetErrorMessageCaption, py::arg("caption"))
        .def_static("ConsoleApplicationMode", &Log::ConsoleApplicationMode)
        .def_static("message", &Log::message, py::arg("severity"), py::arg("message"))
        .def_static("debug", &Log::debug, py::arg("message"))
        .def_static("info", &Log::info, py::arg("message"))
        .def_static("warning", &Log::warning, py::arg("message"))
        .def_static("error", &Log::error, py::arg("message"))
        .def_static("fatal", &Log::fatal, py::arg("message"));

    device.def("createShaderLibrary", [](nvrhi::IDevice &self, const std::string &bytecode) {
        return DetachToShared(self.createShaderLibrary(bytecode.data(), bytecode.size()));
    }, py::arg("bytecode"));

#if PYDONUT_HAVE_DXC
    m.def("CompileShader", &CompileShaderWithDXC,
        py::arg("source"), py::arg("entryPoint"), py::arg("shaderType"), py::arg("api"),
        py::arg("sourceName") = "shader.hlsl", py::arg("shaderModel") = "6_5",
        py::arg("includePaths") = std::vector<std::string>{});
    m.def("CompileShaderLibrary", &CompileShaderLibraryWithDXC,
        py::arg("source"), py::arg("api"),
        py::arg("sourceName") = "shader.hlsl", py::arg("shaderModel") = "6_5",
        py::arg("includePaths") = std::vector<std::string>{});
#endif

    py::class_<donut::vfs::IFileSystem, std::shared_ptr<donut::vfs::IFileSystem>>(m, "IFileSystem");
    py::class_<donut::vfs::NativeFileSystem, donut::vfs::IFileSystem, std::shared_ptr<donut::vfs::NativeFileSystem>>(m, "NativeFileSystem")
        .def(py::init<>());
    py::class_<donut::vfs::RootFileSystem, donut::vfs::IFileSystem, std::shared_ptr<donut::vfs::RootFileSystem>>(m, "RootFileSystem")
        .def(py::init<>())
        .def("mount", [](donut::vfs::RootFileSystem &self, const std::filesystem::path &path, const std::filesystem::path &nativePath) {
            self.mount(path, nativePath);
        }, py::arg("path"), py::arg("nativePath"));

    py::class_<donut::engine::ShaderFactory, std::shared_ptr<donut::engine::ShaderFactory>> shaderFactory(m, "ShaderFactory");
    shaderFactory.def(py::init([](nvrhi::IDevice* device, std::shared_ptr<donut::vfs::IFileSystem> fs, const std::filesystem::path& basePath) {
        return new donut::engine::ShaderFactory(nvrhi::DeviceHandle(device), fs, basePath);
    }), py::arg("device"), py::arg("fs"), py::arg("basePath"));
    shaderFactory.def("CreateShader", [](donut::engine::ShaderFactory &self, const std::string &fileName, const std::string &entryName, nvrhi::ShaderType shaderType) {
        return DetachToShared(self.CreateShader(fileName.c_str(), entryName.c_str(), nullptr, shaderType));
    }, py::arg("fileName"), py::arg("entryName"), py::arg("shaderType"));
    shaderFactory.def("CreateShaderLibrary", [](donut::engine::ShaderFactory &self, const std::string &fileName) {
        return DetachToShared(self.CreateShaderLibrary(fileName.c_str(), nullptr));
    }, py::arg("fileName"));

    py::class_<donut::engine::BindingCache>(m, "BindingCache")
        .def(py::init<nvrhi::IDevice*>(), py::arg("device"))
        .def("Clear", &donut::engine::BindingCache::Clear);

    py::class_<donut::engine::CommonRenderPasses, std::shared_ptr<donut::engine::CommonRenderPasses>>(m, "CommonRenderPasses")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::ShaderFactory>>(), py::arg("device"), py::arg("shaderFactory"))
        .def("BlitTexture", [](donut::engine::CommonRenderPasses &self, nvrhi::ICommandList* commandList, nvrhi::IFramebuffer* targetFramebuffer,
                nvrhi::ITexture* sourceTexture, donut::engine::BindingCache* bindingCache) {
            self.BlitTexture(commandList, targetFramebuffer, sourceTexture, bindingCache);
        }, py::arg("commandList"), py::arg("targetFramebuffer"), py::arg("sourceTexture"), py::arg("bindingCache") = nullptr)
        .def_property_readonly("m_AnisotropicWrapSampler", [](donut::engine::CommonRenderPasses &self) -> nvrhi::ISampler* {
            return self.m_AnisotropicWrapSampler;
        }, py::return_value_policy::reference_internal);

    py::class_<donut::engine::DescriptorTableManager, std::shared_ptr<donut::engine::DescriptorTableManager>> descriptorTableManager(m, "DescriptorTableManager");
    descriptorTableManager.def(py::init<nvrhi::IDevice*, nvrhi::IBindingLayout*>(), py::arg("device"), py::arg("layout"));
    descriptorTableManager.def("GetDescriptorTable", [](donut::engine::DescriptorTableManager &self) -> nvrhi::IBindingSet* {
        return self.GetDescriptorTable();
    }, py::return_value_policy::reference_internal);

    py::class_<donut::engine::TextureCache, std::shared_ptr<donut::engine::TextureCache>> textureCache(m, "TextureCache");
    textureCache.def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::vfs::IFileSystem>, std::shared_ptr<donut::engine::DescriptorTableManager>>(),
        py::arg("device"), py::arg("fs"), py::arg("descriptorTable"));
    textureCache.def("Reset", &donut::engine::TextureCache::Reset);
    textureCache.def("ProcessRenderingThreadCommands", &donut::engine::TextureCache::ProcessRenderingThreadCommands,
        py::arg("commonPasses"), py::arg("timeLimitMilliseconds"));
    textureCache.def("LoadingFinished", &donut::engine::TextureCache::LoadingFinished);

    // Scene::Load() reads a glTF file synchronously and builds the CPU-side scene graph;
    // FinishedLoading() then uploads the GPU buffers (instances/geometries/materials) on
    // its own internal command list. sceneTypeFactory is always null here -- Python has no
    // use for custom scene node types, matching the samples that pass nullptr too.
    py::class_<donut::engine::Scene, std::shared_ptr<donut::engine::Scene>> scene(m, "Scene");
    scene.def(py::init([](nvrhi::IDevice* device, donut::engine::ShaderFactory& shaderFactory, std::shared_ptr<donut::vfs::IFileSystem> fs,
            std::shared_ptr<donut::engine::TextureCache> textureCache, std::shared_ptr<donut::engine::DescriptorTableManager> descriptorTable) {
        return new donut::engine::Scene(device, shaderFactory, fs, textureCache, descriptorTable, nullptr);
    }), py::arg("device"), py::arg("shaderFactory"), py::arg("fs"), py::arg("textureCache"), py::arg("descriptorTable"));
    scene.def("Load", [](donut::engine::Scene &self, const std::filesystem::path &sceneFileName) {
        return self.Load(sceneFileName);
    }, py::arg("sceneFileName"));
    scene.def("FinishedLoading", &donut::engine::Scene::FinishedLoading, py::arg("frameIndex"));
    scene.def("GetInstanceBuffer", [](donut::engine::Scene &self) -> nvrhi::IBuffer* { return self.GetInstanceBuffer(); }, py::return_value_policy::reference_internal);
    scene.def("GetGeometryBuffer", [](donut::engine::Scene &self) -> nvrhi::IBuffer* { return self.GetGeometryBuffer(); }, py::return_value_policy::reference_internal);
    scene.def("GetMaterialBuffer", [](donut::engine::Scene &self) -> nvrhi::IBuffer* { return self.GetMaterialBuffer(); }, py::return_value_policy::reference_internal);
    // Flattens GetSceneGraph()->GetMeshInstances() -> each geometry into (instanceIndex,
    // geometryIndexInMesh, numIndices) tuples, sparing Python from needing bindings for
    // SceneGraph/MeshInstance/MeshInfo/MeshGeometry just to drive per-geometry draw calls.
    scene.def("GetDrawItems", [](donut::engine::Scene &self) {
        std::vector<std::tuple<int, int, uint32_t>> items;
        for (const auto &instance : self.GetSceneGraph()->GetMeshInstances())
        {
            const auto &mesh = instance->GetMesh();
            for (size_t i = 0; i < mesh->geometries.size(); i++)
            {
                items.emplace_back(instance->GetInstanceIndex(), static_cast<int>(i), mesh->geometries[i]->numIndices);
            }
        }
        return items;
    });

    // FirstPersonCamera's matrices (dm::affine3/float4x4) aren't exposed to Python --
    // SetMatricesFromCamera on PlanarView below consumes them internally instead.
    py::class_<donut::app::FirstPersonCamera> firstPersonCamera(m, "FirstPersonCamera");
    firstPersonCamera.def(py::init<>());
    firstPersonCamera.def("LookAt", [](donut::app::FirstPersonCamera &self,
            float posX, float posY, float posZ, float targetX, float targetY, float targetZ) {
        self.LookAt(donut::math::float3(posX, posY, posZ), donut::math::float3(targetX, targetY, targetZ));
    }, py::arg("posX"), py::arg("posY"), py::arg("posZ"), py::arg("targetX"), py::arg("targetY"), py::arg("targetZ"));
    firstPersonCamera.def("SetMoveSpeed", &donut::app::FirstPersonCamera::SetMoveSpeed, py::arg("value"));
    firstPersonCamera.def("Animate", &donut::app::FirstPersonCamera::Animate, py::arg("deltaT"));
    firstPersonCamera.def("KeyboardUpdate", &donut::app::FirstPersonCamera::KeyboardUpdate,
        py::arg("key"), py::arg("scancode"), py::arg("action"), py::arg("mods"));
    firstPersonCamera.def("MousePosUpdate", &donut::app::FirstPersonCamera::MousePosUpdate, py::arg("xpos"), py::arg("ypos"));
    firstPersonCamera.def("MouseButtonUpdate", &donut::app::FirstPersonCamera::MouseButtonUpdate,
        py::arg("button"), py::arg("action"), py::arg("mods"));

    py::class_<donut::engine::PlanarView> planarView(m, "PlanarView");
    planarView.def(py::init<>());
    planarView.def("SetViewport", [](donut::engine::PlanarView &self, const nvrhi::Viewport &viewport) {
        self.SetViewport(viewport);
    }, py::arg("viewport"));
    planarView.def("SetMatricesFromCamera", [](donut::engine::PlanarView &self, const donut::app::FirstPersonCamera &camera,
            float aspectRatio, float verticalFovRadians, float zNear) {
        self.SetMatrices(camera.GetWorldToViewMatrix(), donut::math::perspProjD3DStyleReverse(verticalFovRadians, aspectRatio, zNear));
    }, py::arg("camera"), py::arg("aspectRatio"), py::arg("verticalFovRadians") = donut::math::PI_f * 0.25f, py::arg("zNear") = 0.1f);
    planarView.def("UpdateCache", &donut::engine::PlanarView::UpdateCache);
    planarView.def("GetViewportState", &donut::engine::PlanarView::GetViewportState);
    planarView.def("FillPlanarViewConstants", [](const donut::engine::PlanarView &self) {
        PlanarViewConstants constants{};
        self.FillPlanarViewConstants(constants);
        return py::bytes(reinterpret_cast<const char*>(&constants), sizeof(constants));
    });

    py::class_<donut::app::IRenderPass, PyIRenderPass> renderPass(m, "IRenderPass");
    renderPass.def(py::init<donut::app::DeviceManager*>(), py::arg("deviceManager"));
    renderPass.def("SetLatewarpOptions", &donut::app::IRenderPass::SetLatewarpOptions);
    renderPass.def("ShouldAnimateUnfocused", &donut::app::IRenderPass::ShouldAnimateUnfocused);
    renderPass.def("ShouldRenderUnfocused", &donut::app::IRenderPass::ShouldRenderUnfocused);
    renderPass.def("SupportsDepthBuffer", &donut::app::IRenderPass::SupportsDepthBuffer);
    renderPass.def("Render", &donut::app::IRenderPass::Render, py::arg("framebuffer"));
    renderPass.def("Animate", &donut::app::IRenderPass::Animate, py::arg("elapsedTimeSeconds"));
    renderPass.def("BackBufferResizing", &donut::app::IRenderPass::BackBufferResizing);
    renderPass.def("BackBufferResized", &donut::app::IRenderPass::BackBufferResized, py::arg("width"), py::arg("height"), py::arg("sampleCount"));
    renderPass.def("DisplayScaleChanged", &donut::app::IRenderPass::DisplayScaleChanged, py::arg("scaleX"), py::arg("scaleY"));
    renderPass.def("KeyboardUpdate", &donut::app::IRenderPass::KeyboardUpdate, py::arg("key"), py::arg("scancode"), py::arg("action"), py::arg("mods"));
    renderPass.def("KeyboardCharInput", &donut::app::IRenderPass::KeyboardCharInput, py::arg("unicode"), py::arg("mods"));
    renderPass.def("MousePosUpdate", &donut::app::IRenderPass::MousePosUpdate, py::arg("xpos"), py::arg("ypos"));
    renderPass.def("MouseScrollUpdate", &donut::app::IRenderPass::MouseScrollUpdate, py::arg("xoffset"), py::arg("yoffset"));
    renderPass.def("MouseButtonUpdate", &donut::app::IRenderPass::MouseButtonUpdate, py::arg("button"), py::arg("action"), py::arg("mods"));
    renderPass.def("JoystickButtonUpdate", &donut::app::IRenderPass::JoystickButtonUpdate, py::arg("button"), py::arg("pressed"));
    renderPass.def("JoystickAxisUpdate", &donut::app::IRenderPass::JoystickAxisUpdate, py::arg("axis"), py::arg("value"));
    renderPass.def("GetDeviceManager", &donut::app::IRenderPass::GetDeviceManager, py::return_value_policy::reference);
    renderPass.def("GetDevice", &donut::app::IRenderPass::GetDevice, py::return_value_policy::reference);
    renderPass.def("GetFrameIndex", &donut::app::IRenderPass::GetFrameIndex);

    py::class_<donut::app::AdapterInfo>(m, "AdapterInfo")
        .def(py::init<>())
        .def_readonly("name", &donut::app::AdapterInfo::name)
        .def_readonly("vendorID", &donut::app::AdapterInfo::vendorID)
        .def_readonly("deviceID", &donut::app::AdapterInfo::deviceID)
        .def_readonly("dedicatedVideoMemory", &donut::app::AdapterInfo::dedicatedVideoMemory)
        .def_readonly("uuid", &donut::app::AdapterInfo::uuid)
        .def_readonly("luid", &donut::app::AdapterInfo::luid);

    pybind11::class_<donut::app::DeviceManager> deviceManager(m, "DeviceManager");
    deviceManager.def_static(
        "Create",
        &donut::app::DeviceManager::Create,
        py::arg("api") = nvrhi::GraphicsAPI::VULKAN);
    deviceManager.def(
        "CreateHeadlessDevice",
        &donut::app::DeviceManager::CreateHeadlessDevice,
        py::arg("params"));
    deviceManager.def(
        "CreateWindowDeviceAndSwapChain",
        &donut::app::DeviceManager::CreateWindowDeviceAndSwapChain,
        py::arg("params"),
        py::arg("windowTitle") = "");
    deviceManager.def(
        "CreateInstance",
        [](donut::app::DeviceManager& self, const donut::app::DeviceCreationParameters& params) {
            return self.CreateInstance(params);
        },
        py::arg("params"));
    deviceManager.def(
        "EnumerateAdapters",
        [](donut::app::DeviceManager& self) {
            std::vector<donut::app::AdapterInfo> adapters;
            bool ok = self.EnumerateAdapters(adapters);
            return py::make_tuple(ok, adapters);
        });
    deviceManager.def(
        "AddRenderPassToFront",
        &donut::app::DeviceManager::AddRenderPassToFront,
        py::arg("renderPass"));
    deviceManager.def(
        "AddRenderPassToBack",
        &donut::app::DeviceManager::AddRenderPassToBack,
        py::arg("renderPass"));
    deviceManager.def(
        "RemoveRenderPass",
        &donut::app::DeviceManager::RemoveRenderPass,
        py::arg("renderPass"));
    deviceManager.def(
        "RunMessageLoop",
        &donut::app::DeviceManager::RunMessageLoop);
    deviceManager.def(
        "GetWindowDimensions",
        [](donut::app::DeviceManager& self) {
            int width = 0, height = 0;
            self.GetWindowDimensions(width, height);
            return py::make_tuple(width, height);
        });
    deviceManager.def(
        "GetDPIScaleInfo",
        [](const donut::app::DeviceManager& self) {
            float x = 0.f, y = 0.f;
            self.GetDPIScaleInfo(x, y);
            return py::make_tuple(x, y);
        });
    deviceManager.def(
        "GetDeviceParams",
        &donut::app::DeviceManager::GetDeviceParams,
        py::return_value_policy::reference_internal);
    deviceManager.def(
        "GetAverageFrameTimeSeconds",
        &donut::app::DeviceManager::GetAverageFrameTimeSeconds);
    deviceManager.def(
        "GetPreviousFrameTimestamp",
        &donut::app::DeviceManager::GetPreviousFrameTimestamp);
    deviceManager.def(
        "SetFrameTimeUpdateInterval",
        &donut::app::DeviceManager::SetFrameTimeUpdateInterval,
        py::arg("seconds"));
    deviceManager.def(
        "IsVsyncEnabled",
        &donut::app::DeviceManager::IsVsyncEnabled);
    deviceManager.def(
        "SetVsyncEnabled",
        &donut::app::DeviceManager::SetVsyncEnabled,
        py::arg("enabled"));
    deviceManager.def(
        "ReportLiveObjects",
        &donut::app::DeviceManager::ReportLiveObjects);
    deviceManager.def(
        "SetEnableRenderDuringWindowMovement",
        &donut::app::DeviceManager::SetEnableRenderDuringWindowMovement,
        py::arg("val"));
    deviceManager.def(
        "IsWindowFocused",
        &donut::app::DeviceManager::IsWindowFocused);
    deviceManager.def(
        "IsWindowVisible",
        &donut::app::DeviceManager::IsWindowVisible);
    deviceManager.def(
        "RenderNextFrameWhileUnfocused",
        &donut::app::DeviceManager::RenderNextFrameWhileUnfocused);
    deviceManager.def(
        "GetFrameIndex",
        &donut::app::DeviceManager::GetFrameIndex);
    deviceManager.def(
        "GetCurrentBackBuffer",
        &donut::app::DeviceManager::GetCurrentBackBuffer,
        py::return_value_policy::reference);
    deviceManager.def(
        "GetBackBuffer",
        &donut::app::DeviceManager::GetBackBuffer,
        py::arg("index"),
        py::return_value_policy::reference);
    deviceManager.def(
        "GetCurrentBackBufferIndex",
        &donut::app::DeviceManager::GetCurrentBackBufferIndex);
    deviceManager.def(
        "GetBackBufferCount",
        &donut::app::DeviceManager::GetBackBufferCount);
    deviceManager.def(
        "GetCurrentFramebuffer",
        &donut::app::DeviceManager::GetCurrentFramebuffer,
        py::arg("withDepth") = true,
        py::return_value_policy::reference);
    deviceManager.def(
        "GetFramebuffer",
        &donut::app::DeviceManager::GetFramebuffer,
        py::arg("index"),
        py::arg("withDepth") = true,
        py::return_value_policy::reference);
    deviceManager.def(
        "GetDepthBuffer",
        &donut::app::DeviceManager::GetDepthBuffer,
        py::return_value_policy::reference);
    deviceManager.def(
        "GetDevice",
        &donut::app::DeviceManager::GetDevice,
        py::return_value_policy::reference);
    deviceManager.def(
        "GetRendererString",
        &donut::app::DeviceManager::GetRendererString);
    deviceManager.def(
        "GetGraphicsAPI",
        &donut::app::DeviceManager::GetGraphicsAPI);
    deviceManager.def(
        "SetWindowTitle",
        [](donut::app::DeviceManager& self, const std::string& title) {
            self.SetWindowTitle(title.c_str());
        },
        py::arg("title"));
    deviceManager.def(
        "SetInformativeWindowTitle",
        [](donut::app::DeviceManager& self, const std::string& applicationName, bool includeFramerate, std::optional<std::string> extraInfo) {
            self.SetInformativeWindowTitle(applicationName.c_str(), includeFramerate, extraInfo ? extraInfo->c_str() : nullptr);
        },
        py::arg("applicationName"),
        py::arg("includeFramerate") = true,
        py::arg("extraInfo") = std::nullopt);
    deviceManager.def(
        "GetWindowTitle",
        &donut::app::DeviceManager::GetWindowTitle);
    deviceManager.def(
        "IsVulkanInstanceExtensionEnabled",
        &donut::app::DeviceManager::IsVulkanInstanceExtensionEnabled,
        py::arg("extensionName"));
    deviceManager.def(
        "IsVulkanDeviceExtensionEnabled",
        &donut::app::DeviceManager::IsVulkanDeviceExtensionEnabled,
        py::arg("extensionName"));
    deviceManager.def(
        "IsVulkanLayerEnabled",
        &donut::app::DeviceManager::IsVulkanLayerEnabled,
        py::arg("layerName"));
    deviceManager.def(
        "GetEnabledVulkanInstanceExtensions",
        [](const donut::app::DeviceManager& self) {
            std::vector<std::string> extensions;
            self.GetEnabledVulkanInstanceExtensions(extensions);
            return extensions;
        });
    deviceManager.def(
        "GetEnabledVulkanDeviceExtensions",
        [](const donut::app::DeviceManager& self) {
            std::vector<std::string> extensions;
            self.GetEnabledVulkanDeviceExtensions(extensions);
            return extensions;
        });
    deviceManager.def(
        "GetEnabledVulkanLayers",
        [](const donut::app::DeviceManager& self) {
            std::vector<std::string> layers;
            self.GetEnabledVulkanLayers(layers);
            return layers;
        });
    deviceManager.def(
        "Shutdown",
        &donut::app::DeviceManager::Shutdown);

    py::class_<donut::app::DeviceManager::PipelineCallbacks>(m, "PipelineCallbacks")
        .def(py::init<>())
        .def_readwrite("beforeFrame", &donut::app::DeviceManager::PipelineCallbacks::beforeFrame)
        .def_readwrite("beforeAnimate", &donut::app::DeviceManager::PipelineCallbacks::beforeAnimate)
        .def_readwrite("afterAnimate", &donut::app::DeviceManager::PipelineCallbacks::afterAnimate)
        .def_readwrite("beforeRender", &donut::app::DeviceManager::PipelineCallbacks::beforeRender)
        .def_readwrite("afterRender", &donut::app::DeviceManager::PipelineCallbacks::afterRender)
        .def_readwrite("beforePresent", &donut::app::DeviceManager::PipelineCallbacks::beforePresent)
        .def_readwrite("afterPresent", &donut::app::DeviceManager::PipelineCallbacks::afterPresent);
    deviceManager.def_readwrite("callbacks", &donut::app::DeviceManager::m_callbacks);

    pybind11::class_<donut::app::DeviceCreationParameters> deviceCreationParameters(m, "DeviceCreationParameters");
    deviceCreationParameters.def(pybind11::init<>());

    // InstanceParameters (base class)
    deviceCreationParameters.def_readwrite("enableDebugRuntime", &donut::app::DeviceCreationParameters::enableDebugRuntime);
    deviceCreationParameters.def_readwrite("enableWarningsAsErrors", &donut::app::DeviceCreationParameters::enableWarningsAsErrors);
    deviceCreationParameters.def_readwrite("enableGPUValidation", &donut::app::DeviceCreationParameters::enableGPUValidation);
    deviceCreationParameters.def_readwrite("headlessDevice", &donut::app::DeviceCreationParameters::headlessDevice);
    deviceCreationParameters.def_readwrite("logBufferLifetime", &donut::app::DeviceCreationParameters::logBufferLifetime);
    deviceCreationParameters.def_readwrite("enableHeapDirectlyIndexed", &donut::app::DeviceCreationParameters::enableHeapDirectlyIndexed);
    deviceCreationParameters.def_readwrite("enablePerMonitorDPI", &donut::app::DeviceCreationParameters::enablePerMonitorDPI);
    deviceCreationParameters.def_readwrite("infoLogSeverity", &donut::app::DeviceCreationParameters::infoLogSeverity);
#if DONUT_WITH_VULKAN
    deviceCreationParameters.def_readwrite("vulkanLibraryName", &donut::app::DeviceCreationParameters::vulkanLibraryName);
    deviceCreationParameters.def_readwrite("requiredVulkanInstanceExtensions", &donut::app::DeviceCreationParameters::requiredVulkanInstanceExtensions);
    deviceCreationParameters.def_readwrite("requiredVulkanLayers", &donut::app::DeviceCreationParameters::requiredVulkanLayers);
    deviceCreationParameters.def_readwrite("optionalVulkanInstanceExtensions", &donut::app::DeviceCreationParameters::optionalVulkanInstanceExtensions);
    deviceCreationParameters.def_readwrite("optionalVulkanLayers", &donut::app::DeviceCreationParameters::optionalVulkanLayers);
#endif

    // DeviceCreationParameters
    deviceCreationParameters.def_readwrite("startMaximized", &donut::app::DeviceCreationParameters::startMaximized);
    deviceCreationParameters.def_readwrite("startFullscreen", &donut::app::DeviceCreationParameters::startFullscreen);
    deviceCreationParameters.def_readwrite("startBorderless", &donut::app::DeviceCreationParameters::startBorderless);
    deviceCreationParameters.def_readwrite("fullscreenAlwaysOnTop", &donut::app::DeviceCreationParameters::fullscreenAlwaysOnTop);
    deviceCreationParameters.def_readwrite("windowPosX", &donut::app::DeviceCreationParameters::windowPosX);
    deviceCreationParameters.def_readwrite("windowPosY", &donut::app::DeviceCreationParameters::windowPosY);
    deviceCreationParameters.def_readwrite("backBufferWidth", &donut::app::DeviceCreationParameters::backBufferWidth);
    deviceCreationParameters.def_readwrite("backBufferHeight", &donut::app::DeviceCreationParameters::backBufferHeight);
    deviceCreationParameters.def_readwrite("refreshRate", &donut::app::DeviceCreationParameters::refreshRate);
    deviceCreationParameters.def_readwrite("swapChainBufferCount", &donut::app::DeviceCreationParameters::swapChainBufferCount);
    deviceCreationParameters.def_readwrite("swapChainFormat", &donut::app::DeviceCreationParameters::swapChainFormat);
    deviceCreationParameters.def_readwrite("swapChainSampleCount", &donut::app::DeviceCreationParameters::swapChainSampleCount);
    deviceCreationParameters.def_readwrite("swapChainSampleQuality", &donut::app::DeviceCreationParameters::swapChainSampleQuality);
    deviceCreationParameters.def_readwrite("depthBufferFormat", &donut::app::DeviceCreationParameters::depthBufferFormat);
    deviceCreationParameters.def_readwrite("maxFramesInFlight", &donut::app::DeviceCreationParameters::maxFramesInFlight);
    deviceCreationParameters.def_readwrite("enableNvrhiValidationLayer", &donut::app::DeviceCreationParameters::enableNvrhiValidationLayer);
    deviceCreationParameters.def_readwrite("enableRayTracingValidation", &donut::app::DeviceCreationParameters::enableRayTracingValidation);
    deviceCreationParameters.def_readwrite("vsyncEnabled", &donut::app::DeviceCreationParameters::vsyncEnabled);
    deviceCreationParameters.def_readwrite("enableRayTracingExtensions", &donut::app::DeviceCreationParameters::enableRayTracingExtensions);
    deviceCreationParameters.def_readwrite("enableComputeQueue", &donut::app::DeviceCreationParameters::enableComputeQueue);
    deviceCreationParameters.def_readwrite("enableCopyQueue", &donut::app::DeviceCreationParameters::enableCopyQueue);
    deviceCreationParameters.def_readwrite("adapterIndex", &donut::app::DeviceCreationParameters::adapterIndex);
    deviceCreationParameters.def_readwrite("supportExplicitDisplayScaling", &donut::app::DeviceCreationParameters::supportExplicitDisplayScaling);
    deviceCreationParameters.def_readwrite("resizeWindowWithDisplayScale", &donut::app::DeviceCreationParameters::resizeWindowWithDisplayScale);
#if DONUT_WITH_DX11 || DONUT_WITH_DX12
    deviceCreationParameters.def_readwrite("swapChainUsage", &donut::app::DeviceCreationParameters::swapChainUsage);
    deviceCreationParameters.def_property("featureLevel",
        [](const donut::app::DeviceCreationParameters &params) { return static_cast<long>(params.featureLevel); },
        [](donut::app::DeviceCreationParameters &params, long value) { params.featureLevel = static_cast<D3D_FEATURE_LEVEL>(value); });
#endif
#if DONUT_WITH_VULKAN
    deviceCreationParameters.def_readwrite("requiredVulkanDeviceExtensions", &donut::app::DeviceCreationParameters::requiredVulkanDeviceExtensions);
    deviceCreationParameters.def_readwrite("optionalVulkanDeviceExtensions", &donut::app::DeviceCreationParameters::optionalVulkanDeviceExtensions);
    deviceCreationParameters.def_readwrite("ignoredVulkanValidationMessageLocations", &donut::app::DeviceCreationParameters::ignoredVulkanValidationMessageLocations);
#endif
}
