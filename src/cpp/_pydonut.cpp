#include <string>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/complex.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>

#include <donut/app/ApplicationBase.h>

#pragma once

namespace py = pybind11;

PYBIND11_MODULE(_pydonut, m) {
    m.doc() = "pybind11 donut module";

    pybind11::enum_<nvrhi::GraphicsAPI>(m, "GraphicsAPI")
        .value("D3D11", nvrhi::GraphicsAPI::D3D11)
        .value("D3D12", nvrhi::GraphicsAPI::D3D12)
        .value("Vulkan", nvrhi::GraphicsAPI::VULKAN);

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
}
