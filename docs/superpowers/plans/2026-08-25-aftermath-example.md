# Aftermath Example Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `E:\Gits\Donut-Samples\examples\aftermath\aftermath.cpp` to `aftermath.py`, adding the four missing native bindings it needs and an opt-in `PYDONUT_WITH_AFTERMATH` build option that produces real NSight Aftermath GPU crash dumps.

**Architecture:** Five bindings go into `_pydonut.cpp` (a `BindingLayoutItem.PushConstants` factory, `CommandList.beginMarker`/`endMarker`, a build-conditional `DeviceCreationParameters.enableAftermath`, an `AFTERMATH_AVAILABLE` module flag, and one deliberately-unsafe native-memory-destroying helper for the page-fault path). A new CMake option flips donut's `DONUT_WITH_AFTERMATH`, which triggers donut's own configure-time SDK fetch, and copies the resulting DLL next to `_pydonut`. Then `aftermath.py` follows `basic_triangle.py`'s runtime-shader-compilation structure paired with a `work_graphs.py`-style `ImGui_Renderer` subclass sharing one mutable state object.

**Tech Stack:** pybind11 (C++/nvrhi/donut bindings), Python 3.14, HLSL compiled at runtime through `pyd.CompileShader` (DXC), Dear ImGui via donut's `ImGui_Renderer`, CMake + scikit-build-core.

**Spec:** `docs/superpowers/specs/2026-08-25-aftermath-example-design.md`

## Global Constraints

