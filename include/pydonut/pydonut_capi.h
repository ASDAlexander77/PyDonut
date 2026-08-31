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

// pydonut C API -- the interop seam that lets a *separate* Python extension module share
// nvrhi and donut objects with pydonut.
//
// Why this exists: _pydonut statically links donut_core/donut_engine/donut_render/donut_app
// and nvrhi. A second extension module that linked its own static copy of those would get a
// duplicate set of nvrhi/donut globals and could not be handed pydonut's DeviceManager or
// command lists. Instead, a consumer module links *no* donut or nvrhi implementation at all:
// nvrhi's IDevice/ICommandList/ITexture/... are pure abstract interfaces, so calling their
// methods needs only the headers and a valid pointer, which is exactly what this API hands
// out. (Free functions such as nvrhi::utils::* are ordinary code and are NOT covered -- a
// consumer that wants those must compile them into itself.)
//
// Usage from a consumer module:
//
//     // -I $(python -c "import pydonut; print(pydonut.get_include())")
//     #include <pydonut/pydonut_capi.h>
//
//     static const PyDonut_CAPI *g_pyd = nullptr;
//     PYBIND11_MODULE(_pyrtxpt, m) {
//         g_pyd = PyDonut_ImportCAPI();
//         if (!g_pyd) throw py::error_already_set();
//         ...
//         nvrhi::IDevice *dev = g_pyd->UnwrapDevice(pyDeviceObject.ptr());
//     }
//
// The consumer must compile against donut/nvrhi headers close enough to the ones pydonut was
// built from that the vtable layouts agree. In practice: use the same Donut commit. Nothing
// can check that at runtime, which is why abi_version and build_config exist -- they catch the
// mismatches that *can* be detected, not this one.
//
// ---------------------------------------------------------------------------------------
// Conventions -- all of these matter:
//
//   * GIL: every function here touches PyObject state and MUST be called with the GIL held.
//   * None: an Unwrap* on Py_None (or NULL) returns nullptr WITHOUT setting a Python error --
//     that is a legitimate "no object". Callers separate it from real failure by checking
//     PyErr_Occurred(). A wrong-typed object returns nullptr WITH a TypeError set.
//   * Unwrap* BORROWS. The returned pointer stays valid only while the Python object that owns
//     it is alive, and no reference is added. Do not store it past the call unless you keep
//     that Python object alive yourself.
//   * Wrap* takes a raw pointer, ADDS a reference to it, and returns a NEW Python reference
//     (or NULL with an error set). Wrapping nullptr returns a new reference to None.
//   * Wrap* returns a new *reference*, not necessarily a new *object*: pybind11 keeps a
//     registry of live instances keyed by pointer, so wrapping a resource Python already holds
//     hands back that same object (and quietly drops the reference this call added) rather than
//     creating a second wrapper for one resource. Identity therefore survives a round trip,
//     which is what you want -- just do not assume the result is freshly minted.
//   * Wrap* exists only for nvrhi IResource-derived types, whose intrusive refcount makes a
//     raw pointer safe to round-trip. It is deliberately absent for donut's engine classes
//     (ShaderFactory, Scene, ...), which pydonut holds by std::shared_ptr: rebuilding a
//     shared_ptr from a raw pointer would create a second, independent ownership group and
//     eventually double-free. Those are borrow-only.
//   * nvrhi::IDevice is borrow-only for the mirror-image reason -- pydonut binds it with a
//     non-owning holder because the DeviceManager owns the device.
//   * No exception ever crosses this boundary; failures are reported the Python way.
// ---------------------------------------------------------------------------------------

#ifndef PYDONUT_CAPI_H
#define PYDONUT_CAPI_H

#include <Python.h>
#include <stdint.h>

// Bumped only for a BREAKING change (a member removed, reordered, or its meaning changed).
// Appending new function pointers at the end of the struct keeps the version and is detected
// via struct_size instead, so an older consumer keeps working against a newer pydonut.
#define PYDONUT_CAPI_ABI_VERSION 1

// Must match byte for byte in PyCapsule_GetPointer.
#define PYDONUT_CAPI_CAPSULE_NAME "pydonut._pydonut._C_API"

namespace nvrhi {
    class IDevice;
    class ICommandList;
    class ITexture;
    class IBuffer;
    class IFramebuffer;
    class ISampler;
    class IBindingLayout;
    class IBindingSet;
    class IShader;
    namespace rt {
        class IAccelStruct;
    }
}

namespace donut {
    namespace app {
        class DeviceManager;
    }
    namespace engine {
        class ShaderFactory;
        class CommonRenderPasses;
        class DescriptorTableManager;
        class TextureCache;
        class FramebufferFactory;
        class Scene;
        class SceneGraph;
        class IView;
    }
}

// Deliberately NOT inside extern "C": the members below name C++ types (nvrhi::IDevice,
// donut::engine::Scene, ...), so this table can never be consumed from C anyway, and C language
// linkage on the function-pointer members would make assigning ordinary C++ functions to them
// ill-formed. What actually matters for interop is the layout, and that is plain: standard
// layout, no virtuals, no C++ library types, append-only.
struct PyDonut_CAPI {
    // --- identity; always the first two members, at a fixed offset, so that even a
    // mismatched consumer can read them safely before trusting anything else here. ---
    uint32_t abi_version;   // == PYDONUT_CAPI_ABI_VERSION
    uint32_t struct_size;   // == sizeof(PyDonut_CAPI) as pydonut was built

