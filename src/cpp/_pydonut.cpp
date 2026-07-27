#include <string>
#include <vector>
#include <memory>
#include <optional>

#include <pybind11/pybind11.h>
#include <pybind11/native_enum.h>
#include <pybind11/stl.h>
#include <pybind11/complex.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>

#include <donut/app/DeviceManager.h>
#include <donut/app/ApplicationBase.h>
#include <donut/core/log.h>

#pragma once

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

    // Opaque nvrhi resource handles: not constructible or usable from Python directly,
    // just passed around between DeviceManager/IRenderPass calls. py::nodelete keeps
    // pybind11 from ever trying to destroy an object it doesn't own.
    py::class_<nvrhi::IFramebuffer, std::unique_ptr<nvrhi::IFramebuffer, py::nodelete>>(m, "Framebuffer");
    py::class_<nvrhi::ITexture, std::unique_ptr<nvrhi::ITexture, py::nodelete>>(m, "Texture");
    py::class_<nvrhi::IDevice, std::unique_ptr<nvrhi::IDevice, py::nodelete>>(m, "Device");

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
