# D3D12 Work Graphs Interop Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that D3D12 Work Graphs (`ID3D12StateObject` + `DispatchGraph`) can be driven from Python through pydonut, via a minimal one-node broadcasting-launch graph that writes a known constant into a UAV buffer and is read back — before committing to porting the full `Donut-Samples/examples/work_graphs/` sample.

**Architecture:** One new C++ class, `D3D12WorkGraphPipeline`, and one new `CommandList.dispatchWorkGraph` method, added inline in `src/cpp/_pydonut.cpp` under `#ifdef NVRHI_WITH_DX12`. Both reach raw D3D12 exclusively through nvrhi's existing `getNativeObject(ObjectTypes::D3D12_*)` escape hatch — no raw pointers ever cross into Python, no changes to the vendored `extern/donut/nvrhi` submodule. A throwaway script, `work_graphs_prototype.py`, drives it end-to-end using a headless device (same shape as `headless.py`).

**Tech Stack:** pybind11 (existing `_pydonut.cpp` module), D3D12/DXR Work Graphs API (`d3dx12/d3dx12.h` helpers from the fetched Agility SDK package), DXC in-process compilation (`pyd.CompileShader`/`pyd.CompileShaderLibrary`, already present), CMake/scikit-build-core build (`uv sync --reinstall-package pydonut`).

## Global Constraints

- Work Graphs interop code compiles only under `#ifdef NVRHI_WITH_DX12` (Windows/D3D12 builds) — it must not affect Vulkan or non-Windows builds at all.
- No changes to the vendored `extern/donut/nvrhi` submodule.
- No raw D3D12/COM pointers are exposed to Python — every COM call stays inside the new C++ binding code.
- New bindings live inline in `src/cpp/_pydonut.cpp`, matching the existing `#if PYDONUT_HAVE_DXC` optional-feature convention — no new binding source file.
- Feature detection from Python is `hasattr(pyd, "D3D12WorkGraphPipeline")` — no separate stub/no-op class on other backends.
- This is a throwaway feasibility probe: `work_graphs_prototype.py` is not a committed example (no scene, no UI, no other launch-node variants) and is not added to any install/build list.
- Reference design: `docs/superpowers/specs/2026-07-31-workgraphs-interop-prototype-design.md`.

---

## Task 1: Minimal Work Graph HLSL + `NVRHI_WITH_DX12` compile-definition wiring

Proves the shader half of the prototype independently of any new C++ binding code, and wires the C++ preprocessor guard the later tasks depend on.

**Files:**
- Create: `shaders/work_graphs_prototype/dummy_cs.hlsl`
- Create: `shaders/work_graphs_prototype/work_graph.hlsl`
- Modify: `CMakeLists.txt:142` (right after the existing `target_link_libraries(_pydonut PRIVATE ...)` call)

**Interfaces:**
- Produces: two HLSL source files on disk, and the C++ preprocessor macro `NVRHI_WITH_DX12` visible inside `src/cpp/_pydonut.cpp` whenever CMake's own `NVRHI_WITH_DX12` option is on (Windows by default — see `extern/donut/nvrhi/CMakeLists.txt:43`). Task 2 depends on this macro existing.

- [ ] **Step 1: Write `shaders/work_graphs_prototype/dummy_cs.hlsl`**

This is a plain compute shader with no Work Graphs attributes at all — used only as a stand-in `ComputePipeline` so Task 2 can read a root signature back out of it via `getNativeObject`. It must bind the same single UAV register (`u0`, space 0) as `work_graph.hlsl` below, so the root signature it produces is compatible with the work graph's global root signature.

```hlsl
RWStructuredBuffer<uint> u_Output : register(u0);

[numthreads(1, 1, 1)]
void CSDummy(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    u_Output[0] = 0;
}
```

- [ ] **Step 2: Write `shaders/work_graphs_prototype/work_graph.hlsl`**

A single broadcasting-launch node that is also the graph's program entry, dispatched as a 1×1×1 grid, one thread, writing a known constant. No node outputs — this is a one-node leaf graph, the simplest thing `DispatchGraph` can execute.

