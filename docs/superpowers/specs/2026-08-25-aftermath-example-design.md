# Aftermath example (`aftermath.py`) — design

## Goal

Port `E:\Gits\Donut-Samples\examples\aftermath\aftermath.cpp` (and its `shaders.hlsl`) to
`aftermath.py`, adding the four missing native bindings it needs, and wire up an opt-in
`PYDONUT_WITH_AFTERMATH` build option so the example produces real NSight Aftermath GPU crash
dumps.

The sample draws one 3-vertex triangle whose vertex shader branches on a push-constant
`crashType`, and offers an ImGui "Controls" window with two buttons that deliberately crash the
GPU:

- **Trigger timeout** — sets `crashType = 1`, making the vertex shader spin in an infinite loop
  until Windows' TDR watchdog (2s by default) resets the display driver.
- **Trigger page fault** — reaches past NVRHI to the buffer's *native* API object and destroys
  its memory while a shader is reading it. It must bypass NVRHI: releasing the NVRHI object
  would fault on the CPU first, before the GPU ever page-faults.

NVRHI debug markers (`Frame` → `Clear` / `Draw Triangle`) bracket the work so the resulting dump
names the marker scope that died — that resolution is the whole point of the sample, and is why
`beginMarker`/`endMarker` are a required binding rather than cosmetic.

Scope decisions taken during brainstorming:

- **Full integration**, including the SDK fetch and real `.nv-gpudmp` output — not a
  crash-repro-only port.
- **Both** crash types, so the page-fault path needs native-object access from Python.
- The unsafe native access is exposed as **one narrow, named-for-danger helper**, not a general
  `getNativeObject` + raw-pointer surface.

## The `#if DONUT_WITH_AFTERMATH` constraint

`DeviceCreationParameters::enableAftermath` is **not** an unconditional field. It lives inside
`#if DONUT_WITH_AFTERMATH` (`extern/donut/include/donut/app/DeviceManager.h:104-106`), as does
`DeviceManager::m_AftermathCrashDumper` (same header, ~line 437). Two consequences drive the
rest of this design:

1. The `enableAftermath` binding **must** be `#if DONUT_WITH_AFTERMATH`-guarded, or
   `_pydonut.cpp` fails to compile in the default (option-off) build.
2. Therefore, in a default build `pyd.DeviceCreationParameters` has **no `enableAftermath`
   attribute at all** — not a present-but-inert one.

Point 2 is why this design adds a module-level `pyd.AFTERMATH_AVAILABLE` flag. Without it, a
user on a default build presses "Trigger timeout", TDRs their machine, and finds no dump and no
explanation for why. With it, `aftermath.py` warns at startup and in the ImGui window.

No extra CMake plumbing is needed to make the `#if` work: `donut-app.cmake:109` already declares
`target_compile_definitions(donut_app PUBLIC DONUT_WITH_AFTERMATH=$<BOOL:${DONUT_WITH_AFTERMATH}>)`,
and `_pydonut` links `donut_app`.

## New native bindings (`src/cpp/_pydonut.cpp`)

- **`BindingLayoutItem.PushConstants(slot: int, byteSize: int) -> BindingLayoutItem`** — a
  `def_static` on the `BindingLayoutItem` class (`_pydonut.cpp:1104-1114`), filling the gap next
  to the already-bound `BindingSetItem.PushConstants` (`_pydonut.cpp:1185`). Same
  static-factory-only pattern the surrounding comment describes.

- **`CommandList.beginMarker(name: str) -> None` / `CommandList.endMarker() -> None`** — thin
  wrappers over `nvrhi::ICommandList::beginMarker`/`endMarker`, added beside the existing
  `beginTimerQuery`/`endTimerQuery` pair (`_pydonut.cpp:1678-1679`). Aftermath stores markers as
  hashed 64-bit values and resolves them back to text via
  `AftermathCrashDump::ResolveMarker`, so the marker strings are what make a dump readable.

- **`DeviceCreationParameters.enableAftermath: bool`** — one `def_readwrite` appended to the
  block ending `_pydonut.cpp:2968`, wrapped in `#if DONUT_WITH_AFTERMATH`.

- **`m.attr("AFTERMATH_AVAILABLE")`** — a module-level `bool` set from
  `DONUT_WITH_AFTERMATH`, so Python can branch on whether dumps are possible. Follows the
  existing convention of feature-conditional module attributes (cf. `pyd.CompileShader` being
  absent without DXC, `PYDONUT_HAVE_DXC`).