- Match `E:\Gits\Donut-Samples\examples\aftermath\aftermath.cpp` behavior exactly — this is a straight port, not a reinterpretation. Deviations are listed explicitly in the spec (runtime shader compilation instead of `ShaderFactory`/VFS; `__spirv__` instead of `SPIRV`; a shared state object instead of a C++ reference-plus-setter; an `AFTERMATH_AVAILABLE` notice with no C++ counterpart).
- **This codebase has no pytest suite for example scripts.** `pyproject.toml` declares `pytest>=9.0.2` in its `dev` dependency group but no `tests/` directory exists. Verification for GPU-rendering code in this repo is always a manual run plus a visual/log check — see every existing design doc's Verification section. Do not invent unit tests for rendering code that has none elsewhere in the codebase.
- **Do not press either crash button during implementation.** Triggering a crash resets the display driver. Per the agreed verification scope, implementation stops at "the window renders and both buttons are present"; the user triggers the crashes themselves.
- Rebuild command after any C++ or CMake change: `uv sync --reinstall-package pydonut` (uv's cache keys cover `src/**/*.{h,c,hpp,cpp}` and `CMakeLists.txt` per `pyproject.toml:24-31`).
- To rebuild **with** Aftermath: `SKBUILD_CMAKE_DEFINE=PYDONUT_WITH_AFTERMATH=ON uv sync --reinstall-package pydonut`. An environment variable alone changes no cache-key file, so `--reinstall-package pydonut` is mandatory or uv silently reuses the cached wheel.
- Guard macros are **asymmetric** and must match existing usage in `_pydonut.cpp`: D3D12 uses `#ifdef NVRHI_WITH_DX12` (lines 68, 1448, 1589), Vulkan uses `#if DONUT_WITH_VULKAN` (lines 2925, 2965). There is no `NVRHI_WITH_VULKAN` definition on this target.
- Every new source file carries the project's standard 22-line copyright header, copied verbatim from `basic_triangle.py:1-22` (Python) — commit `be7a1f9` added these across the repo.

---

## File Structure

- Modify: `src/cpp/_pydonut.cpp` — five new bindings (Tasks 1 and 2).
- Modify: `src/pydonut/_pydonut.pyi` — stubs for all five (Tasks 1 and 2).
- Modify: `src/pydonut/__init__.py` — export the two module-level names (Task 2).
- Modify: `CMakeLists.txt` — `PYDONUT_WITH_AFTERMATH` option, SDK wiring, DLL copy (Task 3).
- Create: `shaders/aftermath/shaders.hlsl` — the ported shader (Task 4).
- Create: `aftermath.py` — the example (Task 5).
- Modify: `README.md` — build documentation (Task 6).

Task order matters: Task 5 consumes bindings from Tasks 1-2, the shader from Task 4, and is only fully exercisable after Task 3.

---

### Task 1: Three straightforward bindings — `BindingLayoutItem.PushConstants`, `CommandList.beginMarker`/`endMarker`

These three have no build-conditionality and no risk; they are separated from Task 2 so the risky native-memory helper can be reviewed and rejected on its own.

**Files:**
- Modify: `src/cpp/_pydonut.cpp:1114` (add `BindingLayoutItem.PushConstants`)
- Modify: `src/cpp/_pydonut.cpp:1679` (add `CommandList.beginMarker`/`endMarker`)
- Modify: `src/pydonut/_pydonut.pyi:567` (add `BindingLayoutItem.PushConstants` stub)
- Modify: `src/pydonut/_pydonut.pyi:830` (add `CommandList.beginMarker`/`endMarker` stubs)

**Interfaces:**
- Produces: `pyd.BindingLayoutItem.PushConstants(slot: int, byteSize: int) -> BindingLayoutItem`; `commandList.beginMarker(name: str) -> None`; `commandList.endMarker() -> None`. Task 5 consumes all three.

- [ ] **Step 1: Add `BindingLayoutItem.PushConstants` to `_pydonut.cpp`**

In `src/cpp/_pydonut.cpp`, find this exact line (currently line 1114 — the last `def_static` of the `BindingLayoutItem` class, ending in a semicolon):

```cpp
        .def_static("RayTracingAccelStruct", &nvrhi::BindingLayoutItem::RayTracingAccelStruct, py::arg("slot"));
```

Replace it with these two lines (note the semicolon moves to the new last entry):

```cpp
        .def_static("RayTracingAccelStruct", &nvrhi::BindingLayoutItem::RayTracingAccelStruct, py::arg("slot"))
        .def_static("PushConstants", &nvrhi::BindingLayoutItem::PushConstants, py::arg("slot"), py::arg("byteSize"));
```

- [ ] **Step 2: Add `CommandList.beginMarker`/`endMarker` to `_pydonut.cpp`**

In `src/cpp/_pydonut.cpp`, find this exact line (currently line 1679):

```cpp
    commandList.def("endTimerQuery", &nvrhi::ICommandList::endTimerQuery, py::arg("query"));
```

Add this immediately after it:

```cpp
    // Debug marker ranges. Nestable: each beginMarker must be matched by an endMarker. These
    // are what make an Aftermath crash dump readable -- Aftermath stores markers as hashed
    // 64-bit values and resolves them back to these strings via
    // donut::app::AftermathCrashDump::ResolveMarker, so the innermost live marker names the
    // scope that faulted (see aftermath.py).
    commandList.def("beginMarker", [](nvrhi::ICommandList &self, const std::string &name) {
        self.beginMarker(name.c_str());
    }, py::arg("name"));
    commandList.def("endMarker", &nvrhi::ICommandList::endMarker);
```

- [ ] **Step 3: Add the `.pyi` stub for `BindingLayoutItem.PushConstants`**

In `src/pydonut/_pydonut.pyi`, find this exact pair of lines (currently 566-567):

```python
    @staticmethod
    def StructuredBuffer_UAV(slot: int) -> BindingLayoutItem: ...
```

Add immediately after them:

```python
    @staticmethod
    def PushConstants(slot: int, byteSize: int) -> BindingLayoutItem: ...
```

- [ ] **Step 4: Add the `.pyi` stubs for the marker methods**

In `src/pydonut/_pydonut.pyi`, find this exact line (currently line 830):

```python
    def setEnableAutomaticBarriers(self: CommandList, enable: bool) -> None: ...
```

Add immediately **before** it:

```python
    # Debug marker range, nestable; each beginMarker needs a matching endMarker. Names the
    # faulting scope in an NSight Aftermath crash dump.
    def beginMarker(self: CommandList, name: str) -> None: ...
    def endMarker(self: CommandList) -> None: ...
```

- [ ] **Step 5: Rebuild**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds with no new warnings from `_pydonut.cpp`.

- [ ] **Step 6: Verify the bindings exist**

Run:

```sh
uv run python -c "import src.pydonut as pyd; print(pyd.BindingLayoutItem.PushConstants(0, 4)); print(pyd.CommandList.beginMarker, pyd.CommandList.endMarker)"
```

Expected: prints a `BindingLayoutItem` repr and two bound-method objects, with no `AttributeError`.

- [ ] **Step 7: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi
git commit -m "Add BindingLayoutItem.PushConstants and CommandList debug marker bindings"
```

---

### Task 2: Aftermath availability flag and the unsafe page-fault helper

This task adds the build-conditional `enableAftermath` field, the `AFTERMATH_AVAILABLE` flag Python needs to branch on, and the one function whose entire purpose is to corrupt GPU state. It is separated from Task 1 because the Vulkan branch carries a real compile risk (see Step 3).

**Files:**
- Modify: `src/cpp/_pydonut.cpp:71` (add the Vulkan header include)
- Modify: `src/cpp/_pydonut.cpp:1681` (add `DestroyBufferMemory_UnsafeForCrashTesting`)
- Modify: `src/cpp/_pydonut.cpp:2968` (add `enableAftermath`)
- Modify: `src/cpp/_pydonut.cpp` (add `AFTERMATH_AVAILABLE` module attribute)
- Modify: `src/pydonut/_pydonut.pyi:279` (add function + flag stubs)
- Modify: `src/pydonut/_pydonut.pyi:1485` (add `enableAftermath` field stub)
- Modify: `src/pydonut/__init__.py:166` and `:332` (export both module-level names)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `pyd.AFTERMATH_AVAILABLE: bool`; `pyd.DestroyBufferMemory_UnsafeForCrashTesting(device: Device, buffer: Buffer) -> None`; `DeviceCreationParameters.enableAftermath: bool` (present **only** when `AFTERMATH_AVAILABLE` is `True`). Task 5 consumes all three.

- [ ] **Step 1: Add the Vulkan header include**

In `src/cpp/_pydonut.cpp`, find this exact block (currently lines 68-71):

```cpp
#ifdef NVRHI_WITH_DX12
#include <wrl.h>
#include <d3dx12/d3dx12.h>
#endif
```

Add immediately after it:

```cpp
#if DONUT_WITH_VULKAN
// Plain C Vulkan API only (for vkFreeMemory in DestroyBufferMemory_UnsafeForCrashTesting).
// Deliberately NOT vulkan.hpp: the aftermath.cpp sample uses it with
// VULKAN_HPP_DISPATCH_LOADER_DYNAMIC, whose dispatcher-storage macro would have to be
// satisfied in this translation unit for no benefit here.
#include <vulkan/vulkan.h>
#endif
```

- [ ] **Step 2: Add the unsafe helper to `_pydonut.cpp`**

In `src/cpp/_pydonut.cpp`, find this exact line (currently line 1681, immediately after the `endMarker` binding added in Task 1):

```cpp
    m.def("ClearColorAttachment", &nvrhi::utils::ClearColorAttachment,
```

Add immediately **before** it:

```cpp
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
            VkDevice vkDevice = static_cast<VkDevice>(device->getNativeObject(nvrhi::ObjectTypes::VK_Device).pointer);
            VkDeviceMemory memory = static_cast<VkDeviceMemory>(buffer->getNativeObject(nvrhi::ObjectTypes::VK_DeviceMemory).pointer);
            vkFreeMemory(vkDevice, memory, nullptr);
            return;
        }
#endif
        throw std::runtime_error(
            "DestroyBufferMemory_UnsafeForCrashTesting: unsupported graphics API. D3D11 does not "
            "page-fault under these conditions, and D3D12/Vulkan must be compiled in.");
    }, py::arg("device"), py::arg("buffer"));