```hlsl
RWStructuredBuffer<uint> u_Output : register(u0);

[Shader("node")]
[NodeLaunch("broadcasting")]
[NodeIsProgramEntry]
[NodeDispatchGrid(1, 1, 1)]
[numthreads(1, 1, 1)]
void WriteConstant_Node(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    u_Output[0] = 0xC0FFEE;
}
```

- [ ] **Step 3: Wire the `NVRHI_WITH_DX12` compile definition in `CMakeLists.txt`**

Open `CMakeLists.txt` and find the existing block ending at line 142:

```cmake
target_link_libraries(_pydonut PRIVATE
    donut_core
    donut_render
    donut_app
    donut_engine
)
```

Add immediately after it:

```cmake
if (NVRHI_WITH_DX12)
    # Forwards the CMake option as a C++ preprocessor macro so _pydonut.cpp can guard its
    # D3D12 Work Graphs interop code the same way it already guards DXC via PYDONUT_HAVE_DXC.
    target_compile_definitions(_pydonut PRIVATE NVRHI_WITH_DX12=1)
    # d3dx12/d3dx12.h (CD3DX12_STATE_OBJECT_DESC, CD3DX12_WORK_GRAPH_SUBOBJECT, ...) ships in the
    # Agility SDK package fetched above by FetchAgilitySDK.cmake, not on any include path yet.
    target_include_directories(_pydonut PRIVATE "${DONUT_D3D_AGILITY_SDK_PATH}/build/native/include")
endif()
```

- [ ] **Step 4: Rebuild the native module**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds (this step only adds a compile definition and an include path — no new code references them yet, so there is nothing new to fail).

- [ ] **Step 5: Verify both shaders actually compile via the existing DXC bindings**

Run:
```
python -c "from src import pydonut as pyd; from pathlib import Path; api = pyd.GraphicsAPI.D3D12; dummy = Path('shaders/work_graphs_prototype/dummy_cs.hlsl').read_text(); wg = Path('shaders/work_graphs_prototype/work_graph.hlsl').read_text(); dummy_bc = pyd.CompileShader(dummy, 'CSDummy', pyd.ShaderType.Compute, api, sourceName='dummy_cs.hlsl'); wg_bc = pyd.CompileShaderLibrary(wg, api, sourceName='work_graph.hlsl', shaderModel='6_8'); print('OK', len(dummy_bc), len(wg_bc))"
```
Expected: prints `OK <n> <m>` with both lengths > 0.

If this instead raises `RuntimeError` with a DXC diagnostic about unrecognized `NodeLaunch`/`NodeIsProgramEntry`/`NodeDispatchGrid` attributes, that means the vendored DXC is too old for Work Graphs (SM 6.8) — a real, informative prototype result per the design doc, not a bug to chase in this task. Note it in the task's commit message and stop; Tasks 2–3 are moot until DXC is updated.

- [ ] **Step 6: Commit**

```bash
git add shaders/work_graphs_prototype/dummy_cs.hlsl shaders/work_graphs_prototype/work_graph.hlsl CMakeLists.txt
git commit -m "Add minimal Work Graphs HLSL + NVRHI_WITH_DX12 compile definition for pydonut"
```

---

## Task 2: `D3D12WorkGraphPipeline` binding (state object creation) + Python exports

Adds the C++ class that builds the `ID3D12StateObject` for the work graph and reads back its backing-memory requirement — the first real proof that `getNativeObject`-based interop works from inside pydonut's binding layer. No dispatch yet.

**Files:**
- Modify: `src/cpp/_pydonut.cpp:41-43` (includes) and after line 1581 (new class + registration, right after the existing `CompileShaderLibrary` binding since both live in the same `ShaderLibrary`-adjacent area)
- Modify: `src/pydonut/__init__.py:152-158` and `:160` (`__all__`)
- Modify: `src/pydonut/_pydonut.pyi` (after the `CompileShaderLibrary` stub, around line 312)
- Create: `work_graphs_prototype.py` (repo root — skeleton only, stops before dispatch)

