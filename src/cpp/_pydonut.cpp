/******************************************************************************
* Copyright (C) 1991-2026 ASDAlexander77.
*
* Permission is hereby granted, free of charge, to any person obtaining
* a copy of this software and associated documentation files (the
* "Software"), to deal in the Software without restriction, including
* without limitation the rights to use, copy, modify, merge, publish,
* distribute, sublicense, and/or sell copies of the Software, and to
* permit persons to whom the Software is furnished to do so, subject to
* the following conditions:
*
* The above copyright notice and this permission notice shall be
* included in all copies or substantial portions of the Software.
*
* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
* EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
* MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
* IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
* CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
* TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
* SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
******************************************************************************/

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
#include <donut/app/imgui_renderer.h>
#include <imgui.h>
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
#include <donut/engine/FramebufferFactory.h>
#include <donut/render/GBuffer.h>
#include <donut/render/GBufferFillPass.h>
#include <donut/render/DeferredLightingPass.h>
#include <donut/render/ForwardShadingPass.h>
#include <donut/render/TemporalAntiAliasingPass.h>
#include <donut/render/SkyPass.h>
#include <donut/render/SsaoPass.h>
#include <donut/render/GeometryPasses.h>
#include <donut/render/DrawStrategy.h>
#include <nvrhi/utils.h>

#if PYDONUT_HAVE_DXC
#include <dxcapi.h>
#endif

#ifdef NVRHI_WITH_DX12
#include <wrl.h>
#include <d3dx12/d3dx12.h>
#endif

#if DONUT_WITH_VULKAN
// Plain C Vulkan API only (for vkFreeMemory in DestroyBufferMemory_UnsafeForCrashTesting).
// Deliberately NOT vulkan.hpp: the aftermath.cpp sample uses it with
// VULKAN_HPP_DISPATCH_LOADER_DYNAMIC, whose dispatcher-storage macro would have to be
// satisfied in this translation unit for no benefit here.
#include <vulkan/vulkan.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

// donut links Vulkan-Headers -- headers only, no loader import library -- because nvrhi loads
// Vulkan dynamically. So vkFreeMemory has no link-time symbol in this translation unit and
// must be resolved from the loader module, which is guaranteed to already be in the process by
// the time a VULKAN device exists. Returns nullptr if the loader somehow isn't present.
static PFN_vkFreeMemory ResolveVkFreeMemory() {
#ifdef _WIN32
    HMODULE loader = GetModuleHandleW(L"vulkan-1.dll");
    if (!loader)
        return nullptr;
    return reinterpret_cast<PFN_vkFreeMemory>(GetProcAddress(loader, "vkFreeMemory"));
#else
    // Already loaded, so this only bumps a refcount and hands back the existing handle.
    void* loader = dlopen("libvulkan.so.1", RTLD_NOW);
    if (!loader)
        return nullptr;
    return reinterpret_cast<PFN_vkFreeMemory>(dlsym(loader, "vkFreeMemory"));
#endif
}
#endif

// view_cb.h is a shared C++/HLSL header: its field types (float4x4, float2, ...) are
// donut::math types used unqualified, exactly as donut's own View.cpp includes it. Its
// PlanarViewConstants is forward-declared at GLOBAL scope in View.h (see the `struct
// PlanarViewConstants;` there), so this include -- and the using-directive it needs --
// must also sit at global scope for the two declarations to refer to the same type.
using namespace donut::math;
#include <donut/shaders/view_cb.h>
#include <donut/shaders/material_cb.h>
#include <donut/shaders/light_cb.h>

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

// Trampoline class so Python subclasses of ApplicationBase can override its virtual methods
// (including the IRenderPass ones ApplicationBase doesn't itself override) and LoadScene,
// which ApplicationBase leaves pure virtual.
class PyApplicationBase : public donut::app::ApplicationBase {
public:
    using ApplicationBase::ApplicationBase;

    // m_TextureCache/m_CommonPasses/m_IsAsyncLoad are protected on ApplicationBase, so a
    // Python subclass has no way to read/wire them -- without SetTextureCache/SetCommonPasses,
    // the inherited SceneLoaded() finalizes a null texture cache and does nothing, forcing
    // every sample to duplicate its logic via the free-function pyd.SceneLoaded(). These back
    // the m_TextureCache/m_CommonPasses/m_IsAsyncLoad properties bound below.
    // (m_SceneLoadingThread is intentionally not exposed: it's a std::unique_ptr<std::thread>
    // owned and joined entirely by BeginLoadingScene()/Render(), with no meaningful Python-side
    // use.)
    void SetTextureCache(std::shared_ptr<donut::engine::TextureCache> textureCache) {
        m_TextureCache = std::move(textureCache);
    }
    std::shared_ptr<donut::engine::TextureCache> GetTextureCache() const {
        return m_TextureCache;
    }
    void SetCommonPasses(std::shared_ptr<donut::engine::CommonRenderPasses> commonPasses) {
        m_CommonPasses = std::move(commonPasses);
    }
    bool GetIsAsyncLoad() const {
        return m_IsAsyncLoad;
    }

    void SetLatewarpOptions() override {
        PYBIND11_OVERRIDE(void, ApplicationBase, SetLatewarpOptions);
    }
    bool ShouldAnimateUnfocused() override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, ShouldAnimateUnfocused);
    }
    bool ShouldRenderUnfocused() override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, ShouldRenderUnfocused);
    }
    bool SupportsDepthBuffer() override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, SupportsDepthBuffer);
    }
    void Render(nvrhi::IFramebuffer* framebuffer) override {
        PYBIND11_OVERRIDE(void, ApplicationBase, Render, framebuffer);
    }
    void RenderScene(nvrhi::IFramebuffer* framebuffer) override {
        PYBIND11_OVERRIDE(void, ApplicationBase, RenderScene, framebuffer);
    }
    void RenderSplashScreen(nvrhi::IFramebuffer* framebuffer) override {
        PYBIND11_OVERRIDE(void, ApplicationBase, RenderSplashScreen, framebuffer);
    }
    void BeginLoadingScene(std::shared_ptr<donut::vfs::IFileSystem> fs, const std::filesystem::path& sceneFileName) override {
        PYBIND11_OVERRIDE(void, ApplicationBase, BeginLoadingScene, fs, sceneFileName);
    }
    bool LoadScene(std::shared_ptr<donut::vfs::IFileSystem> fs, const std::filesystem::path& sceneFileName) override {
        PYBIND11_OVERRIDE_PURE(bool, ApplicationBase, LoadScene, fs, sceneFileName);
    }
    void SceneUnloading() override {
        PYBIND11_OVERRIDE(void, ApplicationBase, SceneUnloading);
    }
    void SceneLoaded() override {
        PYBIND11_OVERRIDE(void, ApplicationBase, SceneLoaded);
    }
    void Animate(float fElapsedTimeSeconds) override {
        PYBIND11_OVERRIDE(void, ApplicationBase, Animate, fElapsedTimeSeconds);
    }
    void BackBufferResizing() override {
        PYBIND11_OVERRIDE(void, ApplicationBase, BackBufferResizing);
    }
    void BackBufferResized(const uint32_t width, const uint32_t height, const uint32_t sampleCount) override {
        PYBIND11_OVERRIDE(void, ApplicationBase, BackBufferResized, width, height, sampleCount);
    }
    void DisplayScaleChanged(float scaleX, float scaleY) override {
        PYBIND11_OVERRIDE(void, ApplicationBase, DisplayScaleChanged, scaleX, scaleY);
    }
    bool KeyboardUpdate(int key, int scancode, int action, int mods) override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, KeyboardUpdate, key, scancode, action, mods);
    }
    bool KeyboardCharInput(unsigned int unicode, int mods) override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, KeyboardCharInput, unicode, mods);
    }
    bool MousePosUpdate(double xpos, double ypos) override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, MousePosUpdate, xpos, ypos);
    }
    bool MouseScrollUpdate(double xoffset, double yoffset) override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, MouseScrollUpdate, xoffset, yoffset);
    }
    bool MouseButtonUpdate(int button, int action, int mods) override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, MouseButtonUpdate, button, action, mods);
    }
    bool JoystickButtonUpdate(int button, bool pressed) override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, JoystickButtonUpdate, button, pressed);
    }
    bool JoystickAxisUpdate(int axis, float value) override {
        PYBIND11_OVERRIDE(bool, ApplicationBase, JoystickAxisUpdate, axis, value);
    }
};

// Trampoline so Python subclasses of ImGui_Renderer can implement its one pure virtual,
// buildUI() (see rt_particles.py's UserInterface). Everything else (KeyboardUpdate, Render,
// Animate, ...) is already implemented by ImGui_Renderer itself and isn't overridden by any
// sample, so unlike PyApplicationBase above, no other virtuals need PYBIND11_OVERRIDE hooks.
class PyImGuiRenderer : public donut::app::ImGui_Renderer {
public:
    using ImGui_Renderer::ImGui_Renderer;

    void buildUI() override {
        PYBIND11_OVERRIDE_PURE(void, ImGui_Renderer, buildUI);
    }
};

// Empty tag type so the raw ImGui:: functions below can be grouped as static methods under
// a "pyd.ImGui" class-as-namespace, matching this module's existing py::class_<Log>(m, "log")
// convention -- and so their generic names (Text, Begin, Combo, ...) don't collide with
// anything at the top level of the pydonut module. Only the subset rt_particles.py's
// UserInterface actually calls is bound.
struct ImGuiNS {};

// PassthroughDrawStrategy::SetData() only stores a raw pointer to the DrawItem it's given --
// it doesn't own it. This wrapper gives the strategy its own DrawItem plus shared_ptr
// references to everything the item points at, so the item stays valid for as long as the
// strategy object (spanning the SetSingleItem() call and the later RenderView() call) lives,
// without requiring the Python caller to separately keep those objects alive.
struct PyPassthroughDrawStrategy : donut::render::PassthroughDrawStrategy {
    donut::render::DrawItem item{};
    std::shared_ptr<donut::engine::MeshInstance> instanceRef;
    std::shared_ptr<donut::engine::MeshInfo> meshRef;
    std::shared_ptr<donut::engine::MeshGeometry> geometryRef;
    std::shared_ptr<donut::engine::Material> materialRef;
    std::shared_ptr<donut::engine::BufferGroup> buffersRef;

    void SetSingleItem(
        std::shared_ptr<donut::engine::MeshInstance> instance,
        std::shared_ptr<donut::engine::MeshInfo> mesh,
        std::shared_ptr<donut::engine::MeshGeometry> geometry,
        std::shared_ptr<donut::engine::Material> material,
        std::shared_ptr<donut::engine::BufferGroup> buffers,
        float distanceToCamera,
        nvrhi::RasterCullMode cullMode)
    {
        instanceRef = std::move(instance);
        meshRef = std::move(mesh);
        geometryRef = std::move(geometry);
        materialRef = std::move(material);
        buffersRef = std::move(buffers);

        item.instance = instanceRef.get();
        item.mesh = meshRef.get();
        item.geometry = geometryRef.get();
        item.material = materialRef.get();
        item.buffers = buffersRef.get();
        item.distanceToCamera = distanceToCamera;
        item.cullMode = cullMode;

        SetData(&item, 1);
    }
};

// DeferredLightingPass::Inputs::lights is a non-owning pointer to a vector -- this wrapper
// gives it an owned vector to point at, so a Python list of lights survives past the call
// that sets it. SetAmbientColors collapses the two dm::float3 fields into a flat-float call,
// consistent with this module's convention of not exposing math vector types to Python.
struct PyDeferredLightingInputs : donut::render::DeferredLightingPass::Inputs {
    std::vector<std::shared_ptr<donut::engine::Light>> ownedLights;

    void SetLights(std::vector<std::shared_ptr<donut::engine::Light>> newLights) {
        ownedLights = std::move(newLights);
        lights = &ownedLights;
    }

    void SetAmbientColors(float topR, float topG, float topB, float bottomR, float bottomG, float bottomB) {
        ambientColorTop = donut::math::float3(topR, topG, topB);
        ambientColorBottom = donut::math::float3(bottomR, bottomG, bottomB);
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
    const std::vector<std::string> &includePaths,
    bool requiresVulkan11)
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
        // Wave Operations (e.g. WaveActiveBitOr/WaveIsFirstLane, used by
        // shaders/work_graphs/light_culling.hlsl) need Vulkan 1.1+, above DXC's default target
        // env -- same reason CompileShaderLibraryWithDXC below sets this for its RT shaders.
        // Opt-in only (unlike the library variant): raising the target env for every shader
        // compiled through this function, regardless of whether it actually uses Vulkan 1.1+
        // features, is an unscoped behavior change for every other example that calls
        // pyd.CompileShader on Vulkan.
        if (requiresVulkan11) {
            args.push_back(L"-fspv-target-env=vulkan1.2");
        }
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

    pybind11::native_enum<nvrhi::CpuAccessMode>(m, "CpuAccessMode", "enum.Enum")
        .value("None_", nvrhi::CpuAccessMode::None)
        .value("Read", nvrhi::CpuAccessMode::Read)
        .value("Write", nvrhi::CpuAccessMode::Write)
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

    // enum.IntFlag, not enum.Enum -- ResourceStates is a real C++ bitmask (see nvrhi.h's
    // operator| overloads), and some resources need combined states, e.g. a buffer that's both
    // read by shaders and used to build an accel struct needs
    // ShaderResource | AccelStructBuildInput (see rt_particles.py).
    pybind11::native_enum<nvrhi::ResourceStates>(m, "ResourceStates", "enum.IntFlag")
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

    pybind11::native_enum<nvrhi::TextureDimension>(m, "TextureDimension", "enum.Enum")
        .value("Unknown", nvrhi::TextureDimension::Unknown)
        .value("Texture1D", nvrhi::TextureDimension::Texture1D)
        .value("Texture1DArray", nvrhi::TextureDimension::Texture1DArray)
        .value("Texture2D", nvrhi::TextureDimension::Texture2D)
        .value("Texture2DArray", nvrhi::TextureDimension::Texture2DArray)
        .value("TextureCube", nvrhi::TextureDimension::TextureCube)
        .value("TextureCubeArray", nvrhi::TextureDimension::TextureCubeArray)
        .value("Texture2DMS", nvrhi::TextureDimension::Texture2DMS)
        .value("Texture2DMSArray", nvrhi::TextureDimension::Texture2DMSArray)
        .value("Texture3D", nvrhi::TextureDimension::Texture3D)
        .finalize();

    pybind11::native_enum<nvrhi::VariableShadingRate>(m, "VariableShadingRate", "enum.Enum")
        .value("e1x1", nvrhi::VariableShadingRate::e1x1)
        .value("e1x2", nvrhi::VariableShadingRate::e1x2)
        .value("e2x1", nvrhi::VariableShadingRate::e2x1)
        .value("e2x2", nvrhi::VariableShadingRate::e2x2)
        .value("e2x4", nvrhi::VariableShadingRate::e2x4)
        .value("e4x2", nvrhi::VariableShadingRate::e4x2)
        .value("e4x4", nvrhi::VariableShadingRate::e4x4)
        .finalize();

    pybind11::native_enum<nvrhi::ShadingRateCombiner>(m, "ShadingRateCombiner", "enum.Enum")
        .value("Passthrough", nvrhi::ShadingRateCombiner::Passthrough)
        .value("Override", nvrhi::ShadingRateCombiner::Override)
        .value("Min", nvrhi::ShadingRateCombiner::Min)
        .value("Max", nvrhi::ShadingRateCombiner::Max)
        .value("ApplyRelative", nvrhi::ShadingRateCombiner::ApplyRelative)
        .finalize();

    pybind11::native_enum<nvrhi::rt::GeometryFlags>(m, "GeometryFlags", "enum.Enum")
        .value("None_", nvrhi::rt::GeometryFlags::None)
        .value("Opaque", nvrhi::rt::GeometryFlags::Opaque)
        .value("NoDuplicateAnyHitInvocation", nvrhi::rt::GeometryFlags::NoDuplicateAnyHitInvocation)
        .finalize();

    // Only the flag rt_particles.py actually sets (PreferFastTrace) plus None (the default) --
    // matching the "only bind what's needed" convention used throughout.
    pybind11::native_enum<nvrhi::rt::AccelStructBuildFlags>(m, "AccelStructBuildFlags", "enum.Enum")
        .value("None_", nvrhi::rt::AccelStructBuildFlags::None)
        .value("PreferFastTrace", nvrhi::rt::AccelStructBuildFlags::PreferFastTrace)
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

    py::class_<nvrhi::IDevice, std::unique_ptr<nvrhi::IDevice, py::nodelete>> device(m, "Device");

    // ITexture/IFramebuffer instances can be either borrowed (swap-chain resources, returned
    // by raw pointer with return_value_policy::reference below) or owned (created via
    // Device.createTexture/createFramebuffer, via DetachToShared); shared_ptr as the holder
    // supports both without conflating lifetimes.
    py::class_<nvrhi::ITexture, std::shared_ptr<nvrhi::ITexture>> texture(m, "Texture");
    py::class_<nvrhi::IFramebuffer, std::shared_ptr<nvrhi::IFramebuffer>> framebuffer(m, "Framebuffer");

