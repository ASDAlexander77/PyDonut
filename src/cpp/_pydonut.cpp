#include <string>
#include <vector>
#include <memory>

#include <pybind11/pybind11.h>
#include <pybind11/native_enum.h>
#include <pybind11/stl.h>
#include <pybind11/complex.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>

#include <donut/app/DeviceManager.h>
#include <donut/app/ApplicationBase.h>

#pragma once

namespace py = pybind11;

PYBIND11_MODULE(_pydonut, m) {
    m.doc() = "pybind11 donut module";

    pybind11::native_enum<nvrhi::GraphicsAPI>(m, "GraphicsAPI", "enum.Enum")
        .value("D3D11", nvrhi::GraphicsAPI::D3D11)
        .value("D3D12", nvrhi::GraphicsAPI::D3D12)
        .value("Vulkan", nvrhi::GraphicsAPI::VULKAN)
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

    pybind11::class_<donut::app::DeviceManager> deviceManager(m, "DeviceManager");
    deviceManager.def_static(
        "Create", 
        [](nvrhi::GraphicsAPI api) {
            return  std::shared_ptr<donut::app::DeviceManager>(donut::app::DeviceManager::Create(api));
        },
        py::arg("api") = nvrhi::GraphicsAPI::VULKAN);
    deviceManager.def(
        "CreateWindowDeviceAndSwapChain", 
        &donut::app::DeviceManager::CreateWindowDeviceAndSwapChain, 
        py::arg("params"), 
        py::arg("windowTitle") = "");

    pybind11::class_<donut::app::DeviceCreationParameters> deviceCreationParameters(m, "DeviceCreationParameters");
    deviceCreationParameters.def(pybind11::init<>());
    deviceCreationParameters.def_readwrite("enableDebugRuntime", &donut::app::DeviceCreationParameters::enableDebugRuntime);
    deviceCreationParameters.def_readwrite("enableNvrhiValidationLayer", &donut::app::DeviceCreationParameters::enableNvrhiValidationLayer);
}