**Interfaces:**
- Consumes: `pyd.CompileShader`/`pyd.CompileShaderLibrary` (existing), `device.createShaderLibrary(bytecode: bytes) -> ShaderLibrary` (existing), `device.createComputePipeline(desc: ComputePipelineDesc) -> ComputePipeline` (existing), `pyd.CreateBindingSetAndLayout(device, shaderType, registerSpace, bindingSetDesc) -> (BindingLayout, BindingSet)` (existing, used in `headless.py:68-70`).
- Produces: `pyd.D3D12WorkGraphPipeline(device: Device, shaderLibrary: ShaderLibrary, rootSigSourcePipeline: ComputePipeline, workGraphName: str)`, `.getBackingMemorySize() -> int`. Task 3 consumes both plus the not-yet-added `.getProgramIdentifier()` (C++-internal only, not bound to Python).

- [ ] **Step 1: Add the D3D12 interop includes**

In `src/cpp/_pydonut.cpp`, right after the existing block:
```cpp
#if PYDONUT_HAVE_DXC
#include <dxcapi.h>
#endif
```
add:
```cpp
#ifdef NVRHI_WITH_DX12
#include <wrl.h>
#include <d3dx12/d3dx12.h>
#endif
```

- [ ] **Step 2: Add the `D3D12WorkGraphPipeline` class**

Find the existing binding (around line 1577):
```cpp
    m.def("CompileShaderLibrary", &CompileShaderLibraryWithDXC,
        py::arg("source"), py::arg("api"),
        py::arg("sourceName") = "shader.hlsl", py::arg("shaderModel") = "6_5",
        py::arg("includePaths") = std::vector<std::string>{});
#endif
```

Add immediately after that `#endif` (the `PYDONUT_HAVE_DXC` one), before the `IFileSystem`/`NativeFileSystem` bindings:

```cpp
#ifdef NVRHI_WITH_DX12
    class D3D12WorkGraphPipeline
    {
    public:
        D3D12WorkGraphPipeline(
            nvrhi::IDevice* device,
            nvrhi::IShaderLibrary* shaderLibrary,
            nvrhi::IComputePipeline* rootSigSourcePipeline,
            const std::string& workGraphName)
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
            D3D12_WORK_GRAPH_MEMORY_REQUIREMENTS memReqs = {};
            workGraphProperties->GetWorkGraphMemoryRequirements(workGraphIndex, &memReqs);
            m_backingMemorySize = memReqs.MaxSizeInBytes;
        }

        uint64_t getBackingMemorySize() const { return m_backingMemorySize; }
        D3D12_PROGRAM_IDENTIFIER getProgramIdentifier() const { return m_programIdentifier; }

    private:
        Microsoft::WRL::ComPtr<ID3D12StateObject> m_stateObject;
        std::wstring m_wideName;
        D3D12_PROGRAM_IDENTIFIER m_programIdentifier{};
        uint64_t m_backingMemorySize = 0;
    };

    py::class_<D3D12WorkGraphPipeline, std::shared_ptr<D3D12WorkGraphPipeline>>(m, "D3D12WorkGraphPipeline")
        .def(py::init<nvrhi::IDevice*, nvrhi::IShaderLibrary*, nvrhi::IComputePipeline*, const std::string&>(),
            py::arg("device"), py::arg("shaderLibrary"), py::arg("rootSigSourcePipeline"), py::arg("workGraphName"))
        .def("getBackingMemorySize", &D3D12WorkGraphPipeline::getBackingMemorySize);
#endif // NVRHI_WITH_DX12
```

- [ ] **Step 3: Export the new class from the Python package**

In `src/pydonut/__init__.py`, extend the existing try/except block (lines 152-158):

```python
try:
    # Only present when the native module was built with DXC available.
    from pydonut._pydonut import CompileShader
    from pydonut._pydonut import CompileShaderLibrary
except ImportError:
    CompileShader = None
    CompileShaderLibrary = None

try:
    # Only present in Windows/D3D12 builds (NVRHI_WITH_DX12) -- a prototype interop class,
    # not part of the stable API.
    from pydonut._pydonut import D3D12WorkGraphPipeline
except ImportError:
    D3D12WorkGraphPipeline = None
```

Add `'D3D12WorkGraphPipeline',` to the `__all__` tuple (near `'CompileShaderLibrary',` at line 310).

- [ ] **Step 4: Add the `.pyi` stub**

In `src/pydonut/_pydonut.pyi`, after the `CompileShaderLibrary` stub (around line 312), add:

```python
# D3D12 Work Graphs interop prototype. Only present in Windows/D3D12 builds. Builds the
# ID3D12StateObject for a single-library work graph; raises RuntimeError if the device/driver
# doesn't report D3D12_WORK_GRAPHS_TIER support, or if state object creation fails.
class D3D12WorkGraphPipeline:
    def __init__(
        self,
        device: Device,
        shaderLibrary: ShaderLibrary,
        rootSigSourcePipeline: ComputePipeline,
        workGraphName: str,
    ) -> None: ...
    def getBackingMemorySize(self) -> int: ...
```

- [ ] **Step 5: Create `work_graphs_prototype.py` (skeleton)**

```python
if __name__ == "__main__":
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    folder = Path(__file__).resolve().parent

    def RunPrototype(device: pyd.Device) -> bool:
        if pyd.D3D12WorkGraphPipeline is None:
            pyd.log.error("This build has no D3D12WorkGraphPipeline (not a D3D12 build).")
            return False

        api = device.getGraphicsAPI()
        shaderDir = folder / "shaders" / "work_graphs_prototype"

        dummySource = (shaderDir / "dummy_cs.hlsl").read_text(encoding="utf-8")
        workGraphSource = (shaderDir / "work_graph.hlsl").read_text(encoding="utf-8")

        assert pyd.CompileShader is not None and pyd.CompileShaderLibrary is not None
        dummyBytecode = pyd.CompileShader(
            dummySource, "CSDummy", pyd.ShaderType.Compute, api, sourceName="dummy_cs.hlsl"
        )
        workGraphBytecode = pyd.CompileShaderLibrary(
            workGraphSource, api, sourceName="work_graph.hlsl", shaderModel="6_8"
        )

        dummyShader = device.createShader(dummyBytecode, "CSDummy", pyd.ShaderType.Compute)
        shaderLibrary = device.createShaderLibrary(workGraphBytecode)

        outputBufferDesc = pyd.BufferDesc()
        outputBufferDesc.byteSize = 4
        outputBufferDesc.structStride = 4
        outputBufferDesc.canHaveUAVs = True
        outputBufferDesc.debugName = "WorkGraphOutput"
        outputBufferDesc.initialState = pyd.ResourceStates.UnorderedAccess
        outputBufferDesc.keepInitialState = True
        outputBuffer = device.createBuffer(outputBufferDesc)

        bindingSetDesc = pyd.BindingSetDesc()
        bindingSetDesc.bindings = [pyd.BindingSetItem.StructuredBuffer_UAV(0, outputBuffer)]
        bindingLayout, bindingSet = pyd.CreateBindingSetAndLayout(
            device, pyd.ShaderType.Compute, 0, bindingSetDesc
        )
        if not bindingLayout or not bindingSet:
            pyd.log.error("Failed to create binding layout/set.")
            return False

        dummyPipelineDesc = pyd.ComputePipelineDesc()
        dummyPipelineDesc.CS = dummyShader
        dummyPipelineDesc.addBindingLayout(bindingLayout)
        dummyPipeline = device.createComputePipeline(dummyPipelineDesc)

        workGraphPipeline = pyd.D3D12WorkGraphPipeline(
            device, shaderLibrary, dummyPipeline, "PrototypeWorkGraph"
        )
        backingSize = workGraphPipeline.getBackingMemorySize()
        print(f"Work graph backing memory size: {backingSize} bytes")
        return backingSize > 0

    is_debug = "-debug" in sys.argv
    pyd.log.ConsoleApplicationMode()
    if not is_debug:
        pyd.log.SetMinSeverity(pyd.LogSeverity.Warning)

    api = pyd.GraphicsAPI.D3D12
    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateHeadlessDevice(deviceParams):
        pyd.log.error("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    ok = RunPrototype(deviceManager.GetDevice())
    print("Test PASSED" if ok else "Test FAILED!")
    deviceManager.Shutdown()
    sys.exit(0 if ok else 1)
```

- [ ] **Step 6: Rebuild the native module**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds; if it fails, re-check the D3D12 headers are reachable via the include path added in Task 1 Step 3, and that `ID3D12Device5`/`ID3D12StateObjectProperties1`/`ID3D12WorkGraphProperties`/`CD3DX12_WORK_GRAPH_SUBOBJECT` are declared in the fetched Agility SDK's `d3d12.h`/`d3dx12.h` (older Agility SDK packages predate Work Graphs types).