    // nvrhi objects created through factory calls below: each create*() call returns one
    // owning reference, handed to Python as a std::shared_ptr that Releases() on collection.
    py::class_<nvrhi::IShader, std::shared_ptr<nvrhi::IShader>>(m, "Shader");
    py::class_<nvrhi::ITimerQuery, std::shared_ptr<nvrhi::ITimerQuery>>(m, "TimerQuery");
    py::class_<nvrhi::IGraphicsPipeline, std::shared_ptr<nvrhi::IGraphicsPipeline>>(m, "GraphicsPipeline");
    py::class_<nvrhi::IMeshletPipeline, std::shared_ptr<nvrhi::IMeshletPipeline>>(m, "MeshletPipeline");
    py::class_<nvrhi::IComputePipeline, std::shared_ptr<nvrhi::IComputePipeline>>(m, "ComputePipeline");
    py::class_<nvrhi::ICommandList, std::shared_ptr<nvrhi::ICommandList>> commandList(m, "CommandList");
    py::class_<nvrhi::IBuffer, std::shared_ptr<nvrhi::IBuffer>> buffer(m, "Buffer");
    py::class_<nvrhi::IBindingLayout, std::shared_ptr<nvrhi::IBindingLayout>> bindingLayout(m, "BindingLayout");
    py::class_<nvrhi::IBindingSet, std::shared_ptr<nvrhi::IBindingSet>> bindingSet(m, "BindingSet");
    py::class_<nvrhi::ISampler, std::shared_ptr<nvrhi::ISampler>>(m, "Sampler");
    py::class_<nvrhi::rt::IAccelStruct, std::shared_ptr<nvrhi::rt::IAccelStruct>> accelStruct(m, "AccelStruct");
    py::class_<nvrhi::rt::IShaderTable, std::shared_ptr<nvrhi::rt::IShaderTable>> shaderTable(m, "ShaderTable");
    py::class_<nvrhi::rt::IPipeline, std::shared_ptr<nvrhi::rt::IPipeline>> rtPipeline(m, "RayTracingPipeline");
    py::class_<nvrhi::IShaderLibrary, std::shared_ptr<nvrhi::IShaderLibrary>> shaderLibrary(m, "ShaderLibrary");
    py::class_<nvrhi::IInputLayout, std::shared_ptr<nvrhi::IInputLayout>>(m, "InputLayout");

    // One Vulkan spec-constant override (constantID declared in HLSL via
    // [[vk::constant_id(N)]]) for Device.createShaderSpecialization. The value union is
    // exposed as three separate static factories (matching the C++ API) rather than one
    // constructor, since the active union member depends on which factory was used.
    py::class_<nvrhi::ShaderSpecialization>(m, "ShaderSpecialization")
        .def_static("UInt32", &nvrhi::ShaderSpecialization::UInt32, py::arg("constantID"), py::arg("value"))
        .def_static("Int32", &nvrhi::ShaderSpecialization::Int32, py::arg("constantID"), py::arg("value"))
        .def_static("Float", &nvrhi::ShaderSpecialization::Float, py::arg("constantID"), py::arg("value"));

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