```

- [ ] **Step 3: Build and resolve the two known compile risks**

Run: `uv sync --reinstall-package pydonut`

Two failures are plausible here. Both have a known fix — do not improvise past them:

1. **`vulkan/vulkan.h: No such file or directory`.** The include path did not propagate. Fix by adding an explicit link in `CMakeLists.txt`, immediately after the `target_compile_definitions(_pydonut PRIVATE NVRHI_WITH_DX12=1)` block that ends at line 171:

   ```cmake
   if (DONUT_WITH_VULKAN)
       target_link_libraries(_pydonut PRIVATE Vulkan-Headers)
   endif()
   ```

2. **`static_cast` from `void*` to `VkDeviceMemory` fails.** On 32-bit targets Vulkan non-dispatchable handles are `uint64_t`, not pointers. This project is 64-bit only (`GFSDK_Aftermath_Lib.x64`, `lib/x64` paths, `d3dx12`), so if this fires, use the `Object` union's integer member instead: replace `.pointer` with `.integer` for the `VkDeviceMemory` line only and cast through `reinterpret_cast<VkDeviceMemory>`.

Expected once resolved: build succeeds.

- [ ] **Step 4: Add the `enableAftermath` binding**

In `src/cpp/_pydonut.cpp`, find this exact line (currently line 2955):

```cpp
    deviceCreationParameters.def_readwrite("enableJoystickInput", &donut::app::DeviceCreationParameters::enableJoystickInput);
```

Add immediately after it:

```cpp
#if DONUT_WITH_AFTERMATH
    // Only exists in builds configured with -DPYDONUT_WITH_AFTERMATH=ON: the underlying field
    // is itself inside #if DONUT_WITH_AFTERMATH (DeviceManager.h:104-106), so binding it
    // unconditionally would not compile. Python must gate on pyd.AFTERMATH_AVAILABLE.
    deviceCreationParameters.def_readwrite("enableAftermath", &donut::app::DeviceCreationParameters::enableAftermath);
#endif
```

- [ ] **Step 5: Add the `AFTERMATH_AVAILABLE` module attribute**

In `src/cpp/_pydonut.cpp`, find the same `ClearColorAttachment` line used in Step 2 and add this immediately before the block you added there:

```cpp
    // True only in builds configured with -DPYDONUT_WITH_AFTERMATH=ON. When False,
    // DeviceCreationParameters has no enableAftermath attribute at all and no crash dumps are
    // written -- the crashes still happen, they just go uncaptured.
    m.attr("AFTERMATH_AVAILABLE") = py::bool_(static_cast<bool>(DONUT_WITH_AFTERMATH));

```

- [ ] **Step 6: Add the `.pyi` stubs**

In `src/pydonut/_pydonut.pyi`, find this exact line (currently line 279):

```python
def ClearColorAttachment(commandList: CommandList, framebuffer: Framebuffer, attachmentIndex: int, color: Color) -> None: ...
```

Add immediately **before** it:

```python
# True only in builds configured with -DPYDONUT_WITH_AFTERMATH=ON. When False,
# DeviceCreationParameters has no enableAftermath attribute and no crash dumps are written.
AFTERMATH_AVAILABLE: bool

