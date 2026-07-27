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
#include <donut/core/log.h>
#include <donut/core/vfs/VFS.h>
#include <donut/engine/ShaderFactory.h>
#include <nvrhi/utils.h>

#if PYDONUT_HAVE_DXC
#include <wrl/client.h>
#include <dxcapi.h>
#endif

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

// Transfers ownership of an nvrhi RefCountPtr's single reference into a std::shared_ptr,
// releasing via nvrhi's own AddRef/Release rather than `delete` (nvrhi resources are refcounted).
template <typename T>
std::shared_ptr<T> DetachToShared(nvrhi::RefCountPtr<T> handle) {
    T* raw = handle.Detach();
    return std::shared_ptr<T>(raw, [](T* p) { if (p) p->Release(); });
}

#if PYDONUT_HAVE_DXC

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

// Compiles HLSL source to DXIL (D3D12) or SPIR-V (Vulkan) in-process via DXC, entirely
// in memory -- no ShaderMake, no external process, no filesystem round-trip.
py::bytes CompileShaderWithDXC(
    const std::string &source,
    const std::string &entryPoint,
    nvrhi::ShaderType shaderType,
    nvrhi::GraphicsAPI api,
    const std::string &sourceName,
    const std::string &shaderModel)
{
    using Microsoft::WRL::ComPtr;

    ComPtr<IDxcUtils> utils;
    ComPtr<IDxcCompiler3> compiler;
    if (FAILED(DxcCreateInstance(CLSID_DxcUtils, IID_PPV_ARGS(&utils))) ||
        FAILED(DxcCreateInstance(CLSID_DxcCompiler, IID_PPV_ARGS(&compiler))))
        throw std::runtime_error("CompileShader: failed to create the DXC compiler instance");

    ComPtr<IDxcIncludeHandler> includeHandler;
    utils->CreateDefaultIncludeHandler(&includeHandler);

    std::wstring wEntryPoint = ToWide(entryPoint);
    std::wstring wProfile = std::wstring(HlslProfilePrefix(shaderType)) + L"_" + ToWide(shaderModel);
    std::wstring wSourceName = ToWide(sourceName);

    std::vector<LPCWSTR> args = {
        wSourceName.c_str(),
        L"-E", wEntryPoint.c_str(),
        L"-T", wProfile.c_str(),
    };
    if (api == nvrhi::GraphicsAPI::VULKAN)
        args.push_back(L"-spirv");

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

#endif // PYDONUT_HAVE_DXC

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

    pybind11::native_enum<nvrhi::CommandQueue>(m, "CommandQueue", "enum.Enum")
        .value("Graphics", nvrhi::CommandQueue::Graphics)
        .value("Compute", nvrhi::CommandQueue::Compute)
        .value("Copy", nvrhi::CommandQueue::Copy)
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
    py::class_<nvrhi::ITexture, std::unique_ptr<nvrhi::ITexture, py::nodelete>>(m, "Texture");
    py::class_<nvrhi::IDevice, std::unique_ptr<nvrhi::IDevice, py::nodelete>> device(m, "Device");

    // nvrhi objects created through factory calls below: each create*() call returns one
    // owning reference, handed to Python as a std::shared_ptr that Releases() on collection.
    py::class_<nvrhi::IShader, std::shared_ptr<nvrhi::IShader>>(m, "Shader");
    py::class_<nvrhi::IGraphicsPipeline, std::shared_ptr<nvrhi::IGraphicsPipeline>>(m, "GraphicsPipeline");
    py::class_<nvrhi::ICommandList, std::shared_ptr<nvrhi::ICommandList>> commandList(m, "CommandList");

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
        .def_readwrite("depthTestEnable", &nvrhi::DepthStencilState::depthTestEnable);

    py::class_<nvrhi::RenderState>(m, "RenderState")
        .def(py::init<>())
        .def_readwrite("depthStencilState", &nvrhi::RenderState::depthStencilState);

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
            py::return_value_policy::reference);

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
            py::return_value_policy::reference);

    framebuffer.def("getFramebufferInfo", &nvrhi::IFramebuffer::getFramebufferInfo, py::return_value_policy::reference_internal);

    device.def("getGraphicsAPI", &nvrhi::IDevice::getGraphicsAPI);
    device.def("createCommandList", [](nvrhi::IDevice &self) {
        return DetachToShared(self.createCommandList());
    });
    device.def("createGraphicsPipeline", [](nvrhi::IDevice &self, const nvrhi::GraphicsPipelineDesc &desc, const nvrhi::FramebufferInfoEx &framebufferInfo) {
        return DetachToShared(self.createGraphicsPipeline(desc, framebufferInfo));
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

    commandList.def("open", &nvrhi::ICommandList::open);
    commandList.def("close", &nvrhi::ICommandList::close);
    commandList.def("setGraphicsState", &nvrhi::ICommandList::setGraphicsState, py::arg("state"));
    commandList.def("draw", &nvrhi::ICommandList::draw, py::arg("args"));

    m.def("ClearColorAttachment", &nvrhi::utils::ClearColorAttachment,
        py::arg("commandList"), py::arg("framebuffer"), py::arg("attachmentIndex"), py::arg("color"));

    m.def("GetDirectoryWithExecutable", &donut::app::GetDirectoryWithExecutable);
    m.def("GetShaderTypeName", &donut::app::GetShaderTypeName, py::arg("api"));

#if PYDONUT_HAVE_DXC
    m.def("CompileShader", &CompileShaderWithDXC,
        py::arg("source"), py::arg("entryPoint"), py::arg("shaderType"), py::arg("api"),
        py::arg("sourceName") = "shader.hlsl", py::arg("shaderModel") = "6_5");
#endif

    py::class_<donut::vfs::IFileSystem, std::shared_ptr<donut::vfs::IFileSystem>>(m, "IFileSystem");
    py::class_<donut::vfs::NativeFileSystem, donut::vfs::IFileSystem, std::shared_ptr<donut::vfs::NativeFileSystem>>(m, "NativeFileSystem")
        .def(py::init<>());

    py::class_<donut::engine::ShaderFactory, std::shared_ptr<donut::engine::ShaderFactory>> shaderFactory(m, "ShaderFactory");
    shaderFactory.def(py::init([](nvrhi::IDevice* device, std::shared_ptr<donut::vfs::IFileSystem> fs, const std::filesystem::path& basePath) {
        return new donut::engine::ShaderFactory(nvrhi::DeviceHandle(device), fs, basePath);
    }), py::arg("device"), py::arg("fs"), py::arg("basePath"));
    shaderFactory.def("CreateShader", [](donut::engine::ShaderFactory &self, const std::string &fileName, const std::string &entryName, nvrhi::ShaderType shaderType) {
        return DetachToShared(self.CreateShader(fileName.c_str(), entryName.c_str(), nullptr, shaderType));
    }, py::arg("fileName"), py::arg("entryName"), py::arg("shaderType"));

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