    py::class_<nvrhi::VertexAttributeDesc>(m, "VertexAttributeDesc")
        .def(py::init<>())
        .def_readwrite("name", &nvrhi::VertexAttributeDesc::name)
        .def_readwrite("format", &nvrhi::VertexAttributeDesc::format)
        .def_readwrite("arraySize", &nvrhi::VertexAttributeDesc::arraySize)
        .def_readwrite("bufferIndex", &nvrhi::VertexAttributeDesc::bufferIndex)
        .def_readwrite("offset", &nvrhi::VertexAttributeDesc::offset)
        .def_readwrite("elementStride", &nvrhi::VertexAttributeDesc::elementStride)
        .def_readwrite("isInstanced", &nvrhi::VertexAttributeDesc::isInstanced);

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
        .def_property("inputLayout",
            [](const nvrhi::GraphicsPipelineDesc &d) -> nvrhi::IInputLayout* { return d.inputLayout.Get(); },
            [](nvrhi::GraphicsPipelineDesc &d, nvrhi::IInputLayout* layout) { d.inputLayout = layout; },
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
        }, py::arg("bindingSet"))
        // vertexBuffers is a fixed-capacity static_vector in nvrhi, not a std::vector, so it's
        // appended to via this method rather than exposed as a plain read-write list.
        .def("addVertexBuffer", [](nvrhi::GraphicsState &self, nvrhi::IBuffer* buffer, uint32_t slot, uint64_t offset) {
            self.vertexBuffers.push_back(nvrhi::VertexBufferBinding{buffer, slot, offset});
        }, py::arg("buffer"), py::arg("slot"), py::arg("offset") = 0)
        .def("setIndexBuffer", [](nvrhi::GraphicsState &self, nvrhi::IBuffer* buffer, nvrhi::Format format, uint32_t offset) {
            self.indexBuffer.buffer = buffer;
            self.indexBuffer.format = format;
            self.indexBuffer.offset = offset;
        }, py::arg("buffer"), py::arg("format"), py::arg("offset") = 0);

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

    py::class_<nvrhi::VariableRateShadingState>(m, "VariableRateShadingState")
        .def(py::init<>())
        .def_readwrite("enabled", &nvrhi::VariableRateShadingState::enabled)
        .def_readwrite("shadingRate", &nvrhi::VariableRateShadingState::shadingRate)
        .def_readwrite("pipelinePrimitiveCombiner", &nvrhi::VariableRateShadingState::pipelinePrimitiveCombiner)
        .def_readwrite("imageCombiner", &nvrhi::VariableRateShadingState::imageCombiner);

    py::class_<nvrhi::VariableRateShadingFeatureInfo>(m, "VariableRateShadingFeatureInfo")
        .def_readonly("shadingRateImageTileSize", &nvrhi::VariableRateShadingFeatureInfo::shadingRateImageTileSize);

    py::class_<nvrhi::ComputePipelineDesc>(m, "ComputePipelineDesc")
        .def(py::init<>())
        .def_property("CS",
            [](const nvrhi::ComputePipelineDesc &d) -> nvrhi::IShader* { return d.CS.Get(); },
            [](nvrhi::ComputePipelineDesc &d, nvrhi::IShader* shader) { d.CS = shader; },
            py::return_value_policy::reference)
        .def("addBindingLayout", [](nvrhi::ComputePipelineDesc &self, nvrhi::IBindingLayout* layout) {
            self.addBindingLayout(layout);
        }, py::arg("layout"));

    py::class_<nvrhi::ComputeState>(m, "ComputeState")
        .def(py::init<>())
        .def_property("pipeline",
            [](const nvrhi::ComputeState &s) -> nvrhi::IComputePipeline* { return s.pipeline; },
            [](nvrhi::ComputeState &s, nvrhi::IComputePipeline* p) { s.pipeline = p; },
            py::return_value_policy::reference)
        .def("addBindingSet", [](nvrhi::ComputeState &self, nvrhi::IBindingSet* set) {
            self.addBindingSet(set);
        }, py::arg("bindingSet"));

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
        .def_readwrite("cpuAccess", &nvrhi::BufferDesc::cpuAccess)
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
        .def_readwrite("isTypeless", &nvrhi::TextureDesc::isTypeless)
        .def_readwrite("isShadingRateSurface", &nvrhi::TextureDesc::isShadingRateSurface)
        .def_readwrite("dimension", &nvrhi::TextureDesc::dimension)
        .def_readwrite("clearValue", &nvrhi::TextureDesc::clearValue)
        .def_readwrite("useClearValue", &nvrhi::TextureDesc::useClearValue)
        .def_readwrite("initialState", &nvrhi::TextureDesc::initialState)
        .def_readwrite("keepInitialState", &nvrhi::TextureDesc::keepInitialState);

    py::class_<nvrhi::FramebufferAttachment>(m, "FramebufferAttachment")
        .def_property_readonly("texture", [](const nvrhi::FramebufferAttachment &a) -> nvrhi::ITexture* { return a.texture; },
            py::return_value_policy::reference);

    py::class_<nvrhi::FramebufferDesc>(m, "FramebufferDesc")
        .def(py::init<>())
        .def("getColorAttachment", [](const nvrhi::FramebufferDesc &self, size_t index) { return self.colorAttachments[index]; },
            py::arg("index"))
        .def("addColorAttachment", [](nvrhi::FramebufferDesc &self, const nvrhi::FramebufferAttachment &attachment) {
            self.addColorAttachment(attachment);
        }, py::arg("attachment"))
        .def("setDepthAttachment", [](nvrhi::FramebufferDesc &self, nvrhi::ITexture* texture) {
            self.setDepthAttachment(texture);
        }, py::arg("texture"));

    // BindingLayoutItem/BindingSetItem pack a bitfield + union that pybind11 can't expose as
    // plain properties; Python only ever obtains instances through these static factories,
    // matching how nvrhi's own C++ call sites are expected to construct them.
    py::class_<nvrhi::BindingLayoutItem>(m, "BindingLayoutItem")
        .def_static("Texture_UAV", &nvrhi::BindingLayoutItem::Texture_UAV, py::arg("slot"))
        .def_static("Texture_SRV", &nvrhi::BindingLayoutItem::Texture_SRV, py::arg("slot"))
        .def_static("RawBuffer_SRV", &nvrhi::BindingLayoutItem::RawBuffer_SRV, py::arg("slot"))
        .def_static("StructuredBuffer_SRV", &nvrhi::BindingLayoutItem::StructuredBuffer_SRV, py::arg("slot"))
        .def_static("TypedBuffer_SRV", &nvrhi::BindingLayoutItem::TypedBuffer_SRV, py::arg("slot"))
        .def_static("TypedBuffer_UAV", &nvrhi::BindingLayoutItem::TypedBuffer_UAV, py::arg("slot"))
        .def_static("StructuredBuffer_UAV", &nvrhi::BindingLayoutItem::StructuredBuffer_UAV, py::arg("slot"))
        .def_static("ConstantBuffer", &nvrhi::BindingLayoutItem::ConstantBuffer, py::arg("slot"))
        .def_static("VolatileConstantBuffer", &nvrhi::BindingLayoutItem::VolatileConstantBuffer, py::arg("slot"))
        .def_static("Sampler", &nvrhi::BindingLayoutItem::Sampler, py::arg("slot"))
        .def_static("RayTracingAccelStruct", &nvrhi::BindingLayoutItem::RayTracingAccelStruct, py::arg("slot"))
        .def_static("PushConstants", &nvrhi::BindingLayoutItem::PushConstants, py::arg("slot"), py::arg("byteSize"));

    py::class_<nvrhi::BindingLayoutDesc>(m, "BindingLayoutDesc")
        .def(py::init<>())
        .def_readwrite("visibility", &nvrhi::BindingLayoutDesc::visibility)
        // 0 (default) unless the binding layout needs to sit in a non-zero register space --
        // e.g. a per-hit-group "local" root signature space in a ray tracing pipeline that
        // also has a "global" space at 0 (see rt_reflections.py).
        .def_readwrite("registerSpace", &nvrhi::BindingLayoutDesc::registerSpace)
        .def_readwrite("bindings", &nvrhi::BindingLayoutDesc::bindings);

    py::class_<nvrhi::BufferRange>(m, "BufferRange")
        .def(py::init<>())
        .def(py::init<uint64_t, uint64_t>(), py::arg("byteOffset"), py::arg("byteSize"))
        .def_readwrite("byteOffset", &nvrhi::BufferRange::byteOffset)
        .def_readwrite("byteSize", &nvrhi::BufferRange::byteSize);

    py::class_<nvrhi::BindingSetItem>(m, "BindingSetItem")
        .def_static("Texture_UAV", [](uint32_t slot, nvrhi::ITexture* texture) {
            return nvrhi::BindingSetItem::Texture_UAV(slot, texture);
        }, py::arg("slot"), py::arg("texture"))
        // Overload with an explicit format, for typed UAV/SRV views that override the
        // texture's own (possibly typeless) format -- e.g. a shading-rate surface.
        .def_static("Texture_UAV", [](uint32_t slot, nvrhi::ITexture* texture, nvrhi::Format format) {
            return nvrhi::BindingSetItem::Texture_UAV(slot, texture, format);
        }, py::arg("slot"), py::arg("texture"), py::arg("format"))
        .def_static("Texture_SRV", [](uint32_t slot, nvrhi::ITexture* texture) {
            return nvrhi::BindingSetItem::Texture_SRV(slot, texture);
        }, py::arg("slot"), py::arg("texture"))
        .def_static("Texture_SRV", [](uint32_t slot, nvrhi::ITexture* texture, nvrhi::Format format) {
            return nvrhi::BindingSetItem::Texture_SRV(slot, texture, format);
        }, py::arg("slot"), py::arg("texture"), py::arg("format"))
        .def_static("RayTracingAccelStruct", [](uint32_t slot, nvrhi::rt::IAccelStruct* accelStruct) {
            return nvrhi::BindingSetItem::RayTracingAccelStruct(slot, accelStruct);
        }, py::arg("slot"), py::arg("accelStruct"))
        .def_static("ConstantBuffer", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::ConstantBuffer(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
        // Overload taking an explicit BufferRange, for binding one slice of a larger buffer
        // (e.g. one entry of an array of same-sized constant buffer structs).
        .def_static("ConstantBuffer", [](uint32_t slot, nvrhi::IBuffer* buffer, const nvrhi::BufferRange &range) {
            return nvrhi::BindingSetItem::ConstantBuffer(slot, buffer, range);
        }, py::arg("slot"), py::arg("buffer"), py::arg("range"))
        .def_static("StructuredBuffer_SRV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::StructuredBuffer_SRV(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
        // Registers a ByteAddressBuffer SRV in the bindless descriptor table (see
        // DescriptorTableManager.CreateDescriptorHandle) -- rt_particles.py uses this for its
        // dynamic particle index/vertex buffers.
        .def_static("RawBuffer_SRV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::RawBuffer_SRV(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
        .def_static("TypedBuffer_SRV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::TypedBuffer_SRV(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
        // Overload with an explicit format and byte range, for viewing one slice of a larger
        // buffer through a specific typed format -- e.g. one mesh's slice of a shared
        // index/vertex buffer, reinterpreted as a different element type/format than the
        // buffer's own (see rt_reflections.py).
        .def_static("TypedBuffer_SRV", [](uint32_t slot, nvrhi::IBuffer* buffer, nvrhi::Format format, const nvrhi::BufferRange &range) {
            return nvrhi::BindingSetItem::TypedBuffer_SRV(slot, buffer, format, range);
        }, py::arg("slot"), py::arg("buffer"), py::arg("format"), py::arg("range"))
        .def_static("TypedBuffer_UAV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::TypedBuffer_UAV(slot, buffer);
        }, py::arg("slot"), py::arg("buffer"))
        .def_static("StructuredBuffer_UAV", [](uint32_t slot, nvrhi::IBuffer* buffer) {
            return nvrhi::BindingSetItem::StructuredBuffer_UAV(slot, buffer);
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

    m.def("CreateVolatileConstantBufferDesc", &nvrhi::utils::CreateVolatileConstantBufferDesc,
        py::arg("byteSize"), py::arg("debugName"), py::arg("maxVersions"));

    m.def("CreateStaticConstantBufferDesc", &nvrhi::utils::CreateStaticConstantBufferDesc,
        py::arg("byteSize"), py::arg("debugName"));

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
        // Byte offsets into indexBuffer/vertexBuffer -- 0 (default) for a geometry that owns
        // its whole buffer; non-zero when several geometries/meshes share one buffer (see
        // rt_shadows.py/rt_reflections.py, which build BLASes from real scene meshes).
        .def_readwrite("indexOffset", &nvrhi::rt::GeometryTriangles::indexOffset)
        .def_readwrite("vertexOffset", &nvrhi::rt::GeometryTriangles::vertexOffset)
        .def_readwrite("indexCount", &nvrhi::rt::GeometryTriangles::indexCount)
        .def_readwrite("vertexCount", &nvrhi::rt::GeometryTriangles::vertexCount)
        .def_readwrite("vertexStride", &nvrhi::rt::GeometryTriangles::vertexStride);

    // Axis-aligned box geometry for procedural/intersection-shader primitives (e.g. the
    // ray-traced particle billboards in rt_particles.py, which intersect an analytic quad
    // inside a unit AABB rather than real triangles).
    py::class_<nvrhi::rt::GeometryAABB>(m, "GeometryAABB")
        .def(py::init<>())
        .def_readwrite("minX", &nvrhi::rt::GeometryAABB::minX)
        .def_readwrite("minY", &nvrhi::rt::GeometryAABB::minY)
        .def_readwrite("minZ", &nvrhi::rt::GeometryAABB::minZ)
        .def_readwrite("maxX", &nvrhi::rt::GeometryAABB::maxX)
        .def_readwrite("maxY", &nvrhi::rt::GeometryAABB::maxY)
        .def_readwrite("maxZ", &nvrhi::rt::GeometryAABB::maxZ);

    py::class_<nvrhi::rt::GeometryAABBs>(m, "GeometryAABBs")
        .def(py::init<>())
        .def("setBuffer", [](nvrhi::rt::GeometryAABBs &self, nvrhi::IBuffer* buffer) -> nvrhi::rt::GeometryAABBs& {
            return self.setBuffer(buffer);
        }, py::arg("buffer"), py::return_value_policy::reference)
        .def("setCount", [](nvrhi::rt::GeometryAABBs &self, uint32_t count) -> nvrhi::rt::GeometryAABBs& {
            return self.setCount(count);
        }, py::arg("count"), py::return_value_policy::reference);

    py::class_<nvrhi::rt::GeometryDesc>(m, "GeometryDesc")
        .def(py::init<>())
        .def_readwrite("flags", &nvrhi::rt::GeometryDesc::flags)
        .def("setTriangles", [](nvrhi::rt::GeometryDesc &self, const nvrhi::rt::GeometryTriangles &triangles) {
            self.setTriangles(triangles);
        }, py::arg("triangles"))
        .def("setAABBs", [](nvrhi::rt::GeometryDesc &self, const nvrhi::rt::GeometryAABBs &aabbs) {
            self.setAABBs(aabbs);
        }, py::arg("aabbs"));

    py::class_<nvrhi::rt::AccelStructDesc>(m, "AccelStructDesc")
        .def(py::init<>())
        .def_readwrite("debugName", &nvrhi::rt::AccelStructDesc::debugName)
        .def_readwrite("buildFlags", &nvrhi::rt::AccelStructDesc::buildFlags)
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
        .def("setBLAS", [](nvrhi::rt::InstanceDesc &self, nvrhi::rt::IAccelStruct* value) { self.setBLAS(value); }, py::arg("value"))
        // Fills the row-major instance transform from a scene graph node's world transform
        // (dm::affineToColumnMajor(node->GetLocalToWorldTransformFloat(), ...)) -- math types
        // aren't exposed to Python, so this hides the conversion behind one call, matching the
        // existing convention (see PlanarView.SetMatricesFromCamera).
        .def("setTransformFromNode", [](nvrhi::rt::InstanceDesc &self, const donut::engine::SceneGraphNode &node) {
            donut::math::affineToColumnMajor(node.GetLocalToWorldTransformFloat(), self.transform);
        }, py::arg("node"))
        // Fills the row-major instance transform as scale-then-translate, for instances with
        // no scene graph node of their own (e.g. rt_particles.py's one intersection-BLAS
        // instance per particle, scaled to its radius and translated to its position).
        .def("setTransformScaleTranslation", [](nvrhi::rt::InstanceDesc &self,
                float sx, float sy, float sz, float tx, float ty, float tz) {
            const donut::math::affine3 transform = donut::math::scaling(donut::math::float3(sx, sy, sz))
                * donut::math::translation(donut::math::float3(tx, ty, tz));
            donut::math::affineToColumnMajor(transform, self.transform);
        }, py::arg("sx"), py::arg("sy"), py::arg("sz"), py::arg("tx"), py::arg("ty"), py::arg("tz"));

    py::class_<nvrhi::rt::PipelineShaderDesc>(m, "PipelineShaderDesc")
        .def(py::init<>())
        .def("setShader", [](nvrhi::rt::PipelineShaderDesc &self, nvrhi::IShader* shader) { self.setShader(shader); }, py::arg("shader"));

    py::class_<nvrhi::rt::PipelineHitGroupDesc>(m, "PipelineHitGroupDesc")
        .def(py::init<>())
        .def("setExportName", [](nvrhi::rt::PipelineHitGroupDesc &self, const std::string &value) { self.setExportName(value); }, py::arg("value"))
        .def("setClosestHitShader", [](nvrhi::rt::PipelineHitGroupDesc &self, nvrhi::IShader* shader) { self.setClosestHitShader(shader); }, py::arg("shader"))
        .def("setBindingLayout", [](nvrhi::rt::PipelineHitGroupDesc &self, nvrhi::IBindingLayout* layout) { self.setBindingLayout(layout); }, py::arg("layout"));

    py::class_<nvrhi::rt::PipelineDesc>(m, "RayTracingPipelineDesc")
        .def(py::init<>())
        .def_readwrite("maxPayloadSize", &nvrhi::rt::PipelineDesc::maxPayloadSize)
        .def_readwrite("maxRecursionDepth", &nvrhi::rt::PipelineDesc::maxRecursionDepth)
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

    py::class_<nvrhi::CommandListParameters>(m, "CommandListParameters")
        .def(py::init<>())
        .def("setEnableImmediateExecution", [](nvrhi::CommandListParameters &self, bool value) -> nvrhi::CommandListParameters& {
            return self.setEnableImmediateExecution(value);
        }, py::arg("value"), py::return_value_policy::reference);

    device.def("getGraphicsAPI", &nvrhi::IDevice::getGraphicsAPI);
    device.def("createCommandList", [](nvrhi::IDevice &self, const nvrhi::CommandListParameters &params) {
        return DetachToShared(self.createCommandList(params));
    }, py::arg("params") = nvrhi::CommandListParameters());
    // Batched, atomic submission of multiple command lists in one call -- used by examples
    // that record several command lists (e.g. one per thread) and submit them together, as
    // opposed to executeCommandList's one-at-a-time submission.
    device.def("executeCommandLists", [](nvrhi::IDevice &self, const std::vector<nvrhi::ICommandList*> &commandLists, nvrhi::CommandQueue executionQueue) {
        return self.executeCommandLists(commandLists.data(), commandLists.size(), executionQueue);
    }, py::arg("commandLists"), py::arg("executionQueue") = nvrhi::CommandQueue::Graphics);
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
    // Bakes Vulkan spec constants (declared in HLSL via [[vk::constant_id(N)]]) into a new
    // shader derived from baseShader -- Vulkan-only, matching nvrhi::Feature::ShaderSpecializations.
    device.def("createShaderSpecialization", [](nvrhi::IDevice &self, nvrhi::IShader* baseShader,
            const std::vector<nvrhi::ShaderSpecialization> &constants) {
        return DetachToShared(self.createShaderSpecialization(baseShader, constants.data(), uint32_t(constants.size())));
    }, py::arg("baseShader"), py::arg("constants"));
    device.def("queryFeatureSupport", [](nvrhi::IDevice &self, nvrhi::Feature feature) {
        return self.queryFeatureSupport(feature);
    }, py::arg("feature"));
    device.def("createBuffer", [](nvrhi::IDevice &self, const nvrhi::BufferDesc &desc) {
        return DetachToShared(self.createBuffer(desc));
    }, py::arg("desc"));
    // Combinator wrapping mapBuffer(Read)+memcpy+unmapBuffer into one safe call, so raw mapped
    // pointers are never exposed to Python -- same spirit as FillPlanarViewConstants returning
    // bytes rather than a pointer. `buffer` must have been created with cpuAccess=Read (or
    // Write, which is also host-visible) and byteSize must not exceed its actual size.
    device.def("readBuffer", [](nvrhi::IDevice &self, nvrhi::IBuffer* buffer, size_t byteSize) {
        void* mapped = self.mapBuffer(buffer, nvrhi::CpuAccessMode::Read);
        py::bytes result(reinterpret_cast<const char*>(mapped), byteSize);
        self.unmapBuffer(buffer);
        return result;
    }, py::arg("buffer"), py::arg("byteSize"));
    device.def("createTexture", [](nvrhi::IDevice &self, const nvrhi::TextureDesc &desc) {
        return DetachToShared(self.createTexture(desc));
    }, py::arg("desc"));
    device.def("createFramebuffer", [](nvrhi::IDevice &self, const nvrhi::FramebufferDesc &desc) {
        return DetachToShared(self.createFramebuffer(desc));
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
    device.def("createInputLayout", [](nvrhi::IDevice &self, const std::vector<nvrhi::VertexAttributeDesc> &attributes, nvrhi::IShader* vertexShader) {
        return DetachToShared(self.createInputLayout(attributes.data(), uint32_t(attributes.size()), vertexShader));
    }, py::arg("attributes"), py::arg("vertexShader"));
    device.def("createComputePipeline", [](nvrhi::IDevice &self, const nvrhi::ComputePipelineDesc &desc) {
        return DetachToShared(self.createComputePipeline(desc));
    }, py::arg("desc"));
    // Wraps the queryFeatureSupport(Feature, void*, size_t) overload for VariableRateShading
    // specifically, which reports the hardware's shading-rate-image tile size.
    device.def("queryVariableRateShadingInfo", [](nvrhi::IDevice &self) {
        nvrhi::VariableRateShadingFeatureInfo info{};
        self.queryFeatureSupport(nvrhi::Feature::VariableRateShading, &info, sizeof(info));
        return info;
    });
    device.def("waitForIdle", &nvrhi::IDevice::waitForIdle);
    // Wrapped through DetachToShared like every other create*() factory below -- the raw
    // method returns nvrhi::TimerQueryHandle (RefCountPtr<ITimerQuery>), which pybind11 can't
    // convert directly to the std::shared_ptr<ITimerQuery> holder TimerQuery is registered with.
    device.def("createTimerQuery", [](nvrhi::IDevice &self) {
        return DetachToShared(self.createTimerQuery());
    });
    // Non-blocking: true once the query's result is ready to read. GPU timing samples are
    // read a few frames late on purpose (see work_graphs.py's timer-ring buffering) so this
    // never has to stall waiting for the queue to catch up.
    device.def("pollTimerQuery", &nvrhi::IDevice::pollTimerQuery, py::arg("query"));
    device.def("getTimerQueryTime", &nvrhi::IDevice::getTimerQueryTime, py::arg("query"));
    device.def("resetTimerQuery", &nvrhi::IDevice::resetTimerQuery, py::arg("query"));

#ifdef NVRHI_WITH_DX12
    class D3D12WorkGraphPipeline
    {
    public:
        D3D12WorkGraphPipeline(
            nvrhi::IDevice* device,
            nvrhi::IShaderLibrary* shaderLibrary,
            nvrhi::IComputePipeline* rootSigSourcePipeline,
            const std::string& workGraphName,
            const std::string& broadcastEntryNodeName,
            uint32_t dispatchGridX,
            uint32_t dispatchGridY,
            uint32_t dispatchGridZ)
        {
            ID3D12Device* deviceD3D12 = device->getNativeObject(nvrhi::ObjectTypes::D3D12_Device);
            if (!deviceD3D12)
                throw std::runtime_error("D3D12WorkGraphPipeline: device is not a D3D12 device");

            D3D12_FEATURE_DATA_D3D12_OPTIONS21 options = {};
            HRESULT hr = deviceD3D12->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS21, &options, sizeof(options));
            if (FAILED(hr) || options.WorkGraphsTier == D3D12_WORK_GRAPHS_TIER_NOT_SUPPORTED)
                throw std::runtime_error("D3D12WorkGraphPipeline: this device/driver does not support D3D12 Work Graphs");

            Microsoft::WRL::ComPtr<ID3D12Device5> deviceD3D12_5;
            hr = deviceD3D12->QueryInterface(IID_PPV_ARGS(&deviceD3D12_5));
            if (FAILED(hr))
                throw std::runtime_error("D3D12WorkGraphPipeline: could not query ID3D12Device5");

            ID3D12RootSignature* rootSignature = rootSigSourcePipeline->getNativeObject(nvrhi::ObjectTypes::D3D12_RootSignature);
            if (!rootSignature)
                throw std::runtime_error("D3D12WorkGraphPipeline: rootSigSourcePipeline has no D3D12 root signature");

            D3D12_SHADER_BYTECODE libBytecode = {};
            shaderLibrary->getBytecode(&libBytecode.pShaderBytecode, &libBytecode.BytecodeLength);

            m_wideName.assign(workGraphName.begin(), workGraphName.end());

            CD3DX12_STATE_OBJECT_DESC soDesc(D3D12_STATE_OBJECT_TYPE_EXECUTABLE);

            auto* librarySubobject = soDesc.CreateSubobject<CD3DX12_DXIL_LIBRARY_SUBOBJECT>();
            librarySubobject->SetDXILLibrary(&libBytecode);

            auto* workGraphSubobject = soDesc.CreateSubobject<CD3DX12_WORK_GRAPH_SUBOBJECT>();
            workGraphSubobject->SetProgramName(m_wideName.c_str());
            workGraphSubobject->IncludeAllAvailableNodes();

            // Override a broadcasting entry node's [NodeDispatchGrid()] attribute, which HLSL
            // can only express as a compile-time constant. Sizes that depend on the viewport
            // (e.g. a tile count) must be supplied here instead -- the alternative, putting
            // SV_DispatchGrid in the entry record, costs performance on every launch for a
            // value that only changes on resize. Empty name = keep the shader's own attribute.
            if (!broadcastEntryNodeName.empty())
            {
                m_wideEntryNodeName.assign(broadcastEntryNodeName.begin(), broadcastEntryNodeName.end());
                auto* nodeOverrides = workGraphSubobject->CreateBroadcastingLaunchNodeOverrides(m_wideEntryNodeName.c_str());
                nodeOverrides->DispatchGrid(dispatchGridX, dispatchGridY, dispatchGridZ);
            }

            auto* rootSigSubobject = soDesc.CreateSubobject<CD3DX12_GLOBAL_ROOT_SIGNATURE_SUBOBJECT>();
            rootSigSubobject->SetRootSignature(rootSignature);

            hr = deviceD3D12_5->CreateStateObject(soDesc, IID_PPV_ARGS(&m_stateObject));
            if (FAILED(hr))
            {
                char message[128];
                snprintf(message, sizeof(message), "D3D12WorkGraphPipeline: CreateStateObject failed with HRESULT 0x%08X", (unsigned)hr);
                throw std::runtime_error(message);
            }

            Microsoft::WRL::ComPtr<ID3D12StateObjectProperties1> soProperties;
            hr = m_stateObject->QueryInterface(IID_PPV_ARGS(&soProperties));
            if (FAILED(hr))
                throw std::runtime_error("D3D12WorkGraphPipeline: could not query ID3D12StateObjectProperties1");
            m_programIdentifier = soProperties->GetProgramIdentifier(m_wideName.c_str());

            Microsoft::WRL::ComPtr<ID3D12WorkGraphProperties> workGraphProperties;
            hr = m_stateObject->QueryInterface(IID_PPV_ARGS(&workGraphProperties));
            if (FAILED(hr))
                throw std::runtime_error("D3D12WorkGraphPipeline: could not query ID3D12WorkGraphProperties");

            uint32_t workGraphIndex = workGraphProperties->GetWorkGraphIndex(m_wideName.c_str());
            if (workGraphIndex == UINT32_MAX)
                throw std::runtime_error("D3D12WorkGraphPipeline: work graph name not found in the state object");

            D3D12_WORK_GRAPH_MEMORY_REQUIREMENTS memReqs = {};
            workGraphProperties->GetWorkGraphMemoryRequirements(workGraphIndex, &memReqs);
            m_backingMemorySize = memReqs.MaxSizeInBytes;
        }

        uint64_t getBackingMemorySize() const { return m_backingMemorySize; }
        D3D12_PROGRAM_IDENTIFIER getProgramIdentifier() const { return m_programIdentifier; }

    private:
        Microsoft::WRL::ComPtr<ID3D12StateObject> m_stateObject;
        std::wstring m_wideName;
        // Kept alive as a member because CreateBroadcastingLaunchNodeOverrides stores the
        // pointer, and it must still be valid when CreateStateObject reads it below.
        std::wstring m_wideEntryNodeName;
        D3D12_PROGRAM_IDENTIFIER m_programIdentifier{};
        uint64_t m_backingMemorySize = 0;
    };

    py::class_<D3D12WorkGraphPipeline, std::shared_ptr<D3D12WorkGraphPipeline>>(m, "D3D12WorkGraphPipeline")
        .def(py::init<nvrhi::IDevice*, nvrhi::IShaderLibrary*, nvrhi::IComputePipeline*, const std::string&,
                const std::string&, uint32_t, uint32_t, uint32_t>(),
            py::arg("device"), py::arg("shaderLibrary"), py::arg("rootSigSourcePipeline"), py::arg("workGraphName"),
            py::arg("broadcastEntryNodeName") = "", py::arg("dispatchGridX") = 1,
            py::arg("dispatchGridY") = 1, py::arg("dispatchGridZ") = 1)
        .def("getBackingMemorySize", &D3D12WorkGraphPipeline::getBackingMemorySize);
#endif // NVRHI_WITH_DX12

    // open/close and the calls below marked with gil_scoped_release are the ones
    // threaded_rendering.py's worker threads call concurrently while recording independent
    // per-face command lists; releasing the GIL here is what lets Python's threading actually
    // run them in parallel instead of just interleaving under the GIL. No other CommandList
    // methods release the GIL -- this is intentionally scoped to what that example needs.
    commandList.def("open", &nvrhi::ICommandList::open, py::call_guard<py::gil_scoped_release>());
    commandList.def("close", &nvrhi::ICommandList::close, py::call_guard<py::gil_scoped_release>());
    commandList.def("setGraphicsState", &nvrhi::ICommandList::setGraphicsState, py::arg("state"));
    commandList.def("draw", &nvrhi::ICommandList::draw, py::arg("args"));
    commandList.def("drawIndexed", &nvrhi::ICommandList::drawIndexed, py::arg("args"));
    commandList.def("setMeshletState", &nvrhi::ICommandList::setMeshletState, py::arg("state"));
    commandList.def("setComputeState", &nvrhi::ICommandList::setComputeState, py::arg("state"));
    commandList.def("dispatch", &nvrhi::ICommandList::dispatch,
        py::arg("groupsX"), py::arg("groupsY") = 1, py::arg("groupsZ") = 1);
    commandList.def("dispatchMesh", &nvrhi::ICommandList::dispatchMesh,
        py::arg("groupsX"), py::arg("groupsY") = 1, py::arg("groupsZ") = 1);
    commandList.def("writeBuffer", [](nvrhi::ICommandList &self, nvrhi::IBuffer* buffer, py::buffer data, uint64_t destOffsetBytes) {
        py::buffer_info info = data.request();
        self.writeBuffer(buffer, info.ptr, static_cast<size_t>(info.size * info.itemsize), destOffsetBytes);
    }, py::arg("buffer"), py::arg("data"), py::arg("destOffsetBytes") = 0);
    commandList.def("copyBuffer", &nvrhi::ICommandList::copyBuffer,
        py::arg("dest"), py::arg("destOffsetBytes"), py::arg("src"), py::arg("srcOffsetBytes"), py::arg("dataSizeBytes"));
    // Whole-resource texture-to-texture copy (both default TextureSlice()s resolve to "entire
    // texture") -- a plain byte copy, unlike CommonRenderPasses.BlitTexture which samples
    // through a shader (and can apply unwanted color-space/tonemap conversions on data that's
    // already in its final display encoding, e.g. work_graphs.py's RGBA8_UNORM LDR buffer).
    // Matches work_graphs_d3d12.cpp:880's own commandList->copyTexture(...) call exactly.
    commandList.def("copyTexture", [](nvrhi::ICommandList &self, nvrhi::ITexture* dest, nvrhi::ITexture* src) {
        self.copyTexture(dest, nvrhi::TextureSlice(), src, nvrhi::TextureSlice());
    }, py::arg("dest"), py::arg("src"));
#ifdef NVRHI_WITH_DX12
    // NOTE: SetProgram is called directly on the native D3D12 command list and nvrhi's own
    // cached compute state has no idea the bound program changed. A later commandList.
    // setComputeState(...) call with the SAME ComputePipeline object nvrhi last saw will skip
    // re-issuing SetPipelineState (since nvrhi thinks nothing changed), silently leaving the
    // work graph program bound instead. Always setComputeState with a DIFFERENT pipeline object
    // after dispatching a work graph, or re-dispatch another work graph -- never assume the
    // previous compute pipeline is still actually bound at the D3D12 level.
    commandList.def("dispatchWorkGraph", [](nvrhi::ICommandList &self, D3D12WorkGraphPipeline &pipeline,
        nvrhi::IBuffer* backingMemoryBuffer, bool initialize, uint32_t numRecords) {
        ID3D12GraphicsCommandList* baseCommandList = self.getNativeObject(nvrhi::ObjectTypes::D3D12_GraphicsCommandList);
        if (!baseCommandList)
            throw std::runtime_error("dispatchWorkGraph: command list is not a D3D12 command list");

        Microsoft::WRL::ComPtr<ID3D12GraphicsCommandList10> commandListD3D12;
        HRESULT hr = baseCommandList->QueryInterface(IID_PPV_ARGS(&commandListD3D12));
        if (FAILED(hr))
            throw std::runtime_error("dispatchWorkGraph: could not query ID3D12GraphicsCommandList10 (requires a recent Agility SDK)");

        ID3D12Resource* backingMemoryD3D12 = backingMemoryBuffer->getNativeObject(nvrhi::ObjectTypes::D3D12_Resource);
        if (!backingMemoryD3D12)
            throw std::runtime_error("dispatchWorkGraph: backingMemoryBuffer has no D3D12 resource");

        if (backingMemoryD3D12->GetDesc().Width < pipeline.getBackingMemorySize())
            throw std::runtime_error("dispatchWorkGraph: backingMemoryBuffer is smaller than the graph's backing memory requirement");

        D3D12_SET_PROGRAM_DESC setProgramDesc = {};
        setProgramDesc.Type = D3D12_PROGRAM_TYPE_WORK_GRAPH;
        setProgramDesc.WorkGraph.ProgramIdentifier = pipeline.getProgramIdentifier();
        setProgramDesc.WorkGraph.Flags = initialize ? D3D12_SET_WORK_GRAPH_FLAG_INITIALIZE : D3D12_SET_WORK_GRAPH_FLAG_NONE;
        setProgramDesc.WorkGraph.BackingMemory.StartAddress = backingMemoryD3D12->GetGPUVirtualAddress();
        setProgramDesc.WorkGraph.BackingMemory.SizeInBytes = backingMemoryD3D12->GetDesc().Width;
        commandListD3D12->SetProgram(&setProgramDesc);

        D3D12_DISPATCH_GRAPH_DESC dispatchDesc = {};
        dispatchDesc.Mode = D3D12_DISPATCH_MODE_NODE_CPU_INPUT;
        dispatchDesc.NodeCPUInput.EntrypointIndex = 0;
        dispatchDesc.NodeCPUInput.NumRecords = numRecords;
        dispatchDesc.NodeCPUInput.pRecords = nullptr;
        dispatchDesc.NodeCPUInput.RecordStrideInBytes = 0;
        commandListD3D12->DispatchGraph(&dispatchDesc);
    }, py::arg("pipeline"), py::arg("backingMemoryBuffer"), py::arg("initialize"), py::arg("numRecords") = 1);
#endif // NVRHI_WITH_DX12
    commandList.def("buildTopLevelAccelStruct", [](nvrhi::ICommandList &self, nvrhi::rt::IAccelStruct* as, const std::vector<nvrhi::rt::InstanceDesc> &instances) {
        self.buildTopLevelAccelStruct(as, instances.data(), instances.size());
    }, py::arg("as"), py::arg("instances"));
    commandList.def("setRayTracingState", &nvrhi::ICommandList::setRayTracingState, py::arg("state"));
    commandList.def("dispatchRays", &nvrhi::ICommandList::dispatchRays, py::arg("args"));
    commandList.def("setPushConstants", [](nvrhi::ICommandList &self, py::buffer data) {
        py::buffer_info info = data.request();
        self.setPushConstants(info.ptr, static_cast<size_t>(info.size * info.itemsize));
    }, py::arg("data"));
    commandList.def("clearTextureFloat", [](nvrhi::ICommandList &self, nvrhi::ITexture* texture, const nvrhi::Color &clearColor) {
        self.clearTextureFloat(texture, nvrhi::AllSubresources, clearColor);
    }, py::arg("texture"), py::arg("clearColor"));
    // View-scoped overload: clears only the subresources `view` covers (e.g. one face's array
    // slice of a shared cube texture) instead of every subresource. Needed when several views
    // share one texture and each must be cleared independently of the others.
    commandList.def("clearTextureFloat", [](nvrhi::ICommandList &self, nvrhi::ITexture* texture,
            const nvrhi::Color &clearColor, const donut::engine::PlanarView &view) {
        self.clearTextureFloat(texture, view.GetSubresources(), clearColor);
    }, py::arg("texture"), py::arg("clearColor"), py::arg("view"), py::call_guard<py::gil_scoped_release>());
    commandList.def("clearDepthStencilTexture", [](nvrhi::ICommandList &self, nvrhi::ITexture* texture,
            bool clearDepth, float depth, bool clearStencil, uint8_t stencil) {
        self.clearDepthStencilTexture(texture, nvrhi::AllSubresources, clearDepth, depth, clearStencil, stencil);
    }, py::arg("texture"), py::arg("clearDepth"), py::arg("depth"), py::arg("clearStencil"), py::arg("stencil"));
    commandList.def("clearDepthStencilTexture", [](nvrhi::ICommandList &self, nvrhi::ITexture* texture,
            bool clearDepth, float depth, bool clearStencil, uint8_t stencil, const donut::engine::PlanarView &view) {
        self.clearDepthStencilTexture(texture, view.GetSubresources(), clearDepth, depth, clearStencil, stencil);
    }, py::arg("texture"), py::arg("clearDepth"), py::arg("depth"), py::arg("clearStencil"), py::arg("stencil"), py::arg("view"),
       py::call_guard<py::gil_scoped_release>());
    // Manual barrier control: disables nvrhi's automatic per-command-list resource-state
    // tracking so multiple command lists can be recorded concurrently against one shared
    // resource (e.g. different array slices of one cube texture) without each one guessing at
    // stale state left by the others. setResourceStatesForFramebuffer declares the states this
    // command list's framebuffer writes need; commitBarriers submits the resulting barriers.
    commandList.def("setEnableAutomaticBarriers", &nvrhi::ICommandList::setEnableAutomaticBarriers,
        py::arg("enable"), py::call_guard<py::gil_scoped_release>());
    commandList.def("setResourceStatesForFramebuffer", &nvrhi::ICommandList::setResourceStatesForFramebuffer,
        py::arg("framebuffer"), py::call_guard<py::gil_scoped_release>());
    // Explicit state transitions for resources nvrhi's automatic tracking wouldn't otherwise
    // catch in time -- e.g. a skinned mesh's vertex buffer/BLAS between the skinning compute
    // dispatch that just wrote new positions and the BLAS rebuild that reads them this same
    // frame (see rt_bindless.py's BuildTLAS, matching the C++ original's per-frame skinned BLAS
    // update). commitBarriers submits the resulting barriers.
    commandList.def("setBufferState", &nvrhi::ICommandList::setBufferState,
        py::arg("buffer"), py::arg("stateBits"), py::call_guard<py::gil_scoped_release>());
    commandList.def("setAccelStructState", &nvrhi::ICommandList::setAccelStructState,
        py::arg("as"), py::arg("stateBits"), py::call_guard<py::gil_scoped_release>());
    commandList.def("commitBarriers", &nvrhi::ICommandList::commitBarriers, py::call_guard<py::gil_scoped_release>());
    commandList.def("beginTimerQuery", &nvrhi::ICommandList::beginTimerQuery, py::arg("query"));
    commandList.def("endTimerQuery", &nvrhi::ICommandList::endTimerQuery, py::arg("query"));
    // Debug marker ranges. Nestable: each beginMarker must be matched by an endMarker. These
    // are what make an Aftermath crash dump readable -- Aftermath stores markers as hashed
    // 64-bit values and resolves them back to these strings via
    // donut::app::AftermathCrashDump::ResolveMarker, so the innermost live marker names the
    // scope that faulted (see aftermath.py).
    commandList.def("beginMarker", [](nvrhi::ICommandList &self, const std::string &name) {
        self.beginMarker(name.c_str());
    }, py::arg("name"));
    commandList.def("endMarker", &nvrhi::ICommandList::endMarker);

    // True only in builds configured with -DPYDONUT_WITH_AFTERMATH=ON. When False,
    // DeviceCreationParameters has no enableAftermath attribute at all and no crash dumps are
    // written -- the crashes still happen, they just go uncaptured.
    m.attr("AFTERMATH_AVAILABLE") = py::bool_(static_cast<bool>(DONUT_WITH_AFTERMATH));

    // DELIBERATELY UNSAFE -- crash testing only, and there is no way to recover the device
    // afterwards. Destroys the native graphics-API memory backing `buffer` while the GPU may
    // still be reading it, so the next draw that touches it page-faults and NSight Aftermath
    // captures a dump. Used by aftermath.py's "Trigger page fault" button and nothing else.
    //
    // It must reach past NVRHI: destroying the nvrhi::IBuffer would fault on the CPU first,
    // before the GPU ever page-faults (aftermath.cpp:155-157).
    m.def("DestroyBufferMemory_UnsafeForCrashTesting", [](nvrhi::IDevice* device, nvrhi::IBuffer* buffer) {
        const nvrhi::GraphicsAPI api = device->getGraphicsAPI();
#ifdef NVRHI_WITH_DX12
        if (api == nvrhi::GraphicsAPI::D3D12) {
            ID3D12Resource* resource = buffer->getNativeObject(nvrhi::ObjectTypes::D3D12_Resource);
            resource->Release();
            return;
        }
#endif
#if DONUT_WITH_VULKAN
        if (api == nvrhi::GraphicsAPI::VULKAN) {
            PFN_vkFreeMemory freeMemory = ResolveVkFreeMemory();
            if (!freeMemory)
                throw std::runtime_error(
                    "DestroyBufferMemory_UnsafeForCrashTesting: could not resolve vkFreeMemory "
                    "from the Vulkan loader.");
            VkDevice vkDevice = static_cast<VkDevice>(device->getNativeObject(nvrhi::ObjectTypes::VK_Device).pointer);
            VkDeviceMemory memory = static_cast<VkDeviceMemory>(buffer->getNativeObject(nvrhi::ObjectTypes::VK_DeviceMemory).pointer);
            freeMemory(vkDevice, memory, nullptr);
            return;
        }
#endif
        throw std::runtime_error(
            "DestroyBufferMemory_UnsafeForCrashTesting: unsupported graphics API. D3D11 does not "
            "page-fault under these conditions, and D3D12/Vulkan must be compiled in.");
    }, py::arg("device"), py::arg("buffer"));

    m.def("ClearColorAttachment", &nvrhi::utils::ClearColorAttachment,
        py::arg("commandList"), py::arg("framebuffer"), py::arg("attachmentIndex"), py::arg("color"));

    m.def("BuildBottomLevelAccelStruct", &nvrhi::utils::BuildBottomLevelAccelStruct,
        py::arg("commandList"), py::arg("as"), py::arg("desc"));

    // Builds one BLAS per scene mesh and the scene's TLAS (one instance per MeshInstance,
    // transformed by its node's world transform), returning just the finished TLAS. Wraps the
    // whole per-mesh/per-geometry/per-instance traversal (mesh index/vertex offsets, node
    // transforms, etc.) as a single combinator rather than exposing that scene-graph plumbing
    // to Python -- matches the existing convention of wrapping multi-step C++ procedures behind
    // one call (see SceneLoaded(), CreateMaterialConstantBuffer()).
    m.def("BuildSceneAccelStructs", [](nvrhi::IDevice* device, nvrhi::ICommandList* commandList, donut::engine::Scene &scene) {
        std::unordered_map<std::shared_ptr<donut::engine::MeshInfo>, nvrhi::rt::AccelStructHandle> meshAccelStructs;

        for (const auto &mesh : scene.GetSceneGraph()->GetMeshes())
        {
            nvrhi::rt::AccelStructDesc blasDesc;
            blasDesc.isTopLevel = false;

            for (const auto &geometry : mesh->geometries)
            {
                nvrhi::rt::GeometryDesc geometryDesc;
                auto &triangles = geometryDesc.geometryData.triangles;
                triangles.indexBuffer = mesh->buffers->indexBuffer;
                triangles.indexOffset = (mesh->indexOffset + geometry->indexOffsetInMesh) * sizeof(uint32_t);
                triangles.indexFormat = nvrhi::Format::R32_UINT;
                triangles.indexCount = geometry->numIndices;
                triangles.vertexBuffer = mesh->buffers->vertexBuffer;
                triangles.vertexOffset = (mesh->vertexOffset + geometry->vertexOffsetInMesh) * sizeof(donut::math::float3)
                    + mesh->buffers->getVertexBufferRange(donut::engine::VertexAttribute::Position).byteOffset;
                triangles.vertexFormat = nvrhi::Format::RGB32_FLOAT;
                triangles.vertexStride = sizeof(donut::math::float3);
                triangles.vertexCount = geometry->numVertices;
                geometryDesc.geometryType = nvrhi::rt::GeometryType::Triangles;
                geometryDesc.flags = nvrhi::rt::GeometryFlags::Opaque;
                blasDesc.bottomLevelGeometries.push_back(geometryDesc);
            }

            nvrhi::rt::AccelStructHandle as = device->createAccelStruct(blasDesc);
            nvrhi::utils::BuildBottomLevelAccelStruct(commandList, as, blasDesc);

            meshAccelStructs[mesh] = as;
        }

        nvrhi::rt::AccelStructDesc tlasDesc;
        tlasDesc.isTopLevel = true;

        std::vector<nvrhi::rt::InstanceDesc> instances;

        for (const auto &instance : scene.GetSceneGraph()->GetMeshInstances())
        {
            nvrhi::rt::InstanceDesc instanceDesc;
            instanceDesc.bottomLevelAS = meshAccelStructs[instance->GetMesh()];
            instanceDesc.instanceMask = 1;

            auto *node = instance->GetNode();
            donut::math::affineToColumnMajor(node->GetLocalToWorldTransformFloat(), instanceDesc.transform);

            instances.push_back(instanceDesc);
        }
        tlasDesc.topLevelMaxInstances = uint32_t(instances.size());

        nvrhi::rt::AccelStructHandle tlas = device->createAccelStruct(tlasDesc);
        commandList->buildTopLevelAccelStruct(tlas, instances.data(), instances.size());

        return DetachToShared(std::move(tlas));
    }, py::arg("device"), py::arg("commandList"), py::arg("scene"));

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
        py::arg("includePaths") = std::vector<std::string>{},
        py::arg("requiresVulkan11") = false);
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
        .def("mount", [](donut::vfs::RootFileSystem &self, const std::filesystem::path& path, const std::filesystem::path& nativePath) {
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

    // Only the fields threaded_rendering.py needs are bound (target framebuffer/viewport,
    // source texture/array slice) -- targetBox/sourceBox/sourceMip/sourceFormat/sampler/
    // blendState/blendConstantColor are left at their defaults, matching the existing
    // convention of leaving unused struct fields unbound (see TemporalAntiAliasingCreateParameters.
    // historyClampRelax).
    py::class_<donut::engine::BlitParameters>(m, "BlitParameters")
        .def(py::init<>())
        .def_property("targetFramebuffer",
            [](const donut::engine::BlitParameters &self) -> nvrhi::IFramebuffer* { return self.targetFramebuffer; },
            [](donut::engine::BlitParameters &self, nvrhi::IFramebuffer* fb) { self.targetFramebuffer = fb; },
            py::return_value_policy::reference)
        .def_readwrite("targetViewport", &donut::engine::BlitParameters::targetViewport)
        .def_property("sourceTexture",
            [](const donut::engine::BlitParameters &self) -> nvrhi::ITexture* { return self.sourceTexture; },
            [](donut::engine::BlitParameters &self, nvrhi::ITexture* t) { self.sourceTexture = t; },
            py::return_value_policy::reference)
        .def_readwrite("sourceArraySlice", &donut::engine::BlitParameters::sourceArraySlice);

    py::class_<donut::engine::CommonRenderPasses, std::shared_ptr<donut::engine::CommonRenderPasses>>(m, "CommonRenderPasses")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::ShaderFactory>>(), py::arg("device"), py::arg("shaderFactory"))
        .def("BlitTexture", [](donut::engine::CommonRenderPasses &self, nvrhi::ICommandList* commandList, nvrhi::IFramebuffer* targetFramebuffer,
                nvrhi::ITexture* sourceTexture, donut::engine::BindingCache* bindingCache) {
            self.BlitTexture(commandList, targetFramebuffer, sourceTexture, bindingCache);
        }, py::arg("commandList"), py::arg("targetFramebuffer"), py::arg("sourceTexture"), py::arg("bindingCache") = nullptr)
        // BlitParameters overload: composites one source array slice into one specific
        // viewport region of the target framebuffer, rather than the whole thing.
        .def("BlitTexture", [](donut::engine::CommonRenderPasses &self, nvrhi::ICommandList* commandList,
                const donut::engine::BlitParameters &params, donut::engine::BindingCache* bindingCache) {
            self.BlitTexture(commandList, params, bindingCache);
        }, py::arg("commandList"), py::arg("params"), py::arg("bindingCache") = nullptr)
        .def_property_readonly("m_AnisotropicWrapSampler", [](donut::engine::CommonRenderPasses &self) -> nvrhi::ISampler* {
            return self.m_AnisotropicWrapSampler;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("m_LinearWrapSampler", [](donut::engine::CommonRenderPasses &self) -> nvrhi::ISampler* {
            return self.m_LinearWrapSampler;
        }, py::return_value_policy::reference_internal)
        // Fallback textures for materials missing a given texture slot (see rt_reflections.py).
        .def_property_readonly("m_WhiteTexture", [](donut::engine::CommonRenderPasses &self) -> nvrhi::ITexture* {
            return self.m_WhiteTexture;
        }, py::return_value_policy::reference_internal)
        .def_property_readonly("m_BlackTexture", [](donut::engine::CommonRenderPasses &self) -> nvrhi::ITexture* {
            return self.m_BlackTexture;
        }, py::return_value_policy::reference_internal);

    // Movable-but-not-copyable in C++, so Python only ever holds it via a shared_ptr (produced
    // by DescriptorTableManager.CreateDescriptorHandle below), never constructs one directly.
    py::class_<donut::engine::DescriptorHandle, std::shared_ptr<donut::engine::DescriptorHandle>>(m, "DescriptorHandle")
        .def("Get", &donut::engine::DescriptorHandle::Get);

    py::class_<donut::engine::DescriptorTableManager, std::shared_ptr<donut::engine::DescriptorTableManager>> descriptorTableManager(m, "DescriptorTableManager");
    descriptorTableManager.def(py::init<nvrhi::IDevice*, nvrhi::IBindingLayout*>(), py::arg("device"), py::arg("layout"));
    descriptorTableManager.def("GetDescriptorTable", [](donut::engine::DescriptorTableManager &self) -> nvrhi::IBindingSet* {
        return self.GetDescriptorTable();
    }, py::return_value_policy::reference_internal);
    // Registers a resource (e.g. a raw buffer SRV) in the bindless descriptor table, returning
    // a handle whose Get() is the bindless index to embed in shader-visible per-instance data
    // (see rt_particles.py, which registers its dynamic particle index/vertex buffers this way).
    descriptorTableManager.def("CreateDescriptorHandle", [](std::shared_ptr<donut::engine::DescriptorTableManager> self, const nvrhi::BindingSetItem &item) {
        return std::make_shared<donut::engine::DescriptorHandle>(self->CreateDescriptorHandle(item));
    }, py::arg("item"));

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
    scene.def("Load", [](donut::engine::Scene &self, const std::filesystem::path& sceneFileName) {
        return self.Load(sceneFileName);
    }, py::arg("sceneFileName"));
    scene.def("FinishedLoading", &donut::engine::Scene::FinishedLoading, py::arg("frameIndex"));
    // Distinct from SceneGraph.Refresh(frameIndex) (bound below): this also captures the scene
    // graph's pending structure/transform-change flags onto the Scene itself, which
    // Scene.Refresh()'s buffer rebuild (below) depends on to notice a newly-attached mesh
    // instance and rebuild GPU buffers for it -- calling SceneGraph.Refresh() directly would
    // skip that and silently leave the new instance's data out of the GPU buffers. Needed right
    // after attaching a hand-built mesh instance to the graph, before the first Scene.Refresh()
    // (see rt_particles.py's procedural particle mesh).
    scene.def("RefreshSceneGraph", &donut::engine::Scene::RefreshSceneGraph, py::arg("frameIndex"));
    // Uploads any per-frame-dynamic scene GPU buffer changes (e.g. a mesh whose vertex/index
    // data or material was updated this frame) -- distinct from RefreshSceneGraph/Refresh(0),
    // which is only for static scene-graph-transform bookkeeping. Needed by scenes with
    // procedurally-updated geometry (see rt_particles.py).
    scene.def("Refresh", [](donut::engine::Scene &self, nvrhi::ICommandList* commandList, uint32_t frameIndex) {
        self.Refresh(commandList, frameIndex);
    }, py::arg("commandList"), py::arg("frameIndex"));
    scene.def("GetInstanceBuffer", [](donut::engine::Scene &self) -> nvrhi::IBuffer* { return self.GetInstanceBuffer(); }, py::return_value_policy::reference_internal);
    scene.def("GetGeometryBuffer", [](donut::engine::Scene &self) -> nvrhi::IBuffer* { return self.GetGeometryBuffer(); }, py::return_value_policy::reference_internal);
    scene.def("GetMaterialBuffer", [](donut::engine::Scene &self) -> nvrhi::IBuffer* { return self.GetMaterialBuffer(); }, py::return_value_policy::reference_internal);
    // For samples that need to walk the graph directly (attach their own lights, use
    // RenderCompositeView with the real root node) rather than just driving simple draw calls
    // via GetDrawItems().
    scene.def("GetSceneGraph", &donut::engine::Scene::GetSceneGraph);
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

    // Mirrors ApplicationBase::SceneLoaded()'s texture-finalization step (the part that runs
    // after LoadScene() returns on the synchronous path, i.e. SetAsynchronousLoadingEnabled(false)
    // followed by BeginLoadingScene()), for samples that subclass IRenderPass directly instead
    // of ApplicationBase. Must run after Scene.Load() and before Scene.FinishedLoading(): it
    // finalizes each texture's bindless descriptor index, which FinishedLoading() then bakes
    // into the material buffer.
    m.def("SceneLoaded", [](donut::engine::TextureCache& textureCache, donut::engine::CommonRenderPasses& commonPasses) {
        textureCache.ProcessRenderingThreadCommands(commonPasses, 0.f);
        textureCache.LoadingFinished();
    }, py::arg("textureCache"), py::arg("commonPasses"));

    textureCache.def("LoadTextureFromFile", [](donut::engine::TextureCache &self, const std::filesystem::path& path, bool sRGB,
            donut::engine::CommonRenderPasses* passes, nvrhi::ICommandList* commandList) {
        return self.LoadTextureFromFile(path, sRGB, passes, commandList);
    }, py::arg("path"), py::arg("sRGB"), py::arg("passes") = nullptr, py::arg("commandList"));
    // Synchronous read+decode, but the GPU upload/mip generation is deferred to the
    // TextureCache's own queue (drained by ProcessRenderingThreadCommands/SceneLoaded) --
    // for loading extra standalone textures outside the scene's own material set (see
    // rt_particles.py's particle/environment-map textures).
    textureCache.def("LoadTextureFromFileDeferred", [](donut::engine::TextureCache &self, const std::filesystem::path& path, bool sRGB) {
        return self.LoadTextureFromFileDeferred(path, sRGB);
    }, py::arg("path"), py::arg("sRGB"));

    py::class_<donut::engine::LoadedTexture, std::shared_ptr<donut::engine::LoadedTexture>>(m, "LoadedTexture")
        .def_property_readonly("texture", [](const donut::engine::LoadedTexture &self) -> nvrhi::ITexture* {
            return self.texture.Get();
        }, py::return_value_policy::reference_internal)
        // The bindless table index for this texture's SRV, to embed in shader-visible
        // per-instance/per-particle data (see rt_particles.py).
        .def_property_readonly("bindlessDescriptorIndex", [](const donut::engine::LoadedTexture &self) {
            return self.bindlessDescriptor.Get();
        });

    // VertexAttribute/BufferGroup/Material/MeshGeometry/MeshInfo/MeshInstance/SceneGraphNode/
    // SceneGraph/Light/DirectionalLight below are bound just deep enough to build a manual
    // scene graph by hand (see deferred_shading.py) -- matching what Scene already builds
    // internally for glTF-loaded scenes, but assembled a few pieces at a time from Python.
    pybind11::native_enum<donut::engine::VertexAttribute>(m, "VertexAttribute", "enum.Enum")
        .value("Position", donut::engine::VertexAttribute::Position)
        .value("TexCoord1", donut::engine::VertexAttribute::TexCoord1)
        .value("Normal", donut::engine::VertexAttribute::Normal)
        .value("Tangent", donut::engine::VertexAttribute::Tangent)
        .finalize();

    py::class_<donut::engine::BufferGroup, std::shared_ptr<donut::engine::BufferGroup>>(m, "BufferGroup")
        .def(py::init<>())
        .def_property("indexBuffer",
            [](const donut::engine::BufferGroup &self) -> nvrhi::IBuffer* { return self.indexBuffer.Get(); },
            [](donut::engine::BufferGroup &self, nvrhi::IBuffer* b) { self.indexBuffer = b; },
            py::return_value_policy::reference)
        .def_property("vertexBuffer",
            [](const donut::engine::BufferGroup &self) -> nvrhi::IBuffer* { return self.vertexBuffer.Get(); },
            [](donut::engine::BufferGroup &self, nvrhi::IBuffer* b) { self.vertexBuffer = b; },
            py::return_value_policy::reference)
        .def_property("instanceBuffer",
            [](const donut::engine::BufferGroup &self) -> nvrhi::IBuffer* { return self.instanceBuffer.Get(); },
            [](donut::engine::BufferGroup &self, nvrhi::IBuffer* b) { self.instanceBuffer = b; },
            py::return_value_policy::reference)
        .def("setVertexBufferRange", [](donut::engine::BufferGroup &self, donut::engine::VertexAttribute attr,
                uint64_t byteOffset, uint64_t byteSize) {
            nvrhi::BufferRange &range = self.getVertexBufferRange(attr);
            range.byteOffset = byteOffset;
            range.byteSize = byteSize;
        }, py::arg("attr"), py::arg("byteOffset"), py::arg("byteSize"))
        .def("getVertexBufferRange", [](donut::engine::BufferGroup &self, donut::engine::VertexAttribute attr) {
            return self.getVertexBufferRange(attr);
        }, py::arg("attr"))
        // Bindless table entries for this buffer group's raw index/vertex buffers (see
        // DescriptorTableManager.CreateDescriptorHandle) -- needed for procedural geometry
        // whose shaders look up vertex data via a bindless buffer index rather than a
        // directly-bound SRV (see rt_particles.py).
        .def_readwrite("indexBufferDescriptor", &donut::engine::BufferGroup::indexBufferDescriptor)
        .def_readwrite("vertexBufferDescriptor", &donut::engine::BufferGroup::vertexBufferDescriptor);

    // Only the domains this module's samples actually set (rt_particles.py's procedural
    // particle material) plus Opaque (the default) -- matching the "only bind what's needed"
    // convention used throughout.
    pybind11::native_enum<donut::engine::MaterialDomain>(m, "MaterialDomain", "enum.Enum")
        .value("Opaque", donut::engine::MaterialDomain::Opaque)
        .value("AlphaBlended", donut::engine::MaterialDomain::AlphaBlended)
        .finalize();

    py::class_<donut::engine::Material, std::shared_ptr<donut::engine::Material>>(m, "Material")
        .def(py::init<>())
        .def_readwrite("name", &donut::engine::Material::name)
        .def_readwrite("domain", &donut::engine::Material::domain)
        // Set by the app to make Scene.Refresh()/FinishedLoading() re-upload the material's
        // constant buffer -- e.g. after swapping baseOrDiffuseTexture (see rt_particles.py).
        .def_readwrite("dirty", &donut::engine::Material::dirty)
        .def_readwrite("useSpecularGlossModel", &donut::engine::Material::useSpecularGlossModel)
        .def_readwrite("enableBaseOrDiffuseTexture", &donut::engine::Material::enableBaseOrDiffuseTexture)
        .def_readwrite("baseOrDiffuseTexture", &donut::engine::Material::baseOrDiffuseTexture)
        .def_readwrite("metalRoughOrSpecularTexture", &donut::engine::Material::metalRoughOrSpecularTexture)
        .def_readwrite("normalTexture", &donut::engine::Material::normalTexture)
        .def_readwrite("emissiveTexture", &donut::engine::Material::emissiveTexture)
        .def_readwrite("occlusionTexture", &donut::engine::Material::occlusionTexture)
        .def_readwrite("transmissionTexture", &donut::engine::Material::transmissionTexture)
        .def_readwrite("opacityTexture", &donut::engine::Material::opacityTexture)
        .def_property("materialConstants",
            [](const donut::engine::Material &self) -> nvrhi::IBuffer* { return self.materialConstants.Get(); },
            [](donut::engine::Material &self, nvrhi::IBuffer* b) { self.materialConstants = b; },
            py::return_value_policy::reference);

    // Wraps Material::FillConstantBuffer(), which fills the generated MaterialConstants
    // shader-cbuffer struct -- not otherwise exposed to Python, same rationale as
    // PlanarView.FillPlanarViewConstants() returning raw bytes instead of a bound struct.
    m.def("CreateMaterialConstantBuffer", [](nvrhi::IDevice* device, nvrhi::ICommandList* commandList, const donut::engine::Material &material) {
        nvrhi::BufferDesc bufferDesc;
        bufferDesc.byteSize = sizeof(MaterialConstants);
        bufferDesc.debugName = material.name;
        bufferDesc.isConstantBuffer = true;
        bufferDesc.initialState = nvrhi::ResourceStates::ConstantBuffer;
        bufferDesc.keepInitialState = true;
        nvrhi::BufferHandle buffer = device->createBuffer(bufferDesc);

        MaterialConstants constants{};
        material.FillConstantBuffer(constants);
        commandList->writeBuffer(buffer, &constants, sizeof(constants));

        return DetachToShared(std::move(buffer));
    }, py::arg("device"), py::arg("commandList"), py::arg("material"));

    py::class_<donut::engine::MeshGeometry, std::shared_ptr<donut::engine::MeshGeometry>>(m, "MeshGeometry")
        .def(py::init<>())
        .def_readwrite("material", &donut::engine::MeshGeometry::material)
        .def_readwrite("numIndices", &donut::engine::MeshGeometry::numIndices)
        .def_readwrite("numVertices", &donut::engine::MeshGeometry::numVertices)
        // Assigned by the scene graph when the mesh is added to the scene; used to compute a
        // stable per-geometry shader-table hit-group index (see rt_reflections.py).
        .def_readonly("globalGeometryIndex", &donut::engine::MeshGeometry::globalGeometryIndex)
        // This geometry's index/vertex range within its owning mesh's shared index/vertex
        // buffers -- combine with MeshInfo.indexOffset/vertexOffset to get the absolute range
        // (see rt_shadows.py's BLAS building and rt_reflections.py's per-geometry bindings).
        .def_readonly("indexOffsetInMesh", &donut::engine::MeshGeometry::indexOffsetInMesh)
        .def_readonly("vertexOffsetInMesh", &donut::engine::MeshGeometry::vertexOffsetInMesh);

    py::class_<donut::engine::MeshInfo, std::shared_ptr<donut::engine::MeshInfo>>(m, "MeshInfo")
        .def(py::init<>())
        .def_readwrite("name", &donut::engine::MeshInfo::name)
        .def_readwrite("buffers", &donut::engine::MeshInfo::buffers)
        .def_readwrite("totalIndices", &donut::engine::MeshInfo::totalIndices)
        .def_readwrite("totalVertices", &donut::engine::MeshInfo::totalVertices)
        .def_readonly("indexOffset", &donut::engine::MeshInfo::indexOffset)
        .def_readonly("vertexOffset", &donut::engine::MeshInfo::vertexOffset)
        .def_readwrite("geometries", &donut::engine::MeshInfo::geometries)
        // Set on the template mesh a skinned instance was cloned from -- see
        // SceneGraph.GetSkinnedMeshInstances()/SkinnedMeshInstance.GetPrototypeMesh(). isSkinPrototype
        // marks that template itself (never instantiated/ray-traced directly; skip it when building
        // BLASes -- see rt_bindless.py's CreateAccelStructs).
        .def_readonly("isSkinPrototype", &donut::engine::MeshInfo::isSkinPrototype)
        .def_readonly("skinPrototype", &donut::engine::MeshInfo::skinPrototype)
        .def("SetObjectSpaceBounds", [](donut::engine::MeshInfo &self,
                float minX, float minY, float minZ, float maxX, float maxY, float maxZ) {
            self.objectSpaceBounds = donut::math::box3(
                donut::math::float3(minX, minY, minZ), donut::math::float3(maxX, maxY, maxZ));
        }, py::arg("minX"), py::arg("minY"), py::arg("minZ"), py::arg("maxX"), py::arg("maxY"), py::arg("maxZ"))
        // "for use by applications" per the engine's own comment -- lets an app cache each
        // mesh's bottom-level acceleration structure directly on the mesh, e.g. while building
        // BLASes once and looking them up per-instance when building the TLAS.
        .def_property("accelStruct",
            [](const donut::engine::MeshInfo &self) -> nvrhi::rt::IAccelStruct* { return self.accelStruct.Get(); },
            [](donut::engine::MeshInfo &self, nvrhi::rt::IAccelStruct* as) { self.accelStruct = as; },
            py::return_value_policy::reference);

    // SceneGraphLeaf is abstract (pure virtual Clone()) -- bound base-only, for MeshInstance/
    // Light/DirectionalLight below to derive from and for SetLeaf()/AttachLeafNode() to accept.
    py::class_<donut::engine::SceneGraphLeaf, std::shared_ptr<donut::engine::SceneGraphLeaf>>(m, "SceneGraphLeaf")
        .def("SetName", [](const donut::engine::SceneGraphLeaf &self, const std::string &name) { self.SetName(name); }, py::arg("name"));

    py::class_<donut::engine::MeshInstance, donut::engine::SceneGraphLeaf, std::shared_ptr<donut::engine::MeshInstance>>(m, "MeshInstance")
        .def(py::init<std::shared_ptr<donut::engine::MeshInfo>>(), py::arg("mesh"))
        .def("GetMesh", &donut::engine::MeshInstance::GetMesh)
        .def("GetNode", &donut::engine::MeshInstance::GetNode, py::return_value_policy::reference)
        // Stable per-instance index assigned by the scene graph -- used as the RT instance ID
        // so shaders can look up per-instance data (see rt_particles.py).
        .def("GetInstanceIndex", &donut::engine::MeshInstance::GetInstanceIndex);

    // One instance of a skinned (animated) mesh -- see SceneGraph.GetSkinnedMeshInstances().
    // GetMesh() (inherited from MeshInstance) returns this instance's own per-instance mesh
    // (deformed vertex buffers), distinct from GetPrototypeMesh()'s shared bind-pose template.
    // GetLastUpdateFrameIndex() tells the app which frame the skinning compute pass last wrote
    // new vertex positions for this instance, so it knows when to rebuild the instance's BLAS
    // (see rt_bindless.py's BuildTLAS, matching the C++ original).
    py::class_<donut::engine::SkinnedMeshInstance, donut::engine::MeshInstance, std::shared_ptr<donut::engine::SkinnedMeshInstance>>(m, "SkinnedMeshInstance")
        .def("GetPrototypeMesh", &donut::engine::SkinnedMeshInstance::GetPrototypeMesh)
        .def("GetLastUpdateFrameIndex", &donut::engine::SkinnedMeshInstance::GetLastUpdateFrameIndex);

    // Light is abstract (pure virtual GetLightType()) -- bound base-only, so
    // SceneGraph.GetLights() can return a homogeneous list regardless of light subtype.
    py::class_<donut::engine::Light, donut::engine::SceneGraphLeaf, std::shared_ptr<donut::engine::Light>>(m, "Light")
        .def("SetDirection", [](const donut::engine::Light &self, double x, double y, double z) {
            self.SetDirection(donut::math::double3(x, y, z));
        }, py::arg("x"), py::arg("y"), py::arg("z"))
        // Raw bytes of the engine's LightConstants struct, ready for CommandList.writeBuffer --
        // same pattern as PlanarView.FillPlanarViewConstants. Virtual, so this dispatches to
        // whichever concrete light type (DirectionalLight, etc.) the Python object actually is.
        .def("FillLightConstants", [](const donut::engine::Light &self) {
            LightConstants constants{};
            self.FillLightConstants(constants);
            return py::bytes(reinterpret_cast<const char*>(&constants), sizeof(constants));
        });

    py::class_<donut::engine::DirectionalLight, donut::engine::Light, std::shared_ptr<donut::engine::DirectionalLight>>(m, "DirectionalLight")
        .def(py::init<>())
        .def_readwrite("irradiance", &donut::engine::DirectionalLight::irradiance)
        .def_readwrite("angularSize", &donut::engine::DirectionalLight::angularSize);

    // One baked animation clip attached to the scene graph (e.g. a glTF skinned character
    // animation) -- see SceneGraph.GetAnimations() below. Apply() drives every channel
    // (node transforms, morph/material properties) to their sampled values at `time`; the
    // caller is responsible for looping/wrapping time against GetDuration() itself (see
    // rt_bindless.py's Animate()).
    py::class_<donut::engine::SceneGraphAnimation, donut::engine::SceneGraphLeaf, std::shared_ptr<donut::engine::SceneGraphAnimation>>(m, "SceneGraphAnimation")
        .def("GetDuration", &donut::engine::SceneGraphAnimation::GetDuration)
        .def("Apply", &donut::engine::SceneGraphAnimation::Apply, py::arg("time"));

    py::class_<donut::engine::SceneGraphNode, std::shared_ptr<donut::engine::SceneGraphNode>>(m, "SceneGraphNode")
        .def(py::init<>())
        .def("SetLeaf", &donut::engine::SceneGraphNode::SetLeaf, py::arg("leaf"))
        .def("SetName", &donut::engine::SceneGraphNode::SetName, py::arg("name"))
        // The world-space translation component of this node's world transform, as (x, y, z)
        // -- math types aren't exposed to Python (see rt_particles.py's emitter-position lookup).
        .def("GetWorldPosition", [](const donut::engine::SceneGraphNode &self) {
            const donut::math::float3 &t = self.GetLocalToWorldTransformFloat().m_translation;
            return py::make_tuple(t.x, t.y, t.z);
        });

    py::class_<donut::engine::SceneGraph, std::shared_ptr<donut::engine::SceneGraph>>(m, "SceneGraph")
        .def(py::init<>())
        .def("SetRootNode", &donut::engine::SceneGraph::SetRootNode, py::arg("root"))
        .def("GetRootNode", &donut::engine::SceneGraph::GetRootNode)
        .def("AttachLeafNode", &donut::engine::SceneGraph::AttachLeafNode, py::arg("parent"), py::arg("leaf"))
        .def("Refresh", &donut::engine::SceneGraph::Refresh, py::arg("frameIndex"))
        .def("GetLights", &donut::engine::SceneGraph::GetLights)
        // ResourceTracker<MeshInfo> isn't a plain container pybind11/stl.h can convert
        // automatically, so it's copied into a plain vector here.
        .def("GetMeshes", [](const donut::engine::SceneGraph &self) {
            std::vector<std::shared_ptr<donut::engine::MeshInfo>> meshes;
            for (const auto &mesh : self.GetMeshes())
                meshes.push_back(mesh);
            return meshes;
        })
        .def("GetMeshInstances", &donut::engine::SceneGraph::GetMeshInstances)
        // Baked animation clips attached anywhere in the graph (see SceneGraphAnimation above).
        .def("GetAnimations", &donut::engine::SceneGraph::GetAnimations)
        // Skinned (animated) mesh instances -- see SkinnedMeshInstance above.
        .def("GetSkinnedMeshInstances", &donut::engine::SceneGraph::GetSkinnedMeshInstances)
        // context is always null here (searches from the graph root) -- nothing in this
        // codebase needs to search from an arbitrary starting node.
        .def("FindNode", [](const donut::engine::SceneGraph &self, const std::filesystem::path &path) {
            return self.FindNode(path, nullptr);
        }, py::arg("path"));

    // GBufferRenderTargets/GBufferFillPass/DeferredLightingPass/ForwardShadingPass/
    // TemporalAntiAliasingPass/draw strategies/RenderView/RenderCompositeView below implement
    // Donut's two rendering pipelines (deferred and forward+TAA) and the scene-traversal
    // machinery they share. IDrawStrategy/IGeometryPass/GeometryPassContext are registered as
    // real polymorphic bases -- rather than binding RenderView/RenderCompositeView against one
    // fixed concrete strategy/pass/context each -- since both pipelines now contribute a second
    // concrete implementation of each (PassthroughDrawStrategy + InstancedOpaqueDrawStrategy +
    // TransparentDrawStrategy; GBufferFillPass + ForwardShadingPass), and a fixed-overload
    // approach would multiply combinatorially.
    py::class_<donut::render::IDrawStrategy, std::shared_ptr<donut::render::IDrawStrategy>>(m, "IDrawStrategy");
    py::class_<donut::render::IGeometryPass, std::shared_ptr<donut::render::IGeometryPass>>(m, "IGeometryPass");
    // GeometryPassContext subclasses are always freshly constructed and passed by reference
    // for the duration of one RenderView/RenderCompositeView call, never independently shared,
    // so (unlike the two hierarchies above) this one doesn't need a shared_ptr holder.
    py::class_<donut::render::GeometryPassContext>(m, "GeometryPassContext");

    py::class_<donut::render::GBufferRenderTargets, std::shared_ptr<donut::render::GBufferRenderTargets>>(m, "GBufferRenderTargets")
        .def(py::init<>())
        .def("Init", [](donut::render::GBufferRenderTargets &self, nvrhi::IDevice* device, uint32_t width, uint32_t height,
                uint32_t sampleCount, bool enableMotionVectors, bool useReverseProjection) {
            self.Init(device, donut::math::uint2(width, height), sampleCount, enableMotionVectors, useReverseProjection);
        }, py::arg("device"), py::arg("width"), py::arg("height"), py::arg("sampleCount"),
           py::arg("enableMotionVectors"), py::arg("useReverseProjection"))
        .def("Clear", &donut::render::GBufferRenderTargets::Clear, py::arg("commandList"))
        .def_property_readonly("width", [](const donut::render::GBufferRenderTargets &self) { return self.GetSize().x; })
        .def_property_readonly("height", [](const donut::render::GBufferRenderTargets &self) { return self.GetSize().y; })
        // Wraps GBufferFramebuffer->GetFramebuffer(view) -- FramebufferFactory itself isn't
        // needed here since this is its only use from Python for this specific render target
        // bundle (contrast RenderTargets in variable_shading.py, which builds its own
        // FramebufferFactory instances directly, since it needs more control over them).
        .def("GetFramebuffer", [](donut::render::GBufferRenderTargets &self, donut::engine::PlanarView &view) -> nvrhi::IFramebuffer* {
            return self.GBufferFramebuffer->GetFramebuffer(view);
        }, py::arg("view"), py::return_value_policy::reference_internal);

    py::class_<donut::render::GBufferFillPass::CreateParameters>(m, "GBufferFillPassCreateParameters")
        .def(py::init<>());

    py::class_<donut::render::GBufferFillPass::Context, donut::render::GeometryPassContext>(m, "GBufferFillPassContext")
        .def(py::init<>());

    py::class_<donut::render::GBufferFillPass, donut::render::IGeometryPass, std::shared_ptr<donut::render::GBufferFillPass>>(m, "GBufferFillPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::CommonRenderPasses>>(), py::arg("device"), py::arg("commonPasses"))
        .def("Init", &donut::render::GBufferFillPass::Init, py::arg("shaderFactory"), py::arg("params"))
        .def("ResetBindingCache", &donut::render::GBufferFillPass::ResetBindingCache);

    py::class_<PyPassthroughDrawStrategy, donut::render::IDrawStrategy, std::shared_ptr<PyPassthroughDrawStrategy>>(m, "PassthroughDrawStrategy")
        .def(py::init<>())
        .def("SetSingleItem", &PyPassthroughDrawStrategy::SetSingleItem,
            py::arg("instance"), py::arg("mesh"), py::arg("geometry"), py::arg("material"), py::arg("buffers"),
            py::arg("distanceToCamera"), py::arg("cullMode"));

    py::class_<donut::render::InstancedOpaqueDrawStrategy, donut::render::IDrawStrategy, std::shared_ptr<donut::render::InstancedOpaqueDrawStrategy>>(
        m, "InstancedOpaqueDrawStrategy")
        .def(py::init<>());

    py::class_<donut::render::TransparentDrawStrategy, donut::render::IDrawStrategy, std::shared_ptr<donut::render::TransparentDrawStrategy>>(
        m, "TransparentDrawStrategy")
        .def(py::init<>());

    py::class_<PyDeferredLightingInputs>(m, "DeferredLightingPassInputs")
        .def(py::init<>())
        .def("SetGBuffer", &PyDeferredLightingInputs::SetGBuffer, py::arg("targets"))
        .def("SetAmbientColors", &PyDeferredLightingInputs::SetAmbientColors,
            py::arg("topR"), py::arg("topG"), py::arg("topB"), py::arg("bottomR"), py::arg("bottomG"), py::arg("bottomB"))
        .def("SetLights", &PyDeferredLightingInputs::SetLights, py::arg("lights"))
        .def_property("output",
            [](const PyDeferredLightingInputs &self) -> nvrhi::ITexture* { return self.output; },
            [](PyDeferredLightingInputs &self, nvrhi::ITexture* tex) { self.output = tex; },
            py::return_value_policy::reference);

    py::class_<donut::render::DeferredLightingPass, std::shared_ptr<donut::render::DeferredLightingPass>>(m, "DeferredLightingPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::CommonRenderPasses>>(), py::arg("device"), py::arg("commonPasses"))
        .def("Init", &donut::render::DeferredLightingPass::Init, py::arg("shaderFactory"))
        .def("Render", [](donut::render::DeferredLightingPass &self, nvrhi::ICommandList* commandList,
                donut::engine::PlanarView &view, const PyDeferredLightingInputs &inputs) {
            self.Render(commandList, view, inputs);
        }, py::arg("commandList"), py::arg("view"), py::arg("inputs"))
        .def("ResetBindingCache", &donut::render::DeferredLightingPass::ResetBindingCache);

    // materialBindings/singlePassCubemap/trackLiveness/useInputAssembler stay at their defaults,
    // matching every current sample's usage; numConstantBufferVersions is bound because
    // threaded_rendering.py needs to raise it above the default 16 (each of the 6 concurrently-
    // recorded per-face command lists consumes its own volatile constant buffer version).
    py::class_<donut::render::ForwardShadingPass::CreateParameters>(m, "ForwardShadingPassCreateParameters")
        .def(py::init<>())
        .def_readwrite("numConstantBufferVersions", &donut::render::ForwardShadingPass::CreateParameters::numConstantBufferVersions);

    py::class_<donut::render::ForwardShadingPass::Context, donut::render::GeometryPassContext>(m, "ForwardShadingPassContext")
        .def(py::init<>());

    py::class_<donut::render::ForwardShadingPass, donut::render::IGeometryPass, std::shared_ptr<donut::render::ForwardShadingPass>>(m, "ForwardShadingPass")
        .def(py::init<nvrhi::IDevice*, std::shared_ptr<donut::engine::CommonRenderPasses>>(), py::arg("device"), py::arg("commonPasses"))
        .def("Init", &donut::render::ForwardShadingPass::Init, py::arg("shaderFactory"), py::arg("params"))
        .def("ResetBindingCache", &donut::render::ForwardShadingPass::ResetBindingCache)
        // lightProbes is always empty here -- not otherwise exposed to Python (nothing in
        // this codebase builds one), matching every current sample's usage of this call.
        .def("PrepareLights", [](donut::render::ForwardShadingPass &self, donut::render::ForwardShadingPass::Context &context,
                nvrhi::ICommandList* commandList, const std::vector<std::shared_ptr<donut::engine::Light>> &lights,
                float topR, float topG, float topB, float bottomR, float bottomG, float bottomB) {
            self.PrepareLights(context, commandList, lights,
                donut::math::float3(topR, topG, topB), donut::math::float3(bottomR, bottomG, bottomB), {});
        }, py::arg("context"), py::arg("commandList"), py::arg("lights"),
           py::arg("topR"), py::arg("topG"), py::arg("topB"), py::arg("bottomR"), py::arg("bottomG"), py::arg("bottomB"),
           // See the comment on CommandList.open above -- released for threaded_rendering.py's
           // concurrent per-face recording.
           py::call_guard<py::gil_scoped_release>());

    py::class_<donut::render::TemporalAntiAliasingParameters>(m, "TemporalAntiAliasingParameters")
        .def(py::init<>())
        .def_readwrite("newFrameWeight", &donut::render::TemporalAntiAliasingParameters::newFrameWeight)
        .def_readwrite("clampingFactor", &donut::render::TemporalAntiAliasingParameters::clampingFactor)
        .def_readwrite("maxRadiance", &donut::render::TemporalAntiAliasingParameters::maxRadiance)
        .def_readwrite("enableHistoryClamping", &donut::render::TemporalAntiAliasingParameters::enableHistoryClamping)
        .def_readwrite("useHistoryClampRelax", &donut::render::TemporalAntiAliasingParameters::useHistoryClampRelax);

    // CreateParameters' texture fields are raw nvrhi::ITexture* (not RefCountPtr), so they're
    // plain pointer properties rather than the .Get()/assign pattern used for TextureHandle
    // fields elsewhere. historyClampRelax is intentionally left unbound: nothing in this
    // codebase builds the mask texture it expects, matching useHistoryClampRelax always false.
    py::class_<donut::render::TemporalAntiAliasingPass::CreateParameters>(m, "TemporalAntiAliasingCreateParameters")
        .def(py::init<>())
        .def_property("sourceDepth",
            [](const donut::render::TemporalAntiAliasingPass::CreateParameters &p) -> nvrhi::ITexture* { return p.sourceDepth; },
            [](donut::render::TemporalAntiAliasingPass::CreateParameters &p, nvrhi::ITexture* t) { p.sourceDepth = t; },
            py::return_value_policy::reference)
        .def_property("motionVectors",
            [](const donut::render::TemporalAntiAliasingPass::CreateParameters &p) -> nvrhi::ITexture* { return p.motionVectors; },
            [](donut::render::TemporalAntiAliasingPass::CreateParameters &p, nvrhi::ITexture* t) { p.motionVectors = t; },
            py::return_value_policy::reference)
        .def_property("unresolvedColor",
            [](const donut::render::TemporalAntiAliasingPass::CreateParameters &p) -> nvrhi::ITexture* { return p.unresolvedColor; },
            [](donut::render::TemporalAntiAliasingPass::CreateParameters &p, nvrhi::ITexture* t) { p.unresolvedColor = t; },
            py::return_value_policy::reference)
        .def_property("resolvedColor",
            [](const donut::render::TemporalAntiAliasingPass::CreateParameters &p) -> nvrhi::ITexture* { return p.resolvedColor; },
            [](donut::render::TemporalAntiAliasingPass::CreateParameters &p, nvrhi::ITexture* t) { p.resolvedColor = t; },
            py::return_value_policy::reference)
        .def_property("feedback1",
            [](const donut::render::TemporalAntiAliasingPass::CreateParameters &p) -> nvrhi::ITexture* { return p.feedback1; },
            [](donut::render::TemporalAntiAliasingPass::CreateParameters &p, nvrhi::ITexture* t) { p.feedback1 = t; },
            py::return_value_policy::reference)
        .def_property("feedback2",
            [](const donut::render::TemporalAntiAliasingPass::CreateParameters &p) -> nvrhi::ITexture* { return p.feedback2; },
            [](donut::render::TemporalAntiAliasingPass::CreateParameters &p, nvrhi::ITexture* t) { p.feedback2 = t; },
            py::return_value_policy::reference)
        .def_readwrite("useCatmullRomFilter", &donut::render::TemporalAntiAliasingPass::CreateParameters::useCatmullRomFilter)
        .def_readwrite("motionVectorStencilMask", &donut::render::TemporalAntiAliasingPass::CreateParameters::motionVectorStencilMask)
        .def_readwrite("numConstantBufferVersions", &donut::render::TemporalAntiAliasingPass::CreateParameters::numConstantBufferVersions);

    py::class_<donut::render::TemporalAntiAliasingPass, std::shared_ptr<donut::render::TemporalAntiAliasingPass>>(m, "TemporalAntiAliasingPass")
        .def(py::init([](nvrhi::IDevice* device, std::shared_ptr<donut::engine::ShaderFactory> shaderFactory,
                std::shared_ptr<donut::engine::CommonRenderPasses> commonPasses, donut::engine::PlanarView &compositeView,
                const donut::render::TemporalAntiAliasingPass::CreateParameters &params) {
            return new donut::render::TemporalAntiAliasingPass(device, shaderFactory, commonPasses, compositeView, params);
        }), py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"), py::arg("compositeView"), py::arg("params"))
        .def("RenderMotionVectors", [](donut::render::TemporalAntiAliasingPass &self, nvrhi::ICommandList* commandList,
                donut::engine::PlanarView &compositeView, donut::engine::PlanarView &compositeViewPrevious) {
            self.RenderMotionVectors(commandList, compositeView, compositeViewPrevious);
        }, py::arg("commandList"), py::arg("compositeView"), py::arg("compositeViewPrevious"))
        .def("TemporalResolve", [](donut::render::TemporalAntiAliasingPass &self, nvrhi::ICommandList* commandList,
                const donut::render::TemporalAntiAliasingParameters &params, bool feedbackIsValid,
                donut::engine::PlanarView &compositeViewInput, donut::engine::PlanarView &compositeViewOutput) {
            self.TemporalResolve(commandList, params, feedbackIsValid, compositeViewInput, compositeViewOutput);
        }, py::arg("commandList"), py::arg("params"), py::arg("feedbackIsValid"), py::arg("compositeViewInput"), py::arg("compositeViewOutput"));

    // SkyParameters' four dm::float3 fields (skyColor/horizonColor/groundColor/directionUp)
    // follow this codebase's flat-scalar convention rather than being exposed as math types --
    // same shape as DeferredLightingPassInputs.SetAmbientColors above.
    py::class_<donut::render::SkyParameters>(m, "SkyParameters")
        .def(py::init<>())
        .def("SetSkyColor", [](donut::render::SkyParameters &self, float r, float g, float b) {
            self.skyColor = donut::math::float3(r, g, b);
        }, py::arg("r"), py::arg("g"), py::arg("b"))
        .def("SetHorizonColor", [](donut::render::SkyParameters &self, float r, float g, float b) {
            self.horizonColor = donut::math::float3(r, g, b);
        }, py::arg("r"), py::arg("g"), py::arg("b"))
        .def("SetGroundColor", [](donut::render::SkyParameters &self, float r, float g, float b) {
            self.groundColor = donut::math::float3(r, g, b);
        }, py::arg("r"), py::arg("g"), py::arg("b"))
        .def("SetDirectionUp", [](donut::render::SkyParameters &self, float x, float y, float z) {
            self.directionUp = donut::math::float3(x, y, z);
        }, py::arg("x"), py::arg("y"), py::arg("z"))
        .def_readwrite("brightness", &donut::render::SkyParameters::brightness)
        .def_readwrite("horizonSize", &donut::render::SkyParameters::horizonSize)
        .def_readwrite("glowSize", &donut::render::SkyParameters::glowSize)
        .def_readwrite("glowIntensity", &donut::render::SkyParameters::glowIntensity)
        .def_readwrite("glowSharpness", &donut::render::SkyParameters::glowSharpness)
        .def_readwrite("maxLightRadiance", &donut::render::SkyParameters::maxLightRadiance);

    // FillShaderParameters is deliberately not bound: it is a static helper for callers that
    // drive the procedural sky constants themselves, which no sample in this repo does.
    py::class_<donut::render::SkyPass, std::shared_ptr<donut::render::SkyPass>>(m, "SkyPass")
        .def(py::init([](nvrhi::IDevice* device, const std::shared_ptr<donut::engine::ShaderFactory> &shaderFactory,
                const std::shared_ptr<donut::engine::CommonRenderPasses> &commonPasses,
                const std::shared_ptr<donut::engine::FramebufferFactory> &framebufferFactory,
                const donut::engine::IView &compositeView) {
            return new donut::render::SkyPass(device, shaderFactory, commonPasses, framebufferFactory, compositeView);
        }), py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"),
            py::arg("framebufferFactory"), py::arg("compositeView"))
        .def("Render", [](const donut::render::SkyPass &self, nvrhi::ICommandList* commandList,
                const donut::engine::IView &compositeView, const donut::engine::DirectionalLight &light,
                const donut::render::SkyParameters &params) {
            self.Render(commandList, compositeView, light, params);
        }, py::arg("commandList"), py::arg("compositeView"), py::arg("light"), py::arg("params"));

    py::class_<donut::render::SsaoParameters>(m, "SsaoParameters")
        .def(py::init<>())
        .def_readwrite("amount", &donut::render::SsaoParameters::amount)
        .def_readwrite("backgroundViewDepth", &donut::render::SsaoParameters::backgroundViewDepth)
        .def_readwrite("radiusWorld", &donut::render::SsaoParameters::radiusWorld)
        .def_readwrite("surfaceBias", &donut::render::SsaoParameters::surfaceBias)
        .def_readwrite("powerExponent", &donut::render::SsaoParameters::powerExponent)
        .def_readwrite("enableBlur", &donut::render::SsaoParameters::enableBlur)
        .def_readwrite("blurSharpness", &donut::render::SsaoParameters::blurSharpness);

    // Only the texture-taking constructor is bound. SsaoPass' other constructor takes a
    // CreateParameters (which holds a dm::int2 that would need flattening) and pairs with
    // CreateBindingSet(..., bindingSetIndex) for callers juggling several binding sets across
    // views; nothing in this repo needs that, so neither is exposed. Render's bindingSetIndex
    // is likewise fixed at its default of 0.
    py::class_<donut::render::SsaoPass, std::shared_ptr<donut::render::SsaoPass>>(m, "SsaoPass")
        .def(py::init([](nvrhi::IDevice* device, std::shared_ptr<donut::engine::ShaderFactory> shaderFactory,
                std::shared_ptr<donut::engine::CommonRenderPasses> commonPasses, nvrhi::ITexture* gbufferDepth,
                nvrhi::ITexture* gbufferNormals, nvrhi::ITexture* destinationTexture) {
            return new donut::render::SsaoPass(device, shaderFactory, commonPasses, gbufferDepth,
                gbufferNormals, destinationTexture);
        }), py::arg("device"), py::arg("shaderFactory"), py::arg("commonPasses"),
            py::arg("gbufferDepth"), py::arg("gbufferNormals"), py::arg("destinationTexture"))
        .def("Render", [](donut::render::SsaoPass &self, nvrhi::ICommandList* commandList,
                const donut::render::SsaoParameters &params, const donut::engine::IView &compositeView) {
            self.Render(commandList, params, compositeView);
        }, py::arg("commandList"), py::arg("params"), py::arg("compositeView"));

    py::class_<donut::engine::FramebufferFactory, std::shared_ptr<donut::engine::FramebufferFactory>>(m, "FramebufferFactory")
        .def(py::init<nvrhi::IDevice*>(), py::arg("device"))
        .def("SetRenderTargets", [](donut::engine::FramebufferFactory &self, std::vector<nvrhi::ITexture*> targets) {
            self.RenderTargets.clear();
            for (nvrhi::ITexture* t : targets)
                self.RenderTargets.push_back(t);
        }, py::arg("targets"))
        .def_property("depthTarget",
            [](const donut::engine::FramebufferFactory &self) -> nvrhi::ITexture* { return self.DepthTarget.Get(); },
            [](donut::engine::FramebufferFactory &self, nvrhi::ITexture* t) { self.DepthTarget = t; },
            py::return_value_policy::reference)
        .def_property("shadingRateSurface",
            [](const donut::engine::FramebufferFactory &self) -> nvrhi::ITexture* { return self.ShadingRateSurface.Get(); },
            [](donut::engine::FramebufferFactory &self, nvrhi::ITexture* t) { self.ShadingRateSurface = t; },
            py::return_value_policy::reference)
        .def("GetFramebuffer", [](donut::engine::FramebufferFactory &self, donut::engine::PlanarView &view) -> nvrhi::IFramebuffer* {
            return self.GetFramebuffer(view);
        }, py::arg("view"), py::return_value_policy::reference_internal);

    m.def("RenderView", [](nvrhi::ICommandList* commandList, donut::engine::PlanarView &view, donut::engine::PlanarView &viewPrev,
            nvrhi::IFramebuffer* framebuffer, donut::render::IDrawStrategy &drawStrategy, donut::render::IGeometryPass &pass,
            donut::render::GeometryPassContext &context, bool materialEvents) {
        donut::render::RenderView(commandList, &view, &viewPrev, framebuffer, drawStrategy, pass, context, materialEvents);
    }, py::arg("commandList"), py::arg("view"), py::arg("viewPrev"), py::arg("framebuffer"), py::arg("drawStrategy"),
       py::arg("pass"), py::arg("context"), py::arg("materialEvents") = false);

    m.def("RenderCompositeView", [](nvrhi::ICommandList* commandList, donut::engine::PlanarView &view, donut::engine::PlanarView &viewPrev,
            donut::engine::FramebufferFactory &framebufferFactory, std::shared_ptr<donut::engine::SceneGraphNode> rootNode,
            donut::render::IDrawStrategy &drawStrategy, donut::render::IGeometryPass &pass,
            donut::render::GeometryPassContext &passContext, bool materialEvents) {
        donut::render::RenderCompositeView(commandList, &view, &viewPrev, framebufferFactory, rootNode,
            drawStrategy, pass, passContext, nullptr, materialEvents);
    }, py::arg("commandList"), py::arg("view"), py::arg("viewPrev"), py::arg("framebufferFactory"), py::arg("rootNode"),
       py::arg("drawStrategy"), py::arg("pass"), py::arg("passContext"), py::arg("materialEvents") = false,
       // See the comment on CommandList.open above -- released for threaded_rendering.py's
       // concurrent per-face recording. Safe: this walks read-only scene-graph/mesh/material
       // data and issues draws into the caller's own CommandList, touching no Python objects.
       py::call_guard<py::gil_scoped_release>());

    // BaseCamera is registered (opaque, no constructor -- Python never creates one directly)
    // purely so FirstPersonCamera/ThirdPersonCamera can share it as a pybind11 base, letting
    // PlanarView.SetMatricesFromCamera below accept either camera type uniformly. Matrices
    // (dm::affine3/float4x4) aren't exposed to Python -- SetMatricesFromCamera consumes them
    // internally instead.
    py::class_<donut::app::BaseCamera>(m, "BaseCamera")
        .def("SetMoveSpeed", &donut::app::BaseCamera::SetMoveSpeed, py::arg("value"))
        // (x, y, z) -- math types aren't exposed to Python. Needed for camera-facing particle
        // billboard orientation (see rt_particles.py).
        .def("GetDir", [](const donut::app::BaseCamera &self) {
            const donut::math::float3 &d = self.GetDir();
            return py::make_tuple(d.x, d.y, d.z);
        })
        .def("GetUp", [](const donut::app::BaseCamera &self) {
            const donut::math::float3 &u = self.GetUp();
            return py::make_tuple(u.x, u.y, u.z);
        });

    py::class_<donut::app::FirstPersonCamera, donut::app::BaseCamera> firstPersonCamera(m, "FirstPersonCamera");
    firstPersonCamera.def(py::init<>());
    firstPersonCamera.def("LookAt", [](donut::app::FirstPersonCamera &self,
            float posX, float posY, float posZ, float targetX, float targetY, float targetZ) {
        self.LookAt(donut::math::float3(posX, posY, posZ), donut::math::float3(targetX, targetY, targetZ));
    }, py::arg("posX"), py::arg("posY"), py::arg("posZ"), py::arg("targetX"), py::arg("targetY"), py::arg("targetZ"));
    firstPersonCamera.def("Animate", &donut::app::FirstPersonCamera::Animate, py::arg("deltaT"));
    firstPersonCamera.def("KeyboardUpdate", &donut::app::FirstPersonCamera::KeyboardUpdate,
        py::arg("key"), py::arg("scancode"), py::arg("action"), py::arg("mods"));
    firstPersonCamera.def("MousePosUpdate", &donut::app::FirstPersonCamera::MousePosUpdate, py::arg("xpos"), py::arg("ypos"));
    firstPersonCamera.def("MouseButtonUpdate", &donut::app::FirstPersonCamera::MouseButtonUpdate,
        py::arg("button"), py::arg("action"), py::arg("mods"));

    // Orbit camera used by rt_particles.py. SetView feeds the camera's projection/viewport
    // back in (needed for its own mouse-drag translation math), matching the C++ original's
    // m_Camera.SetView(m_View) call after PlanarView is updated each frame.
    py::class_<donut::app::ThirdPersonCamera, donut::app::BaseCamera> thirdPersonCamera(m, "ThirdPersonCamera");
    thirdPersonCamera.def(py::init<>());
    thirdPersonCamera.def("SetTargetPosition", [](donut::app::ThirdPersonCamera &self, float x, float y, float z) {
        self.SetTargetPosition(donut::math::float3(x, y, z));
    }, py::arg("x"), py::arg("y"), py::arg("z"));
    thirdPersonCamera.def("SetDistance", &donut::app::ThirdPersonCamera::SetDistance, py::arg("distance"));
    thirdPersonCamera.def("SetRotation", &donut::app::ThirdPersonCamera::SetRotation, py::arg("yaw"), py::arg("pitch"));
    thirdPersonCamera.def("SetView", &donut::app::ThirdPersonCamera::SetView, py::arg("view"));
    thirdPersonCamera.def("Animate", &donut::app::ThirdPersonCamera::Animate, py::arg("deltaT"));
    thirdPersonCamera.def("KeyboardUpdate", &donut::app::ThirdPersonCamera::KeyboardUpdate,
        py::arg("key"), py::arg("scancode"), py::arg("action"), py::arg("mods"));
    thirdPersonCamera.def("MousePosUpdate", &donut::app::ThirdPersonCamera::MousePosUpdate, py::arg("xpos"), py::arg("ypos"));
    thirdPersonCamera.def("MouseButtonUpdate", &donut::app::ThirdPersonCamera::MouseButtonUpdate,
        py::arg("button"), py::arg("action"), py::arg("mods"));
    thirdPersonCamera.def("MouseScrollUpdate", &donut::app::ThirdPersonCamera::MouseScrollUpdate, py::arg("xoffset"), py::arg("yoffset"));

    // ICompositeView/IView are registered as real polymorphic bases rather than having every
    // pass signature hardcode PlanarView&: SkyPass/SsaoPass/ToneMappingPass/BloomPass all take
    // const ICompositeView&, and there are already two concrete views bound (PlanarView,
    // CubemapView). Same reasoning as IDrawStrategy/IGeometryPass above (see :2282-2290).
    // Neither base is constructible from Python -- they exist purely to carry the conversion.
    py::class_<donut::engine::ICompositeView>(m, "ICompositeView");
    py::class_<donut::engine::IView, donut::engine::ICompositeView>(m, "IView");

    py::class_<donut::engine::PlanarView, donut::engine::IView> planarView(m, "PlanarView");
    planarView.def(py::init<>());
    // Copy constructor: PlanarView has no Python-visible identity beyond its cached state, so
    // this is how Python takes a snapshot of "this frame's view" to keep around as "last
    // frame's view" (e.g. for TemporalAntiAliasingPass, which needs both) -- mirrors the
    // C++ pattern of plain copy-assigning one PlanarView into another.
    planarView.def(py::init<const donut::engine::PlanarView&>(), py::arg("other"));
    planarView.def("SetViewport", [](donut::engine::PlanarView &self, const nvrhi::Viewport &viewport) {
        self.SetViewport(viewport);
    }, py::arg("viewport"));
    planarView.def("SetVariableRateShadingState", &donut::engine::PlanarView::SetVariableRateShadingState, py::arg("state"));
    planarView.def("SetMatricesFromCamera", [](donut::engine::PlanarView &self, const donut::app::BaseCamera &camera,
            float aspectRatio, float verticalFovRadians, float zNear) {
        self.SetMatrices(camera.GetWorldToViewMatrix(), donut::math::perspProjD3DStyleReverse(verticalFovRadians, aspectRatio, zNear));
    }, py::arg("camera"), py::arg("aspectRatio"), py::arg("verticalFovRadians") = donut::math::PI_f * 0.25f, py::arg("zNear") = 0.1f);
    // Non-camera, non-reverse-Z view setup for static/orbiting subjects (see
    // deferred_shading.py): a combined yaw+pitch rotation, pushed back `distance` along
    // its own Z axis, with a regular (not reversed) D3D-style perspective projection.
    planarView.def("SetMatricesOrbit", [](donut::engine::PlanarView &self, float yawRadians, float pitchRadians, float distance,
            float aspectRatio, float fovYRadians, float zNear, float zFar) {
        donut::math::affine3 viewMatrix = donut::math::yawPitchRoll(yawRadians, 0.f, 0.f)
            * donut::math::yawPitchRoll(0.f, pitchRadians, 0.f)
            * donut::math::translation(donut::math::float3(0.f, 0.f, distance));
        donut::math::float4x4 projection = donut::math::perspProjD3DStyle(fovYRadians, aspectRatio, zNear, zFar);
        self.SetMatrices(viewMatrix, projection);
    }, py::arg("yawRadians"), py::arg("pitchRadians"), py::arg("distance"), py::arg("aspectRatio"),
       py::arg("fovYRadians"), py::arg("zNear"), py::arg("zFar"));

    // Explicit look-at, regular (non-reverse-Z) D3D-style perspective, for subjects whose eye
    // AND target both move independently (unlike SetMatricesOrbit's fixed-target-at-origin
    // yaw/pitch/distance parameterization -- see work_graphs.py, whose camera orbits both its
    // position and its look-at target on separate paths). The view matrix is built directly
    // (basis vectors from cross products, exactly the classic D3D "look-to" construction) and
    // packed into affine3's row-vector layout: m_linear's rows are (x.x,y.x,z.x), (x.y,y.y,z.y),
    // (x.z,y.z,z.z) -- the transpose of the natural [x;y;z] row layout -- and m_translation is
    // (dot(x,-eye), dot(y,-eye), dot(z,-eye)), matching how PlanarView::transformPoint applies
    // v*m_linear+m_translation in the same row-vector convention HLSL's mul(vec,matrix) uses.
    planarView.def("SetMatricesLookAt", [](donut::engine::PlanarView &self,
            float posX, float posY, float posZ, float targetX, float targetY, float targetZ,
            float upX, float upY, float upZ, float aspectRatio, float fovYRadians, float zNear, float zFar) {
        using namespace donut::math;
        const float3 eye(posX, posY, posZ);
        const float3 target(targetX, targetY, targetZ);
        const float3 up(upX, upY, upZ);

        const float3 z = normalize(target - eye);
        const float3 x = normalize(cross(up, z));
        const float3 y = cross(z, x);
        const float3 negEye = -eye;

        const affine3 viewMatrix(
            float3(x.x, y.x, z.x),
            float3(x.y, y.y, z.y),
            float3(x.z, y.z, z.z),
            float3(dot(x, negEye), dot(y, negEye), dot(z, negEye)));
        const float4x4 projection = perspProjD3DStyle(fovYRadians, aspectRatio, zNear, zFar);
        self.SetMatrices(viewMatrix, projection);
    }, py::arg("posX"), py::arg("posY"), py::arg("posZ"), py::arg("targetX"), py::arg("targetY"), py::arg("targetZ"),
       py::arg("upX"), py::arg("upY"), py::arg("upZ"), py::arg("aspectRatio"), py::arg("fovYRadians"),
       py::arg("zNear"), py::arg("zFar"));

    // Raw bytes of viewProj and its inverse, in work_graphs.py's own SceneConstantBuffer layout
    // (NOT donut's PlanarViewConstants layout that FillPlanarViewConstants above returns) --
    // GetViewProjectionMatrix/GetInverseViewProjectionMatrix already exist on PlanarView
    // (donut/engine/View.h:77-78), this just exposes them as one 128-byte blob. Transposed to
    // match work_graphs_d3d12.cpp's own upload convention (work_graphs_d3d12.cpp:607-608:
    // "constants.viewProj = transpose(view*proj);") -- scene_data.hlsli's cbuffer has no
    // `row_major` qualifier, so DXC packs it column-major; donut::math::float4x4 is row-major,
    // so it must be transposed before upload or mul(vertexPosition, viewProj) computes garbage.
    planarView.def("GetViewProjMatrixBytes", [](const donut::engine::PlanarView &self) {
        struct { donut::math::float4x4 viewProj, viewProjInverse; } out {
            donut::math::transpose(self.GetViewProjectionMatrix()),
            donut::math::transpose(self.GetInverseViewProjectionMatrix())
        };
        return py::bytes(reinterpret_cast<const char*>(&out), sizeof(out));
    });

    planarView.def("UpdateCache", &donut::engine::PlanarView::UpdateCache);

    // Standalone view*projection matrix computation for cases that don't go through
    // PlanarView at all (e.g. vertex_buffer.py's four independently-rotating model views,
    // uploaded straight into a constant buffer rather than driven by a View object): rotate
    // by `rotationRadians` around an arbitrary (auto-normalized) axis, tilt down by
    // `pitchRadians`, push back `distance`, then apply a regular D3D-style perspective
    // projection. Returns the resulting float4x4 as raw bytes, ready for CommandList.writeBuffer.
    m.def("ComputeRotatingViewProjMatrix", [](float axisX, float axisY, float axisZ, float rotationRadians,
            float pitchRadians, float distance, float aspectRatio, float fovYRadians, float zNear, float zFar) {
        donut::math::affine3 viewMatrix = donut::math::rotation(
                donut::math::normalize(donut::math::float3(axisX, axisY, axisZ)), rotationRadians)
            * donut::math::yawPitchRoll(0.f, pitchRadians, 0.f)
            * donut::math::translation(donut::math::float3(0.f, 0.f, distance));
        donut::math::float4x4 projMatrix = donut::math::perspProjD3DStyle(fovYRadians, aspectRatio, zNear, zFar);
        donut::math::float4x4 viewProjMatrix = donut::math::affineToHomogeneous(viewMatrix) * projMatrix;
        return py::bytes(reinterpret_cast<const char*>(&viewProjMatrix), sizeof(viewProjMatrix));
    }, py::arg("axisX"), py::arg("axisY"), py::arg("axisZ"), py::arg("rotationRadians"), py::arg("pitchRadians"),
       py::arg("distance"), py::arg("aspectRatio"), py::arg("fovYRadians"), py::arg("zNear"), py::arg("zFar"));
    planarView.def("GetViewportState", &donut::engine::PlanarView::GetViewportState);
    planarView.def("FillPlanarViewConstants", [](const donut::engine::PlanarView &self) {
        PlanarViewConstants constants{};
        self.FillPlanarViewConstants(constants);
        return py::bytes(reinterpret_cast<const char*>(&constants), sizeof(constants));
    });

    // CubemapView splits one transform into 6 face view/proj matrices for cube-map/environment
    // rendering (see threaded_rendering.py). Its faces are a plain PlanarView[6] internally, so
    // GetFaceView returns the existing PlanarView type -- no new view hierarchy is exposed.
    py::class_<donut::engine::CubemapView, donut::engine::IView> cubemapView(m, "CubemapView");
    cubemapView.def(py::init<>());
    // Fetches the camera's world-to-view transform on the C++ side (consistent with
    // PlanarView.SetMatricesFromCamera not exposing dm::affine3 to Python either) and forwards
    // it to CubemapView::SetTransform.
    cubemapView.def("SetTransformFromCamera", [](donut::engine::CubemapView &self, const donut::app::FirstPersonCamera &camera,
            float zNear, float cullDistance, bool useReverseInfiniteProjections) {
        self.SetTransform(camera.GetWorldToViewMatrix(), zNear, cullDistance, useReverseInfiniteProjections);
    }, py::arg("camera"), py::arg("zNear"), py::arg("cullDistance"), py::arg("useReverseInfiniteProjections") = true);
    cubemapView.def("SetArrayViewports", &donut::engine::CubemapView::SetArrayViewports,
        py::arg("resolution"), py::arg("firstArraySlice"));
    cubemapView.def("UpdateCache", &donut::engine::CubemapView::UpdateCache);
    // GetChildView(PLANAR, face) always returns a pointer into this CubemapView's own
    // m_FaceViews[6] array -- reference_internal ties the returned PlanarView's lifetime to
    // this CubemapView, since it owns the storage.
    cubemapView.def("GetFaceView", [](donut::engine::CubemapView &self, uint32_t face) -> donut::engine::PlanarView* {
        const donut::engine::IView* view = self.GetChildView(donut::engine::ViewType::PLANAR, face);
        return const_cast<donut::engine::PlanarView*>(static_cast<const donut::engine::PlanarView*>(view));
    }, py::arg("face"), py::return_value_policy::reference_internal);

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

    py::class_<donut::app::ApplicationBase, donut::app::IRenderPass, PyApplicationBase> applicationBase(m, "ApplicationBase");
    applicationBase.def(py::init<donut::app::DeviceManager*>(), py::arg("deviceManager"));
    applicationBase.def("RenderScene", &donut::app::ApplicationBase::RenderScene, py::arg("framebuffer"));
    applicationBase.def("RenderSplashScreen", &donut::app::ApplicationBase::RenderSplashScreen, py::arg("framebuffer"));
    applicationBase.def("BeginLoadingScene", [](donut::app::ApplicationBase &self, std::shared_ptr<donut::vfs::IFileSystem> fs, const std::filesystem::path& sceneFileName) {
        self.BeginLoadingScene(fs, sceneFileName);
    }, py::arg("fs"), py::arg("sceneFileName"));
    applicationBase.def("LoadScene", [](donut::app::ApplicationBase &self, std::shared_ptr<donut::vfs::IFileSystem> fs, const std::filesystem::path& sceneFileName) {
        return self.LoadScene(fs, sceneFileName);
    }, py::arg("fs"), py::arg("sceneFileName"));
    applicationBase.def("SceneUnloading", &donut::app::ApplicationBase::SceneUnloading);
    applicationBase.def("SceneLoaded", &donut::app::ApplicationBase::SceneLoaded);
    applicationBase.def("SetAsynchronousLoadingEnabled", &donut::app::ApplicationBase::SetAsynchronousLoadingEnabled, py::arg("enabled"));
    applicationBase.def("IsSceneLoading", &donut::app::ApplicationBase::IsSceneLoading);
    applicationBase.def("IsSceneLoaded", &donut::app::ApplicationBase::IsSceneLoaded);
    applicationBase.def("GetCommonPasses", &donut::app::ApplicationBase::GetCommonPasses);
    // Actual instances are always the PyApplicationBase trampoline, so these downcasts are
    // safe; they're needed because the backing members are protected on ApplicationBase
    // itself. Named/cased to match the m_-prefixed properties this module already exposes
    // for other classes' public fields (e.g. CommonRenderPasses.m_WhiteTexture).
    applicationBase.def_property("m_TextureCache",
        [](donut::app::ApplicationBase &self) {
            return static_cast<PyApplicationBase&>(self).GetTextureCache();
        },
        [](donut::app::ApplicationBase &self, std::shared_ptr<donut::engine::TextureCache> textureCache) {
            static_cast<PyApplicationBase&>(self).SetTextureCache(std::move(textureCache));
        });
    applicationBase.def_property("m_CommonPasses",
        &donut::app::ApplicationBase::GetCommonPasses,
        [](donut::app::ApplicationBase &self, std::shared_ptr<donut::engine::CommonRenderPasses> commonPasses) {
            static_cast<PyApplicationBase&>(self).SetCommonPasses(std::move(commonPasses));
        });
    // Read-only: the real setter is SetAsynchronousLoadingEnabled(), which BeginLoadingScene()
    // reads on the next scene load; there's no corresponding C++ getter, so this mirrors the
    // field directly, matching the other m_-prefixed properties in this module.
    applicationBase.def_property_readonly("m_IsAsyncLoad", [](donut::app::ApplicationBase &self) {
        return static_cast<PyApplicationBase&>(self).GetIsAsyncLoad();
    });

    py::class_<donut::app::ImGui_Renderer, donut::app::IRenderPass, PyImGuiRenderer> imguiRenderer(m, "ImGui_Renderer");
    imguiRenderer.def(py::init<donut::app::DeviceManager*>(), py::arg("deviceManager"));
    imguiRenderer.def("Init", [](donut::app::ImGui_Renderer &self, std::shared_ptr<donut::engine::ShaderFactory> shaderFactory) {
        return self.Init(shaderFactory);
    }, py::arg("shaderFactory"));

    // Only the ImGui:: entry points rt_particles.py's UserInterface.buildUI() actually calls.
    // Out-params (bool*, float*, int*) become (changed, newValue...) return tuples -- Python
    // has no pointers, so the caller re-assigns its own state from the tuple, e.g.
    // changed, ui.enableAnimations = pyd.ImGui.Checkbox("...", ui.enableAnimations).
    py::class_<ImGuiNS>(m, "ImGui")
        // Disables ImGui's automatic imgui.ini window-layout persistence, which would
        // otherwise write that file into the process's working directory on exit (see
        // rt_particles.py's UserInterface, matching the C++ original's
        // ImGui::GetIO().IniFilename = nullptr).
        .def_static("DisableIniFile", []() { ImGui::GetIO().IniFilename = nullptr; })
        .def_static("SetNextWindowPos", [](float x, float y, int cond) {
            ImGui::SetNextWindowPos(ImVec2(x, y), cond);
        }, py::arg("x"), py::arg("y"), py::arg("cond") = 0)
        // p_open is always null in this codebase's usage (no closable windows).
        .def_static("Begin", [](const std::string &name, int flags) {
            return ImGui::Begin(name.c_str(), nullptr, flags);
        }, py::arg("name"), py::arg("flags") = 0)
        .def_static("End", &ImGui::End)
        .def_static("Checkbox", [](const std::string &label, bool value) {
            bool changed = ImGui::Checkbox(label.c_str(), &value);
            return py::make_tuple(changed, value);
        }, py::arg("label"), py::arg("value"))
        .def_static("Separator", &ImGui::Separator)
        // TextUnformatted, not Text -- Text() parses its argument as a printf format string,
        // which would let arbitrary Python string content control formatting.
        .def_static("Text", [](const std::string &text) {
            ImGui::TextUnformatted(text.c_str());
        }, py::arg("text"))
        .def_static("Indent", []() { ImGui::Indent(); })
        .def_static("Unindent", []() { ImGui::Unindent(); })
        // items are joined into ImGui's own "item1\0item2\0" combo format internally.
        .def_static("Combo", [](const std::string &label, int currentItem, const std::vector<std::string> &items) {
            std::string joined;
            for (const auto &item : items) { joined += item; joined += '\0'; }
            bool changed = ImGui::Combo(label.c_str(), &currentItem, joined.c_str());
            return py::make_tuple(changed, currentItem);
        }, py::arg("label"), py::arg("currentItem"), py::arg("items"))
        .def_static("PushItemWidth", &ImGui::PushItemWidth, py::arg("width"))
        .def_static("PopItemWidth", []() { ImGui::PopItemWidth(); })
        .def_static("BeginCombo", [](const std::string &label, const std::string &previewValue) {
            return ImGui::BeginCombo(label.c_str(), previewValue.c_str());
        }, py::arg("label"), py::arg("previewValue"))
        .def_static("Selectable", [](const std::string &label, bool selected) {
            return ImGui::Selectable(label.c_str(), selected);
        }, py::arg("label"), py::arg("selected") = false)
        .def_static("EndCombo", []() { ImGui::EndCombo(); })
        .def_static("DragFloat3", [](const std::string &label, float x, float y, float z, float speed) {
            float v[3] = { x, y, z };
            bool changed = ImGui::DragFloat3(label.c_str(), v, speed);
            return py::make_tuple(changed, v[0], v[1], v[2]);
        }, py::arg("label"), py::arg("x"), py::arg("y"), py::arg("z"), py::arg("speed") = 1.0f)
        .def_static("Button", [](const std::string &label) {
            return ImGui::Button(label.c_str());
        }, py::arg("label"));

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
    deviceCreationParameters.def_readwrite("enableJoystickInput", &donut::app::DeviceCreationParameters::enableJoystickInput);
#if DONUT_WITH_AFTERMATH
    // Only exists in builds configured with -DPYDONUT_WITH_AFTERMATH=ON: the underlying field
    // is itself inside #if DONUT_WITH_AFTERMATH (DeviceManager.h:104-106), so binding it
    // unconditionally would not compile. Python must gate on pyd.AFTERMATH_AVAILABLE.
    deviceCreationParameters.def_readwrite("enableAftermath", &donut::app::DeviceCreationParameters::enableAftermath);
#endif
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