# DELIBERATELY UNSAFE -- crash testing only. Destroys the native API memory backing `buffer`
# while the GPU may still be reading it, so the next draw page-faults. The device cannot be
# recovered afterwards. Raises RuntimeError on D3D11, which does not fault this way.
def DestroyBufferMemory_UnsafeForCrashTesting(device: Device, buffer: Buffer) -> None: ...
```

Then find this exact line (currently line 1485):

```python
    enableJoystickInput: bool
```

Add immediately after it:

```python
    # Present ONLY when AFTERMATH_AVAILABLE is True (built with -DPYDONUT_WITH_AFTERMATH=ON).
    # Guard every access on that flag; this attribute does not exist in a default build.
    enableAftermath: bool
```

- [ ] **Step 7: Export both names from `__init__.py`**

In `src/pydonut/__init__.py`, find this exact line (currently line 166):

```python
from pydonut._pydonut import ClearColorAttachment
```

Add immediately **before** it:

```python
from pydonut._pydonut import AFTERMATH_AVAILABLE
from pydonut._pydonut import DestroyBufferMemory_UnsafeForCrashTesting
```

Then find this exact line (currently line 332):

```python
    'ClearColorAttachment',
```

Add immediately **before** it:

```python
    'AFTERMATH_AVAILABLE',
    'DestroyBufferMemory_UnsafeForCrashTesting',
```

- [ ] **Step 8: Rebuild and verify the default (option-off) build**

This is the case the `#if` guards exist for, and it must be checked explicitly rather than assumed.

Run: `uv sync --reinstall-package pydonut`

Then:

```sh
uv run python -c "import src.pydonut as pyd; print(pyd.AFTERMATH_AVAILABLE); print(hasattr(pyd.DeviceCreationParameters(), 'enableAftermath')); print(pyd.DestroyBufferMemory_UnsafeForCrashTesting)"
```

Expected: `False`, then `False`, then a builtin-function repr. If the first two print `True`, the option leaked on somehow — stop and investigate rather than continuing.

- [ ] **Step 9: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py CMakeLists.txt
git commit -m "Add Aftermath availability flag and unsafe page-fault crash-testing binding"
```

---

### Task 3: `PYDONUT_WITH_AFTERMATH` build option

**Files:**
- Modify: `CMakeLists.txt:126` (set `DONUT_WITH_AFTERMATH` before `add_subdirectory(extern/donut)`)
- Modify: `CMakeLists.txt:231` (DLL copy + install, after the DXC block)

**Interfaces:**
- Consumes: the `#if DONUT_WITH_AFTERMATH` guards added in Task 2.
- Produces: a build in which `pyd.AFTERMATH_AVAILABLE` is `True` and `GFSDK_Aftermath_Lib.x64.dll` sits next to `_pydonut`.

- [ ] **Step 1: Add the option and force donut's flag before the subdirectory is added**

In `CMakeLists.txt`, find this exact line (currently line 126):

```cmake
add_subdirectory(extern/donut)
```

Add immediately **before** it:

```cmake
# Opt-in NSight Aftermath GPU crash dumps. OFF by default: turning it on makes donut force
# NVRHI_WITH_AFTERMATH (extern/donut/CMakeLists.txt:101), which pulls in
# extern/donut/nvrhi/cmake/FetchAftermath.cmake -- a configure-time FetchContent download of
# the NSight Aftermath SDK from developer.nvidia.com. Must be set before add_subdirectory()
# below, or donut caches the OFF value.
option(PYDONUT_WITH_AFTERMATH "Enable NSight Aftermath GPU crash dumps (downloads the SDK at configure time)" OFF)
if (PYDONUT_WITH_AFTERMATH)
    set(DONUT_WITH_AFTERMATH ON CACHE BOOL "" FORCE)
endif()
```

- [ ] **Step 2: Copy the Aftermath runtime DLL next to the module**

In `CMakeLists.txt`, find this exact line (currently line 231, the last line of the DXC-found branch):

```cmake
    install(FILES ${DXC_RUNTIME_FILES} DESTINATION ${SKBUILD_PROJECT_NAME})
```

Find the `endif()` / `else()` that closes that `if (DXC_INCLUDE_DIR AND ...)` block, and add this **after** the whole block ends:

```cmake
# The Aftermath SDK's runtime DLL has to sit next to _pydonut, both in a dev build tree and in
# an installed wheel -- same two-step (POST_BUILD copy + install) the DXC runtime uses above.
# The `aftermath` imported target is created by donut's FetchAftermath.cmake.
if (PYDONUT_WITH_AFTERMATH AND TARGET aftermath)
    get_target_property(AFTERMATH_RUNTIME aftermath IMPORTED_LOCATION)
    add_custom_command(TARGET _pydonut POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different "${AFTERMATH_RUNTIME}" "$<TARGET_FILE_DIR:_pydonut>"
        COMMENT "pydonut: copying Aftermath runtime library next to _pydonut")
    install(FILES "${AFTERMATH_RUNTIME}" DESTINATION ${SKBUILD_PROJECT_NAME})
    message(STATUS "pydonut: Aftermath enabled (${AFTERMATH_RUNTIME})")
endif()
```