- **`DestroyBufferMemory_UnsafeForCrashTesting(device: Device, buffer: Buffer) -> None`** — a
  free function on the module. Switches on `device->getGraphicsAPI()`:
  - `D3D12` (under `#ifdef NVRHI_WITH_DX12`): `buffer->getNativeObject(ObjectTypes::D3D12_Resource)`
    then `->Release()`, matching `aftermath.cpp:164-166`.
  - `VULKAN` (under `#if DONUT_WITH_VULKAN`): free the `VK_DeviceMemory` behind the buffer via
    the `VK_Device` from `device->getNativeObject(...)`, matching `aftermath.cpp:171-173`.
  - `D3D11` (or an API compiled out): raise `RuntimeError` with a message explaining that D3D11
    does not page-fault under these conditions — the same fact `aftermath.cpp:231-232` encodes
    by hiding the button.

  The two guard macros are **not** spelled symmetrically, and must match what this file already
  does: D3D12 code uses `#ifdef NVRHI_WITH_DX12` (`_pydonut.cpp:68`, `1448`, `1589`), set for
  this target at `CMakeLists.txt:170`; Vulkan code uses `#if DONUT_WITH_VULKAN`
  (`_pydonut.cpp:2925`, `2965`), which arrives transitively as a PUBLIC compile definition from
  `donut-engine.cmake:59`. There is no `NVRHI_WITH_VULKAN` compile definition on `_pydonut`.

  The existing D3D12 native-object call sites (`_pydonut.cpp:1462`, `1476`, `1599`, `1608`) are
  the precedent for the guarding and `getNativeObject` usage. The name is deliberately alarming:
  this function's only legitimate use is crash testing, and Python never receives a raw pointer.

  **Implementation risk to settle during planning:** `_pydonut.cpp` currently includes no Vulkan
  headers, so the Vulkan branch needs one (`<vulkan/vulkan.h>` or nvrhi's Vulkan header).
  `donut-app.cmake:102` links `Vulkan-Headers` into `donut_app` with the plain signature, so the
  include directories should propagate to `_pydonut`; if they do not, an explicit
  `target_link_libraries(_pydonut PRIVATE Vulkan-Headers)` is the fallback. Unlike the sample,
  the binding should use the plain C API rather than `vulkan.hpp`, to avoid pulling
  `VULKAN_HPP_DISPATCH_LOADER_DYNAMIC` and its storage requirements into this translation unit.

All of the above are declared in `src/pydonut/_pydonut.pyi` (`CommandList` methods near
`setEnableAutomaticBarriers` at line 830; `DeviceCreationParameters.enableAftermath` near
`enableJoystickInput` at line 1485) and re-exported from `src/pydonut/__init__.py` where they
are free functions or module attributes (`DestroyBufferMemory_UnsafeForCrashTesting`,
`AFTERMATH_AVAILABLE`); `CommandList`, `BindingLayoutItem` and `DeviceCreationParameters` are
already exported as classes.

Because `enableAftermath` and `AFTERMATH_AVAILABLE` are build-conditional, the `.pyi` comments
must state that `enableAftermath` is absent unless the module was built with
`PYDONUT_WITH_AFTERMATH=ON`, so the type stub does not promise an attribute that may not exist.

## Build option (`CMakeLists.txt`)

Modelled on the existing Agility SDK block (`CMakeLists.txt:128-137`) and DXC runtime-copy block
(`CMakeLists.txt:212-231`):

- `option(PYDONUT_WITH_AFTERMATH "Enable NSight Aftermath GPU crash dumps" OFF)` — **default
  OFF**, so the normal build is unchanged and needs no network access.
- When ON, `set(DONUT_WITH_AFTERMATH ON CACHE BOOL "" FORCE)` **before**
  `add_subdirectory(extern/donut)` at `CMakeLists.txt:126`. Donut then forces
  `NVRHI_WITH_AFTERMATH` (`extern/donut/CMakeLists.txt:101`), which pulls in
  `extern/donut/nvrhi/cmake/FetchAftermath.cmake` (`nvrhi/CMakeLists.txt:206-208`) — a
  configure-time `FetchContent` download of the NSight Aftermath SDK from `developer.nvidia.com`
  (2025.1.0, MD5-pinned), producing an imported `aftermath` target.
- A `POST_BUILD copy_if_different` of `GFSDK_Aftermath_Lib.x64.dll` (read from the `aftermath`
  target's `IMPORTED_LOCATION`) into `$<TARGET_FILE_DIR:_pydonut>`, plus a matching
  `install(FILES ... DESTINATION ${SKBUILD_PROJECT_NAME})` — exactly the two-step the DXC
  runtime already uses at `CMakeLists.txt:227-231`, so the DLL is present both in a dev build
  tree and in an installed wheel.

The option is only meaningful on builds that have a supported backend; it is not gated on
`NVRHI_WITH_DX12` because Aftermath supports Vulkan as well.

## `shaders/aftermath/shaders.hlsl`

Ported from the sample's `shaders.hlsl` with one deliberate change.

The original selects the Vulkan push-constant decoration under `#ifdef SPIRV`:

```hlsl
#ifdef SPIRV
[[vk::push_constant]] ConstantBuffer<Constants> g_constants;
#else
cbuffer g_constants : register(b0) { Constants g_constants; };
#endif
```

`pyd.CompileShader` passes `-spirv` to DXC for Vulkan (`_pydonut.cpp:458-459`) but **never
defines `SPIRV`**, and exposes no `defines` parameter (`_pydonut.pyi:316-327`). The port
therefore guards on **`__spirv__`**, which DXC predefines itself whenever it targets SPIR-V, so
the decoration is actually applied on Vulkan.

The rest — `g_positions`/`g_colors`, `RWStructuredBuffer<float> g_buffer : register(u0)`, the
`crashType == 1` infinite loop with its `o_color.r *= test` anti-optimization line, the
`g_buffer[i_vertexId]` load whose memory the page-fault path destroys, and `main_ps` — is
copied verbatim, including the original's explanatory comments.

**Observation, explicitly out of scope:** `shaders/bindless_rendering/bindless_rendering.hlsl:28`
uses the same `#ifdef SPIRV` guard and so silently compiles `VK_PUSH_CONSTANT` to nothing on
Vulkan today. That is a pre-existing issue in a different example; this work notes it but does
not change it.

## `aftermath.py`

Follows `basic_triangle.py`'s structure (runtime shader compilation, `if __name__ ==
"__main__":` body, `folder = Path(__file__).resolve().parent`) plus `work_graphs.py`'s
ImGui-renderer pairing.

- **`CrashType`** — an `enum.IntEnum` with `NONE = 0`, `TIMEOUT = 1`, `PAGEFAULT = 2`, matching
  the C++ `enum class CrashType` values the shader compares against.

- **Shared state** — a small `UIData`-style holder (`crashType: CrashType`) shared by reference
  between the render pass and the UI renderer, the same three-way share `work_graphs.py` and
  `rt_particles.py` use. This replaces the C++ `UIRenderer`-holds-`AftermathSample&` reference
  and its `SetCrashType` setter.

- **`AftermathSample(pyd.IRenderPass)`**
  - `Init()`: compile `main_vs`/`main_ps` from `shaders/aftermath/shaders.hlsl` via
    `pyd.CompileShader` (replacing the sample's `RootFileSystem` mount + `ShaderFactory`, which
    PyDonut does not need), create the command list, and create the 1024-byte
    `R32_FLOAT`/`structStride=4` UAV buffer with `keepInitialState=True` and initial state
    `UnorderedAccess`, matching `aftermath.cpp:98-106`. Sets `waitingForCrash = False`.
  - `BackBufferResizing()`: drop the pipeline, as in the original.
  - `Animate()`: `SetInformativeWindowTitle`.
  - `Render(framebuffer)`: lazily build the binding layout
    (`PushConstants(0, 4)` + `StructuredBuffer_UAV(0)`, visibility `All`), binding set, and
    graphics pipeline with `depthTestEnable = False`; then `open()`, `beginMarker("Frame")`, the
    page-fault block, `beginMarker("Clear")` + `ClearColorAttachment` + `endMarker()`,
    `beginMarker("Draw Triangle")` + state/push-constants/`draw(vertexCount=3)` + `endMarker()`,
    `endMarker()`, `close()`, `executeCommandList`.
  - Push constants are sent as
    `self.commandList.setPushConstants(struct.pack("<I", int(state.crashType)))` — the existing
    binding takes a `bytes`/buffer object (`_pydonut.cpp:1637-1640`), so the C++
    `setPushConstants(&m_CrashType, sizeof(uint32_t))` becomes an explicit 4-byte little-endian
    pack.
  - Page-fault block: when `state.crashType == CrashType.PAGEFAULT and not self.waitingForCrash`,
    call `pyd.DestroyBufferMemory_UnsafeForCrashTesting(device, self.buffer)`, then
    `setEnableAutomaticBarriers(False)` and set `waitingForCrash = True` — the same order as
    `aftermath.cpp:158-178`.

- **`UIRenderer(pyd.ImGui_Renderer)`** — `__init__(deviceManager, state)` stores the shared
  state and calls `pyd.ImGui.DisableIniFile()`, as `work_graphs.py:1039` does. `buildUI()` opens
  a "Controls" window at (10, 10) with the auto-resize flag (the
  `_IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE` constant `work_graphs.py`/`rt_particles.py` already
  define locally), containing:
  - `Button("Trigger timeout")` → sets `state.crashType = CrashType.TIMEOUT`.
  - `Button("Trigger page fault")`, **shown only when the API is not D3D11** — same
    short-circuit and same reason as `aftermath.cpp:231-232`.
  - When `not pyd.AFTERMATH_AVAILABLE`, a `Text` line stating that crash dumps are disabled in
    this build and that the crashes will still occur. This has no C++ counterpart; it exists
    because of the build-conditional binding described above.

- **Bootstrap**
  - `deviceParams.enableDebugRuntime` is **left False even under `-debug`** — Aftermath is
    incompatible with the D3D debug layer (`aftermath.cpp:253-254`). Only
    `enableNvrhiValidationLayer` is set under `-debug`. This intentionally diverges from every
    other example in this repo, and carries a comment saying so.
  - `deviceParams.enableAftermath = True` guarded by `if pyd.AFTERMATH_AVAILABLE:`, with an
    otherwise-branch that prints a warning naming the `-DPYDONUT_WITH_AFTERMATH=ON` rebuild.
  - A `ShaderFactory` over a `RootFileSystem` mounting `bin/shaders/framework/<api>` solely so
    `UIRenderer.Init()` can load ImGui's own shaders — the same mount convention
    `work_graphs.py:1111-1115` uses.
  - Standard `AddRenderPassToBack(example)` / `AddRenderPassToBack(gui)` / `RunMessageLoop()` /
    `RemoveRenderPass` / `Shutdown()` tail.

- **Module docstring** must state where dumps land: `GetDirectoryWithExecutable() /
  crash_<YYYY-MM-DD-HH_MM_SS>` (`extern/donut/src/app/aftermath/AftermathCrashDump.cpp:206`).
  Under PyDonut the "executable" is the interpreter, so dumps appear next to `python.exe` in the
  venv's `Scripts/` directory, **not** in the project root. Donut logs the absolute path when it
  writes the dump (`AftermathCrashDump.cpp:44-45`), so it is discoverable, but the location is
  surprising enough to document up front.

## README

A short subsection alongside the existing optional-feature notes (the `pyd.CompileShader` /
DXC section at `README.md:107` is the model): what `-DPYDONUT_WITH_AFTERMATH=ON` does, that it
downloads the SDK at configure time and so needs network access, that `enableAftermath` and
`AFTERMATH_AVAILABLE` only exist in such a build, and where dumps are written.

## Verification

1. Rebuild with `-DPYDONUT_WITH_AFTERMATH=ON`; confirm the configure step reports the Aftermath
   fetch and that `GFSDK_Aftermath_Lib.x64.dll` lands next to `_pydonut.pyd`.
2. Confirm a **default** (option-off) build still compiles — this is the case the `#if` guards
   exist for, and it must be checked explicitly rather than assumed.
3. `python -c "import src.pydonut as pyd; print(pyd.AFTERMATH_AVAILABLE)"` → `True` on the
   option-on build.
4. Run `aftermath.py`; confirm the triangle renders, the "Controls" window appears, and both
   buttons are present on D3D12 (one button on D3D11).
5. **Stop there.** Actually pressing either button resets the display driver, so triggering the
   crashes and inspecting the resulting `.nv-gpudmp` is left to the user, per the verification
   scope agreed during brainstorming.