- [ ] **Step 7: Run the prototype skeleton**

Run: `python work_graphs_prototype.py`
Expected: prints `Work graph backing memory size: <n> bytes` with `n > 0`, then `Test PASSED`. A `RuntimeError` mentioning `D3D12_WORK_GRAPHS_TIER_NOT_SUPPORTED` here is a valid, documented prototype outcome (no Work Graphs support on this GPU/driver) — record it and stop; Task 3 needs working state-object creation to proceed.

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/__init__.py src/pydonut/_pydonut.pyi work_graphs_prototype.py
git commit -m "Add D3D12WorkGraphPipeline binding: state object creation via getNativeObject"
```

---

## Task 3: `CommandList.dispatchWorkGraph` binding + full end-to-end dispatch

Adds the `SetProgram`/`DispatchGraph` call and completes the prototype script with backing-memory allocation, command recording, execution, and UAV readback — the actual proof this works.

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (add the method to the existing `commandList` binding, right after `commandList.def("buildTopLevelAccelStruct", ...)` around line 1414-1417, still inside the `#ifdef NVRHI_WITH_DX12` region opened for Task 2 — move the `#endif` down to include it)
- Modify: `work_graphs_prototype.py` (extend `RunPrototype` with backing buffer, dispatch, readback, assertion)

**Interfaces:**
- Consumes: `D3D12WorkGraphPipeline.getProgramIdentifier()` (C++-internal, added in Task 2, not previously bound to Python — stays that way), `commandList.setComputeState`, `device.createBuffer`, `device.executeCommandList`, `device.waitForIdle`, `device.readBuffer` (all existing, used exactly as in `headless.py`).
- Produces: `commandList.dispatchWorkGraph(pipeline: D3D12WorkGraphPipeline, backingMemoryBuffer: Buffer, initialize: bool, numRecords: int = 1) -> None`.

- [ ] **Step 1: Move the `D3D12WorkGraphPipeline` block's closing `#endif`**

In `src/cpp/_pydonut.cpp`, the `#endif // NVRHI_WITH_DX12` added at the end of Task 2 Step 2 currently closes right after the `py::class_<D3D12WorkGraphPipeline, ...>` registration, before the existing `commandList.def("buildTopLevelAccelStruct", ...)` binding lower in the file. Since the new `dispatchWorkGraph` method must be registered on the already-existing `commandList` object (declared once at line 805, used throughout the file), add it as a **separate** `#ifdef NVRHI_WITH_DX12` block placed immediately after the current `commandList.def("copyBuffer", ...)` binding (around line 1412-1413), rather than moving the Task 2 block. This keeps the two `#ifdef` regions independent and avoids reordering unrelated bindings.

- [ ] **Step 2: Add the `dispatchWorkGraph` binding**

Find (around line 1412):
```cpp
    commandList.def("copyBuffer", &nvrhi::ICommandList::copyBuffer,
        py::arg("dest"), py::arg("destOffsetBytes"), py::arg("src"), py::arg("srcOffsetBytes"), py::arg("dataSizeBytes"));
```

Add immediately after it:

```cpp
#ifdef NVRHI_WITH_DX12
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
```

- [ ] **Step 3: Add the `.pyi` stub**

In `src/pydonut/_pydonut.pyi`, inside the `CommandList` class (find the existing `copyBuffer` stub and add after it, matching its indentation):

```python
    # D3D12 Work Graphs interop prototype. Only present in Windows/D3D12 builds. Sets the
    # given work graph as the active program (initializing its backing memory on first use)
    # and dispatches it with a single, zero-size input record at entry point 0.
    def dispatchWorkGraph(
        self,
        pipeline: D3D12WorkGraphPipeline,
        backingMemoryBuffer: Buffer,
        initialize: bool,
        numRecords: int = 1,
    ) -> None: ...
```

- [ ] **Step 4: Extend `work_graphs_prototype.py` with the full dispatch + readback**

Replace the tail of `RunPrototype` (from `workGraphPipeline = pyd.D3D12WorkGraphPipeline(...)` through `return backingSize > 0`) with:

```python
        workGraphPipeline = pyd.D3D12WorkGraphPipeline(
            device, shaderLibrary, dummyPipeline, "PrototypeWorkGraph"
        )
        backingSize = workGraphPipeline.getBackingMemorySize()
        print(f"Work graph backing memory size: {backingSize} bytes")

        backingBufferDesc = pyd.BufferDesc()
        backingBufferDesc.byteSize = max(backingSize, 1)
        backingBufferDesc.canHaveUAVs = True
        backingBufferDesc.debugName = "WorkGraphBackingMemory"
        backingBufferDesc.initialState = pyd.ResourceStates.UnorderedAccess
        backingBufferDesc.keepInitialState = True
        backingBuffer = device.createBuffer(backingBufferDesc)

        readbackBufferDesc = pyd.BufferDesc()
        readbackBufferDesc.byteSize = outputBufferDesc.byteSize
        readbackBufferDesc.cpuAccess = pyd.CpuAccessMode.Read
        readbackBufferDesc.debugName = "ReadbackBuffer"
        readbackBufferDesc.initialState = pyd.ResourceStates.CopyDest
        readbackBufferDesc.keepInitialState = True
        readbackBuffer = device.createBuffer(readbackBufferDesc)

        commandList = device.createCommandList()
        commandList.open()

        state = pyd.ComputeState()
        state.pipeline = dummyPipeline
        state.addBindingSet(bindingSet)
        commandList.setComputeState(state)

        commandList.dispatchWorkGraph(workGraphPipeline, backingBuffer, True, 1)

        commandList.copyBuffer(readbackBuffer, 0, outputBuffer, 0, readbackBufferDesc.byteSize)

        commandList.close()
        device.executeCommandList(commandList)
        device.waitForIdle()

        import struct
        computedResult = struct.unpack("<I", device.readBuffer(readbackBuffer, 4))[0]
        expectedResult = 0xC0FFEE
        print(f"Expected result: {expectedResult:#x}, computed result: {computedResult:#x}")
        return computedResult == expectedResult
```

- [ ] **Step 5: Rebuild the native module**

Run: `uv sync --reinstall-package pydonut`
Expected: build succeeds.

- [ ] **Step 6: Run the full prototype**

Run: `python work_graphs_prototype.py`
Expected: prints the backing memory size, then `Expected result: 0xc0ffee, computed result: 0xc0ffee`, then `Test PASSED`, and the script exits 0.

If `computedResult` differs (e.g. `0`), the graph's output write isn't reaching the buffer the readback observes — check the binding set uses the same UAV slot the dummy pipeline's root signature was compiled with (`register(u0)` in both HLSL files, `StructuredBuffer_UAV(0, ...)` in the binding set), and that `initialize=True` was actually passed on the (in this prototype, only) dispatch call.

- [ ] **Step 7: Regression check**

Run: `python headless.py`
Expected: reaches `Test PASSED` as before — confirms the new `commandList.dispatchWorkGraph` binding and the `#ifdef NVRHI_WITH_DX12` changes didn't break the existing headless example.

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi work_graphs_prototype.py
git commit -m "Add dispatchWorkGraph binding; complete end-to-end Work Graphs interop prototype"
```

---

## Plan Self-Review Notes

- **Spec coverage:** every piece of the design doc's "New native bindings" and "Prototype script structure" sections maps to a task — HLSL (Task 1), `D3D12WorkGraphPipeline`/exports (Task 2), `dispatchWorkGraph`/full script (Task 3). The design's "Verification" section maps directly to Task 3 Steps 6-7.
- **Placeholder scan:** no TBD/"handle appropriately" text; every step has literal code or an exact command.
- **Type consistency:** `D3D12WorkGraphPipeline` (class name), `getBackingMemorySize`/`getProgramIdentifier` (methods), `dispatchWorkGraph(pipeline, backingMemoryBuffer, initialize, numRecords=1)` (signature) are used identically across Tasks 2 and 3 and in the `.pyi` stubs.
- **Known risk, called out where it bites:** Work Graphs requires shader model 6.8 and a sufficiently recent DXC/Agility SDK; both Task 1 Step 5 and Task 2 Step 7 spell out that a `RuntimeError` here is a valid, informative prototype outcome, not a bug to debug further within this plan.

---

Plan complete and saved to `docs/superpowers/plans/2026-07-31-workgraphs-interop-prototype.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
