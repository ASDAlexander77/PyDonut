# D3D12 Work Graphs interop prototype — design

## Goal

Before committing to porting `Donut-Samples/examples/work_graphs/` as a full
pydonut example, prove that the one piece of it pydonut cannot do today —
D3D12 Work Graphs (`ID3D12StateObject`, `DispatchGraph`) — can be reached from
Python at all, and how much new binding surface that actually costs.

Work Graphs has no nvrhi abstraction (confirmed: no `WorkGraph`/`DispatchGraph`
symbol anywhere under `extern/donut/nvrhi`), unlike ray tracing pipelines
(`nvrhi::rt::IPipeline`), which is why every other pydonut example ports
cleanly but this one can't yet. This prototype is a throwaway feasibility
probe, not the committed example — scene, UI, and the coalescing/thread-launch
variants are explicitly out of scope.

## Decisions made during brainstorming

- **Success bar: a real end-to-end `DispatchGraph`**, not just "bindings
  compile." A minimal one-node broadcasting-launch graph that writes a known
  constant into a UAV buffer, dispatched and read back, is the only outcome
  that actually proves the interop chain (native device access → state object
  creation → program identifier readback → backing memory → `DispatchGraph`)
  works on real hardware/driver — not just that the C++ compiles.
- **As much through nvrhi as possible; raw D3D12 only where nvrhi has no
  abstraction.** nvrhi already ships exactly the escape hatch this needs —
  `IResource::getNativeObject(ObjectTypes::D3D12_Device /
  D3D12_GraphicsCommandList / D3D12_RootSignature)` — used internally by
  donut's own C++ sample and available on `IDevice`/`ICommandList`/
  `IComputePipeline` today, just not yet bound to Python. Two options were
  considered and rejected in favor of this:
  - Extending nvrhi itself with a cross-API `nvrhi::wg::IPipeline` (mirroring
    `nvrhi::rt`) — rejected as out of scope for a prototype: it patches a
    vendored upstream submodule, and Vulkan has no Work Graphs equivalent to
    implement against.
  - Binding raw pointers (`getNativeObject` return value) directly into
    Python and doing the COM calls in a `.py` file via `ctypes`/ ­`comtypes` —
    rejected because it exposes COM interop to Python, which pydonut has never
    done, and every other binding in this codebase keeps native pointers
    entirely on the C++ side.
- **One new class, not a generic native-object binding.** `getNativeObject`
  itself is *not* exposed to Python. Instead, one new C++-side class
  (`D3D12WorkGraphPipeline`) does the `getNativeObject` calls internally and
  exposes only the high-level operations Work Graphs needs
  (`getBackingMemorySize`, `dispatchWorkGraph`) — keeping the Python-visible
  surface small and consistent with how `nvrhi::rt` is already bound (rich
  desc/state objects, no raw pointers).