    // Comma-separated build switches of the pydonut that produced this struct, e.g.
    // "d3d12,vulkan,dxc". A consumer needing D3D12 interop should check for it here rather
    // than discover its absence at runtime.
    const char *build_config;

    // --- borrow: Python object -> raw pointer (see conventions above) ---
    nvrhi::IDevice          *(*UnwrapDevice)(PyObject *obj);
    nvrhi::ICommandList     *(*UnwrapCommandList)(PyObject *obj);
    nvrhi::ITexture         *(*UnwrapTexture)(PyObject *obj);
    nvrhi::IBuffer          *(*UnwrapBuffer)(PyObject *obj);
    nvrhi::IFramebuffer     *(*UnwrapFramebuffer)(PyObject *obj);
    nvrhi::ISampler         *(*UnwrapSampler)(PyObject *obj);
    nvrhi::IBindingLayout   *(*UnwrapBindingLayout)(PyObject *obj);
    nvrhi::IBindingSet      *(*UnwrapBindingSet)(PyObject *obj);
    nvrhi::IShader          *(*UnwrapShader)(PyObject *obj);
    nvrhi::rt::IAccelStruct *(*UnwrapAccelStruct)(PyObject *obj);

    donut::app::DeviceManager             *(*UnwrapDeviceManager)(PyObject *obj);
    donut::engine::ShaderFactory          *(*UnwrapShaderFactory)(PyObject *obj);
    donut::engine::CommonRenderPasses     *(*UnwrapCommonRenderPasses)(PyObject *obj);
    donut::engine::DescriptorTableManager *(*UnwrapDescriptorTableManager)(PyObject *obj);
    donut::engine::TextureCache           *(*UnwrapTextureCache)(PyObject *obj);
    donut::engine::FramebufferFactory     *(*UnwrapFramebufferFactory)(PyObject *obj);
    donut::engine::Scene                  *(*UnwrapScene)(PyObject *obj);
    donut::engine::SceneGraph             *(*UnwrapSceneGraph)(PyObject *obj);
    donut::engine::IView                  *(*UnwrapView)(PyObject *obj);

    // --- wrap: raw pointer -> new Python reference, adding an nvrhi reference ---
    PyObject *(*WrapCommandList)(nvrhi::ICommandList *ptr);
    PyObject *(*WrapTexture)(nvrhi::ITexture *ptr);
    PyObject *(*WrapBuffer)(nvrhi::IBuffer *ptr);
    PyObject *(*WrapFramebuffer)(nvrhi::IFramebuffer *ptr);
    PyObject *(*WrapSampler)(nvrhi::ISampler *ptr);
    PyObject *(*WrapBindingLayout)(nvrhi::IBindingLayout *ptr);
    PyObject *(*WrapBindingSet)(nvrhi::IBindingSet *ptr);
    PyObject *(*WrapShader)(nvrhi::IShader *ptr);
    PyObject *(*WrapAccelStruct)(nvrhi::rt::IAccelStruct *ptr);
};

// Imports pydonut and returns its C API table, or nullptr with a Python error set. The
// returned pointer belongs to the pydonut module and stays valid for the life of the process,
// so call this once at module init and cache it. Requires the GIL.
inline const PyDonut_CAPI *PyDonut_ImportCAPI() {
    PyObject *module = PyImport_ImportModule("pydonut._pydonut");
    if (!module) {
        return nullptr;
    }

    PyObject *capsule = PyObject_GetAttrString(module, "_C_API");
    Py_DECREF(module);
    if (!capsule) {
        return nullptr;
    }

    void *pointer = PyCapsule_GetPointer(capsule, PYDONUT_CAPI_CAPSULE_NAME);
    Py_DECREF(capsule);
    if (!pointer) {
        return nullptr;
    }

    const PyDonut_CAPI *api = static_cast<const PyDonut_CAPI *>(pointer);

    if (api->abi_version != PYDONUT_CAPI_ABI_VERSION) {
        PyErr_Format(PyExc_ImportError,
                     "pydonut C API version mismatch: this module was built against ABI %d, but "
                     "the installed pydonut provides ABI %u. Rebuild against a matching pydonut.",
                     PYDONUT_CAPI_ABI_VERSION, (unsigned)api->abi_version);
        return nullptr;
    }

    // Same ABI version but a smaller table means the installed pydonut predates a function this
    // consumer's header knows about, and reading past its end would be a wild call. A LARGER
    // table is fine: everything this header declares is present and at the same offset.
    if (api->struct_size < sizeof(PyDonut_CAPI)) {
        PyErr_Format(PyExc_ImportError,
                     "pydonut C API is smaller than expected (%u bytes, need %u): the installed "
                     "pydonut is older than the headers this module was built against.",
                     (unsigned)api->struct_size, (unsigned)sizeof(PyDonut_CAPI));
        return nullptr;
    }

    return api;
}

#endif // PYDONUT_CAPI_H