- [ ] **Step 3: Build with the option on**

Run: `SKBUILD_CMAKE_DEFINE=PYDONUT_WITH_AFTERMATH=ON uv sync --reinstall-package pydonut`

Expected: configure output shows donut fetching the Aftermath SDK and the `pydonut: Aftermath enabled (...)` status line; the build succeeds. This step needs network access. If the download fails, report the failure rather than falling back to the OFF build silently — a silent fallback would make every later verification meaningless.

- [ ] **Step 4: Verify the flag and the DLL**

Run:

```sh
uv run python -c "import src.pydonut as pyd; print(pyd.AFTERMATH_AVAILABLE); p = pyd.DeviceCreationParameters(); p.enableAftermath = True; print(p.enableAftermath)"
```

Expected: `True`, then `True`.

Then confirm the DLL landed (adjust the glob if the build tag differs):

```sh
ls build/*/GFSDK_Aftermath_Lib.x64.dll .venv/Lib/site-packages/pydonut/GFSDK_Aftermath_Lib.x64.dll
```

Expected: at least the site-packages copy exists.

- [ ] **Step 5: Re-verify the default build still works**

Run: `uv sync --reinstall-package pydonut` (no env var), then:

```sh
uv run python -c "import src.pydonut as pyd; print(pyd.AFTERMATH_AVAILABLE)"
```

Expected: `False`. Then rebuild with the option ON again for the remaining tasks.

- [ ] **Step 6: Commit**

```bash
git add CMakeLists.txt
git commit -m "Add opt-in PYDONUT_WITH_AFTERMATH build option"
```

---

### Task 4: `shaders/aftermath/shaders.hlsl`

**Files:**
- Create: `shaders/aftermath/shaders.hlsl`

**Interfaces:**
- Produces: entry points `main_vs` and `main_ps`; a push-constant `Constants { uint crashType; }` at `b0`; `RWStructuredBuffer<float> g_buffer` at `u0`. Task 5 consumes all of these.

- [ ] **Step 1: Create the shader file**

Create `shaders/aftermath/shaders.hlsl` with exactly this content. Note it keeps the original NVIDIA copyright header (this is ported NVIDIA sample code, matching how `shaders/basic_triangle/shaders.hlsl` and the other ported shaders in this repo are headed), and that the SPIR-V guard is `__spirv__`, **not** the original's `SPIRV` — `pyd.CompileShader` passes `-spirv` but never defines `SPIRV` and takes no `defines` argument, whereas DXC predefines `__spirv__` itself whenever it targets SPIR-V.

```hlsl
/*
* Copyright (c) 2014-2021, NVIDIA CORPORATION. All rights reserved.
*
* Permission is hereby granted, free of charge, to any person obtaining a
* copy of this software and associated documentation files (the "Software"),
* to deal in the Software without restriction, including without limitation
* the rights to use, copy, modify, merge, publish, distribute, sublicense,
* and/or sell copies of the Software, and to permit persons to whom the
* Software is furnished to do so, subject to the following conditions:
*
* The above copyright notice and this permission notice shall be included in
* all copies or substantial portions of the Software.
*
* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
* THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
* FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
* DEALINGS IN THE SOFTWARE.
*/

static const float2 g_positions[] = {
	float2(-0.5, -0.5),
	float2(0, 0.5),
	float2(0.5, -0.5)
};

static const float3 g_colors[] = {
	float3(1, 0, 0),
	float3(0, 1, 0),
	float3(0, 0, 1)	
};

struct Constants
{
    uint crashType;
};

// __spirv__ (DXC's own predefine when targeting SPIR-V), not the original sample's SPIRV:
// pyd.CompileShader passes -spirv but defines no SPIRV macro and exposes no `defines`
// parameter, so the original guard would silently drop the push-constant decoration on Vulkan.
#ifdef __spirv__

[[vk::push_constant]] ConstantBuffer<Constants> g_constants;

#else

cbuffer g_constants : register(b0)
{
    Constants g_constants;
};
#endif

RWStructuredBuffer<float> g_buffer : register(u0);

void main_vs(
	uint i_vertexId : SV_VertexID,
	out float4 o_pos : SV_Position,
	out float3 o_color : COLOR
)
{
	o_pos = float4(g_positions[i_vertexId], 0, 1);
	o_color = g_colors[i_vertexId];

	// infinite loop to cause a timeout crash
    if (g_constants.crashType == 1)
    {
        float test = 0.99f;
        while (test < 1.f)
        {
            test *= test;
        }
		// execution will never reach this line, but it is necessary to keep the compiler from optimizing out the loop
		// since otherwise the loop result is never used anywhere
        o_color.r *= test;
    }

	// for page fault crash, if g_buffer is destroyed while this shader is executing, this load should fail
	o_color.r += g_buffer[i_vertexId];
}

void main_ps(
	in float4 i_pos : SV_Position,
	in float3 i_color : COLOR,
	out float4 o_color : SV_Target0
)
{
	o_color = float4(i_color, 1);
}
```