- **Inline in `_pydonut.cpp` under `#ifdef NVRHI_WITH_DX12`**, not a new file —
  matches the existing optional-feature convention already in this file
  (`PYDONUT_HAVE_DXC` gates `pyd.CompileShader`'s DXC path the same way).
- **Feature detection via `hasattr`.** Because the class only exists in the
  `#ifdef` block, `hasattr(pyd, "D3D12WorkGraphPipeline")` is the natural
  Python-side capability check — no separate Vulkan stub/no-op class needed.
- **Throwaway test script, not a committed example.** Modeled directly on
  `headless.py` (headless device, no window, single compute round-trip with
  readback) since that pattern already proves out buffer creation, shader
  compilation, dispatch, and readback with the least ceremony. Lives outside
  the committed example set (scratch location) — promoting it to a real
  top-level example is a separate, later decision gated on this prototype
  actually working.

## New native bindings (`src/cpp/_pydonut.cpp`, `#ifdef NVRHI_WITH_DX12` only)

- `D3D12WorkGraphPipeline`:
  - `__init__(device: Device, shaderLibrary: ShaderLibrary, rootSigSourcePipeline: ComputePipeline, workGraphName: str)`
    — queries `ID3D12Device5` via `getNativeObject(D3D12_Device)`; checks
    `D3D12_FEATURE_D3D12_OPTIONS21.WorkGraphsTier`, raising `RuntimeError` if
    `D3D12_WORK_GRAPHS_TIER_NOT_SUPPORTED`; builds
    `CD3DX12_STATE_OBJECT_DESC` (DXIL library subobject from the shader
    library's bytecode, work-graph subobject with `IncludeAllAvailableNodes()`,
    global root signature subobject from `rootSigSourcePipeline->
    getNativeObject(D3D12_RootSignature)`); calls `CreateStateObject`, raising
    `RuntimeError` with the `HRESULT` on failure; reads back the program
    identifier and `D3D12_WORK_GRAPH_MEMORY_REQUIREMENTS`.
  - `getBackingMemorySize() -> int`
- `CommandList.dispatchWorkGraph(pipeline: D3D12WorkGraphPipeline, backingMemoryBuffer: Buffer, initialize: bool, numRecords: int = 1) -> None`
  — queries `ID3D12GraphicsCommandList10` via `getNativeObject
  (D3D12_GraphicsCommandList)`, calls `SetProgram` (with
  `D3D12_SET_WORK_GRAPH_FLAG_INITIALIZE` iff `initialize`) then
  `DispatchGraph` with `D3D12_DISPATCH_MODE_NODE_CPU_INPUT` and
  `NumRecords = numRecords`, no per-record input data (matches the sample's
  root-node entry point with no `SV_DispatchGrid` input).

Both are exported from `src/pydonut/__init__.py` and documented in
`_pydonut.pyi` only when compiled in — guarded the same way the rest of the
module handles conditionally-available features (`pyd.CompileShader`), so
importing pydonut on a non-D3D12 build doesn't fail, it just omits these two
names.

No other existing binding changes. `device.createBuffer`, `createBindingSet`,
`createBindingLayout`, `createComputePipeline`, `ShaderFactory.
CreateShaderLibrary`, and `commandList.setComputeState` are reused exactly as
they exist today.

## New HLSL

One minimal shader library, trimmed from `work_graph_broadcasting.hlsl`: a
single broadcasting-launch root node with no dispatch-grid override, one
thread, that writes a known constant (e.g. `0xC0FFEE`) into a UAV structured
buffer bound at register `u0`. No lighting, materials, or multi-node
fan-out — just enough to exercise `DispatchGraph` once.

## Prototype script structure

Modeled on `headless.py`:

- Create a headless D3D12 device (reuses the existing headless bootstrap; the
  script exits early with a clear message if `device.getGraphicsAPI() !=
  pyd.GraphicsAPI.D3D12` or `not hasattr(pyd, "D3D12WorkGraphPipeline")`).
- Compile the minimal work-graph HLSL library via `ShaderFactory.
  CreateShaderLibrary`.
- Create a UAV output buffer (4 bytes, `R32_UINT`, typed view) and its binding
  layout/set.
- Create a placeholder `ComputePipeline` against that same binding layout,
  purely to source a root signature for `D3D12WorkGraphPipeline` (mirrors the
  C++ sample's use of `m_AnimateLightsPSO` as a bindings-only placeholder).
- Construct `D3D12WorkGraphPipeline`, create the backing-memory buffer sized
  via `getBackingMemorySize()`.
- Record a command list: `setComputeState` (to establish the binding set),
  `dispatchWorkGraph(pipeline, backingBuffer, initialize=True)`.
- Execute, wait for idle, read back the output buffer, assert it equals the
  expected constant, print pass/fail.

## Verification

- `uv sync --reinstall-package pydonut` to rebuild the native module.
- Run the prototype script directly (`python work_graph_prototype.py`) under a
  bounded `timeout`, on a D3D12-capable machine/driver with Work Graphs tier
  support; confirm it prints a pass result with the expected constant read
  back, not an exception.
- If `D3D12_WORK_GRAPHS_TIER_NOT_SUPPORTED` is hit on this machine, that's a
  valid, informative prototype outcome (documents a hard blocker on GPU/driver
  /Agility SDK support) rather than a failure to fix.
- No automated test suite — this is a one-shot feasibility probe, consistent
  with how every other example in this repo is verified (run and observe).