- [ ] **Step 2: Verify both entry points compile for both backends**

Run:

```sh
uv run python -c "
import src.pydonut as pyd
from pathlib import Path
src = Path('shaders/aftermath/shaders.hlsl').read_text(encoding='utf-8')
for api in (pyd.GraphicsAPI.D3D12, pyd.GraphicsAPI.Vulkan):  # NB: Vulkan, not VULKAN
    for entry, st in (('main_vs', pyd.ShaderType.Vertex), ('main_ps', pyd.ShaderType.Pixel)):
        print(api, entry, len(pyd.CompileShader(src, entry, st, api, sourceName='shaders.hlsl')))
"
```

Expected: four lines, each ending in a non-zero byte count. A `RuntimeError` here means the shader is wrong — fix it before moving on, since Task 5 cannot run without it.

- [ ] **Step 3: Commit**

```bash
git add shaders/aftermath/shaders.hlsl
git commit -m "Add aftermath example shader"
```

---

### Task 5: `aftermath.py`

**Files:**
- Create: `aftermath.py`

**Interfaces:**
- Consumes: `pyd.BindingLayoutItem.PushConstants`, `commandList.beginMarker`/`endMarker` (Task 1); `pyd.AFTERMATH_AVAILABLE`, `pyd.DestroyBufferMemory_UnsafeForCrashTesting`, `DeviceCreationParameters.enableAftermath` (Task 2); `shaders/aftermath/shaders.hlsl` (Task 4).
- Produces: the runnable example. Nothing consumes it.

- [ ] **Step 1: Create `aftermath.py`**

Create `aftermath.py` with exactly this content:

```python
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

"""NSight Aftermath GPU crash dump example (port of Donut's aftermath.cpp).

Draws one triangle and offers two buttons that deliberately crash the GPU:

  * "Trigger timeout"    -- the vertex shader spins forever, tripping Windows' TDR
                            watchdog (2s by default), which resets the display driver.
  * "Trigger page fault" -- the buffer's native API memory is destroyed while a shader
                            is reading it.

Either one resets the display driver: the screen blanks, this process dies, and other
GPU applications may die with it. Nothing here is recoverable by design.

Crash dumps are only written when the module was built with -DPYDONUT_WITH_AFTERMATH=ON
(check pyd.AFTERMATH_AVAILABLE). Without it the crashes still happen, just uncaptured.

WHERE THE DUMPS GO: donut writes them to GetDirectoryWithExecutable() / "crash_<timestamp>"
(AftermathCrashDump.cpp:206). Under PyDonut the executable is the interpreter, so dumps
land next to python.exe in the venv's Scripts/ directory -- NOT in the project root. The
absolute path is logged when the dump is written.
"""

from __future__ import annotations

if __name__ == "__main__":
    import struct
    import sys
    from enum import IntEnum
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Aftermath"
    folder = Path(__file__).resolve().parent

    # ImGuiWindowFlags_AlwaysAutoResize -- same constant work_graphs.py and rt_particles.py
    # already define locally rather than binding the whole ImGuiWindowFlags enum.
    _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE = 64

    class CrashType(IntEnum):
        """Values must match the shader's g_constants.crashType comparisons."""

        NONE = 0
        TIMEOUT = 1
        PAGEFAULT = 2

    class UIData:
        """Shared by reference between AftermathSample and UIRenderer.

        Replaces the C++ original's UIRenderer-holds-AftermathSample& plus SetCrashType
        setter, matching how work_graphs.py and rt_particles.py share their UIData.
        """

        def __init__(self: UIData) -> None:
            self.crashType: CrashType = CrashType.NONE

    class AftermathSample(pyd.IRenderPass):
        def __init__(self: AftermathSample, deviceManager: pyd.DeviceManager, ui: UIData) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            self.vertexShader: pyd.Shader | None = None
            self.pixelShader: pyd.Shader | None = None
            self.pipeline: pyd.GraphicsPipeline | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.commandList: pyd.CommandList | None = None
            self.buffer: pyd.Buffer | None = None
            self.waitingForCrash = False

        def Init(self: AftermathSample) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "aftermath" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                vsBytecode = pyd.CompileShader(
                    source, "main_vs", pyd.ShaderType.Vertex, api, sourceName=shaderPath.name
                )
                psBytecode = pyd.CompileShader(
                    source, "main_ps", pyd.ShaderType.Pixel, api, sourceName=shaderPath.name
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.vertexShader = device.createShader(vsBytecode, "main_vs", pyd.ShaderType.Vertex)
            self.pixelShader = device.createShader(psBytecode, "main_ps", pyd.ShaderType.Pixel)

            if not self.vertexShader or not self.pixelShader:
                return False

            self.commandList = device.createCommandList()

            bufDesc = pyd.BufferDesc()
            bufDesc.byteSize = 1024
            bufDesc.canHaveUAVs = True
            bufDesc.debugName = "Aftermath test buffer"
            bufDesc.format = pyd.Format.R32_FLOAT
            bufDesc.initialState = pyd.ResourceStates.UnorderedAccess
            bufDesc.keepInitialState = True
            bufDesc.structStride = 4  # sizeof(float)
            self.buffer = device.createBuffer(bufDesc)

            self.waitingForCrash = False
            return True

        def BackBufferResizing(self: AftermathSample) -> None:
            self.pipeline = None

        def Animate(self: AftermathSample, elapsedTimeSeconds: float) -> None:
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def Render(self: AftermathSample, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.buffer is not None

            if not self.pipeline:
                bindingLayoutDesc = pyd.BindingLayoutDesc()
                bindingLayoutDesc.visibility = pyd.ShaderType.All
                bindingLayoutDesc.bindings = [
                    pyd.BindingLayoutItem.PushConstants(0, 4),
                    pyd.BindingLayoutItem.StructuredBuffer_UAV(0),
                ]
                self.bindingLayout = device.createBindingLayout(bindingLayoutDesc)

                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.PushConstants(0, 4),
                    pyd.BindingSetItem.StructuredBuffer_UAV(0, self.buffer),
                ]
                self.bindingSet = device.createBindingSet(bindingSetDesc, self.bindingLayout)

                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.vertexShader
                psoDesc.PS = self.pixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.renderState.depthStencilState.depthTestEnable = False
                # NOT psoDesc.bindingLayouts = [...] -- GraphicsPipelineDesc exposes no such
                # list property in this binding, only addBindingLayout (_pydonut.pyi:452).
                psoDesc.addBindingLayout(self.bindingLayout)

                self.pipeline = device.createGraphicsPipeline(
                    psoDesc, framebuffer.getFramebufferInfo()
                )

            self.commandList.open()
            self.commandList.beginMarker("Frame")

            # One way to cause a page fault is to destroy a resource that is in use. Destroying
            # the nvrhi resource would crash on the CPU before the GPU ever faults, so the
            # native graphics API object is destroyed directly instead.
            if self.ui.crashType == CrashType.PAGEFAULT and not self.waitingForCrash:
                pyd.DestroyBufferMemory_UnsafeForCrashTesting(device, self.buffer)
                self.commandList.setEnableAutomaticBarriers(False)
                self.waitingForCrash = True

            self.commandList.beginMarker("Clear")
            pyd.ClearColorAttachment(self.commandList, framebuffer, 0, pyd.Color(0.0))
            self.commandList.endMarker()

            self.commandList.beginMarker("Draw Triangle")
            state = pyd.GraphicsState()
            state.pipeline = self.pipeline
            state.framebuffer = framebuffer
            state.viewport.addViewportAndScissorRect(
                framebuffer.getFramebufferInfo().getViewport()
            )
            state.addBindingSet(self.bindingSet)

            self.commandList.setGraphicsState(state)

            # The C++ original passes &m_CrashType with sizeof(uint32_t); the binding takes a
            # buffer object, so the enum is packed explicitly as one little-endian uint32.
            self.commandList.setPushConstants(struct.pack("<I", int(self.ui.crashType)))

            args = pyd.DrawArguments()
            args.vertexCount = 3
            self.commandList.draw(args)
            self.commandList.endMarker()

            self.commandList.endMarker()
            self.commandList.close()

            device.executeCommandList(self.commandList)

    class UIRenderer(pyd.ImGui_Renderer):
        def __init__(
            self: UIRenderer, deviceManager: pyd.DeviceManager, ui: UIData, api: pyd.GraphicsAPI
        ) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            self.api = api
            pyd.ImGui.DisableIniFile()

        def buildUI(self: UIRenderer) -> None:
            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Controls", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            if pyd.ImGui.Button("Trigger timeout"):
                self.ui.crashType = CrashType.TIMEOUT

            # d3d11 does not page fault in these conditions, so short circuit showing the
            # button in d3d11
            if self.api != pyd.GraphicsAPI.D3D11 and pyd.ImGui.Button("Trigger page fault"):
                self.ui.crashType = CrashType.PAGEFAULT

            if not pyd.AFTERMATH_AVAILABLE:
                pyd.ImGui.Separator()
                pyd.ImGui.Text("Crash dumps DISABLED in this build.")
                pyd.ImGui.Text("The crashes will still reset the GPU.")

            pyd.ImGui.End()

    is_debug = "-debug" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        # NOTE: unlike every other example in this repo, enableDebugRuntime is deliberately
        # NOT set here even under -debug -- Aftermath is incompatible with the D3D debug
        # layer (aftermath.cpp:253-254). Only the NVRHI validation layer is enabled.
        print("Debug mode is enabled (D3D debug runtime stays off for Aftermath).")
        deviceParams.enableNvrhiValidationLayer = True

    if pyd.AFTERMATH_AVAILABLE:
        deviceParams.enableAftermath = True
    else:
        print(
            "WARNING: this build has no Aftermath support, so no crash dump will be written.\n"
            "         The crash buttons still reset the GPU. To enable dumps, rebuild with:\n"
            "         SKBUILD_CMAKE_DEFINE=PYDONUT_WITH_AFTERMATH=ON "
            "uv sync --reinstall-package pydonut"
        )

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    device = deviceManager.GetDevice()

    # Framework shaders (needed only so UIRenderer.Init() can load ImGui's own vertex/pixel
    # shaders) -- same RootFileSystem/ShaderFactory mount convention work_graphs.py uses.
    rootFS = pyd.RootFileSystem()
    frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
    rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
    uiShaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))

    uiData = UIData()
    example = AftermathSample(deviceManager, uiData)
    gui = UIRenderer(deviceManager, uiData, api)

    if example.Init() and gui.Init(uiShaderFactory):
        deviceManager.AddRenderPassToBack(example)
        deviceManager.AddRenderPassToBack(gui)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(gui)
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")
```

- [ ] **Step 2: Run it**

Run: `uv run python aftermath.py`

Expected: a window titled "PyDonut Aftermath" showing a red/green/blue triangle on black, with a "Controls" window at the top-left containing **two** buttons ("Trigger timeout", "Trigger page fault") and no "Crash dumps DISABLED" notice (assuming the Task 3 option-on build is current).

**Do not press either button.** Close the window normally; the console should print `Done.`

- [ ] **Step 3: Fix whatever the run surfaced**

Likely failure points, in rough order of probability:

- Framework shaders missing at `bin/shaders/framework/<api>` → `gui.Init()` returns `False` and the window never appears. Confirm that directory exists; every other ImGui example depends on it identically.
- Vulkan push constants: this is the first example in the repo whose HLSL actually gets the `[[vk::push_constant]]` decoration applied (see Task 4's `__spirv__` note). If the Vulkan run specifically fails validation on the push-constant binding while D3D12 is fine, that is the suspect — report it rather than reverting the guard, since reverting reintroduces the silent bug.

All other API names used in this file were verified against `src/pydonut/_pydonut.pyi` while writing this plan: `Format.R32_FLOAT` (line 69), `ResourceStates.UnorderedAccess` (208), `ShaderType.All` (132), `GraphicsState.addBindingSet` (459), `DeviceManager.GetDevice` (1529), and `createGraphicsPipeline(desc, framebufferInfo)` (851 — there is only this one overload; it does **not** accept a `Framebuffer`).

- [ ] **Step 4: Commit**

```bash
git add aftermath.py
git commit -m "Add aftermath.py example"
```

---

### Task 6: README documentation

**Files:**
- Modify: `README.md` (new subsection after the existing DXC subsection, which starts at line 107)

**Interfaces:**
- Consumes: the build option from Task 3.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the documentation subsection**

In `README.md`, find the "### 4. Enabling `pyd.CompileShader` (optional, both platforms)" subsection (starts at line 107) and add this new subsection immediately after it, before the `## Running the example` heading.

The block below is fenced with **four** backticks because its own content contains a three-backtick `sh` block — insert only the inner content into the README, not the outer fence:

````markdown
### 5. Enabling NSight Aftermath crash dumps (optional, Windows & Linux)

`aftermath.py` deliberately crashes the GPU to demonstrate NSight Aftermath crash dumps. The
crashes work in any build, but capturing a dump needs the Aftermath SDK compiled in:

```sh
SKBUILD_CMAKE_DEFINE=PYDONUT_WITH_AFTERMATH=ON uv sync --reinstall-package pydonut
```

`--reinstall-package pydonut` is required: an environment variable changes none of the cache-key
files listed in `pyproject.toml`, so uv would otherwise reuse the cached wheel. The option
downloads the NSight Aftermath SDK from `developer.nvidia.com` at configure time, so this build
needs network access.

In such a build `pyd.AFTERMATH_AVAILABLE` is `True` and `DeviceCreationParameters` gains an
`enableAftermath` field. **In a default build that field does not exist at all** — always guard
access on `pyd.AFTERMATH_AVAILABLE`.

Dumps are written to `<directory containing the running executable>/crash_<timestamp>/`. Under
PyDonut the executable is the Python interpreter, so they land next to `python.exe` in
`.venv/Scripts/`, not in the project directory. The absolute path is logged when the dump is
written.

> Warning: triggering either crash resets the display driver. The screen blanks, the example
> dies, and other GPU applications may die with it.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Document the PYDONUT_WITH_AFTERMATH build option"
```

---

## Final verification

Run through the spec's Verification section end to end:

1. `SKBUILD_CMAKE_DEFINE=PYDONUT_WITH_AFTERMATH=ON uv sync --reinstall-package pydonut` succeeds, SDK fetches, DLL lands next to `_pydonut`.
2. A default `uv sync --reinstall-package pydonut` build still compiles (Task 3, Step 5).
3. `pyd.AFTERMATH_AVAILABLE` is `True` on the option-on build.
4. `uv run python aftermath.py` renders the triangle with both buttons present.
5. **Stop.** Report to the user that triggering the crashes is theirs to do.
