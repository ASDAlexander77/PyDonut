# Async Compute Example Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `Donut-Samples/examples/async_compute/async_compute.cpp` to `async_compute.py`, adding the multi-queue binding surface PyDonut currently lacks.

**Architecture:** Six new pybind11 bindings expose NVRHI's second-queue machinery (per-queue lifetime tracker, cross-queue fence wait, command-list queue selection, and the thread-safe binding-set cache). The GIL is then released on the calls a worker thread makes, so a Python `threading.Thread` recording and submitting on the compute queue genuinely overlaps the render thread. The example is a full-screen quad on the graphics queue sampling a 512x512 noise texture that the worker rewrites at 100 Hz on the compute queue, with two textures ping-ponging between them.

**Tech Stack:** C++20, pybind11, NVRHI, Donut, scikit-build-core, uv, pytest. Python 3.14.

**Spec:** `docs/superpowers/specs/2026-08-30-async-compute-example-design.md`

## Global Constraints

- Every new `.py` file starts with the 22-line MIT header used by every other example — copy it verbatim from `meshlets.py:1-22` (`Copyright (C) 1991-2026 ASDAlexander77.`).
- Example bodies live entirely inside `if __name__ == "__main__":`, with imports inside that block, matching all 18 existing examples.
- Examples import as `from src import pydonut as pyd`. Tests import as `import pydonut as pyd`.
- Type hints use `X | None`, never `Optional[X]` (see commit `a24fe68`).
- Any binding added to `src/cpp/_pydonut.cpp` must also be added to `src/pydonut/_pydonut.pyi` and, if it is a new top-level name, to both the import list and `__all__` in `src/pydonut/__init__.py`.
- After editing `src/cpp/_pydonut.cpp`, `uv sync` must be re-run to rebuild the native module. It is cached on `src/**/*.{h,c,hpp,cpp}`, so the rebuild is automatic but takes minutes.
- Tests in `test/` must not create a device or render anything — they are GPU-free surface tests.
- `pyd.CompileShader` is `None` when the native module was built without DXC (`src/pydonut/__init__.py:218`). Any test that compiles a shader must skip in that case.
- Do not run `git commit` with `--no-verify`. Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/cpp/_pydonut.cpp` (modify) | The six new bindings, plus the widened GIL-release list |
| `src/pydonut/_pydonut.pyi` (modify) | Stub entries, including the `setLifetimeTracker` ownership warning |
| `src/pydonut/__init__.py` (modify) | Re-export `CommandListLifetimeTracker` |
| `test/test_async_compute_bindings.py` (create) | GPU-free surface tests for all six bindings, plus the shader compile test |
| `shaders/async_compute/shaders.hlsl` (create) | Copied verbatim from the C++ sample; `main_vs` / `main_ps` / `main_cs` |
| `async_compute.py` (create) | The example |
| `README.md` (modify) | One row in the compute examples table |

Tasks 1 and 2 each end in a native rebuild plus `uv run pytest`. Task 3 is separated because it changes an existing hot path used by all 18 examples and deserves its own review gate. Tasks 4 and 5 are the example itself.

---

### Task 1: Lifetime tracker and command-list queue selection

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (near `:927`, `:1426-1430`, `:1433`)
- Modify: `src/pydonut/_pydonut.pyi`
- Modify: `src/pydonut/__init__.py`
- Test: `test/test_async_compute_bindings.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `pyd.CommandListLifetimeTracker` — opaque, no Python constructor; method `runGarbageCollection() -> None`
  - `pyd.Device.createCommandListLifetimeTracker(executionQueue: CommandQueue) -> CommandListLifetimeTracker`
  - `pyd.CommandListParameters.setQueueType(value: CommandQueue) -> CommandListParameters` (returns self)
  - `pyd.CommandListParameters.setLifetimeTracker(value: CommandListLifetimeTracker) -> CommandListParameters` (returns self)

- [ ] **Step 1: Write the failing test**

Create `test/test_async_compute_bindings.py`. Start with the 22-line MIT header copied from `meshlets.py:1-22`, then:

```python
"""Surface tests for the async_compute multi-queue bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a chained setter that returns a copy instead of self.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def test_lifetime_tracker_is_exported() -> None:
    assert hasattr(pyd, "CommandListLifetimeTracker")
    assert "CommandListLifetimeTracker" in pyd.__all__


def test_lifetime_tracker_has_no_python_constructor() -> None:
    # Device-only construction: nvrhi hands out exactly one owning reference per
    # createCommandListLifetimeTracker call (nvrhi.h:3764), and there is no standalone
    # constructor to bind.
    with pytest.raises(TypeError):
        pyd.CommandListLifetimeTracker()


def test_lifetime_tracker_exposes_run_garbage_collection() -> None:
    assert callable(pyd.CommandListLifetimeTracker.runGarbageCollection)


def test_device_exposes_create_lifetime_tracker() -> None:
    assert hasattr(pyd.Device, "createCommandListLifetimeTracker")


def test_set_queue_type_returns_self_so_calls_chain() -> None:
    # py::return_value_policy::reference keeps Python object identity, so `is` holds --
    # verified against the existing setEnableImmediateExecution binding.
    params = pyd.CommandListParameters()
    assert params.setQueueType(pyd.CommandQueue.Compute) is params


def test_set_queue_type_accepts_every_queue() -> None:
    params = pyd.CommandListParameters()
    for queue in (pyd.CommandQueue.Graphics, pyd.CommandQueue.Compute, pyd.CommandQueue.Copy):
        assert params.setQueueType(queue) is params


def test_set_lifetime_tracker_is_bound_and_chains() -> None:
    # None is a valid tracker (nvrhi.h:3135 defaults it to nullptr, meaning "use the device's
    # own trackers"), so this exercises the binding without needing a device.
    params = pyd.CommandListParameters()
    assert params.setLifetimeTracker(None) is params


def test_parameters_setters_chain_together() -> None:
    params = pyd.CommandListParameters()
    chained = (
        params.setEnableImmediateExecution(False)
        .setQueueType(pyd.CommandQueue.Compute)
        .setLifetimeTracker(None)
    )
    assert chained is params
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_async_compute_bindings.py -v`
Expected: FAIL — `AttributeError: module 'pydonut' has no attribute 'CommandListLifetimeTracker'`.

- [ ] **Step 3: Add the tracker class binding**

In `src/cpp/_pydonut.cpp`, immediately after the `Sampler` line at `:927`:

```cpp
    // Per-queue command list lifetime tracker (nvrhi.h:3157). A thread that submits work to a
    // queue should own one for that queue, so it can retire its own submissions without racing
    // the device's internal trackers -- which is exactly what async_compute.py's compute thread
    // does. runGarbageCollection polls the GPU, so it releases the GIL.
    py::class_<nvrhi::ICommandListLifetimeTracker,
               std::shared_ptr<nvrhi::ICommandListLifetimeTracker>>(m, "CommandListLifetimeTracker")
        .def("runGarbageCollection", &nvrhi::ICommandListLifetimeTracker::runGarbageCollection,
             py::call_guard<py::gil_scoped_release>());
```

This must stay above `:1426`, so the type is registered before `setLifetimeTracker` references it.

- [ ] **Step 4: Add the device factory method**

In `src/cpp/_pydonut.cpp`, directly after the `createCommandList` binding at `:1433`:

```cpp
    device.def("createCommandListLifetimeTracker", [](nvrhi::IDevice &self, nvrhi::CommandQueue executionQueue) {
        return DetachToShared(self.createCommandListLifetimeTracker(executionQueue));
    }, py::arg("executionQueue"));
```

- [ ] **Step 5: Add the two chained setters**

Extend the `CommandListParameters` chain at `src/cpp/_pydonut.cpp:1426-1430` so it reads:

```cpp
    py::class_<nvrhi::CommandListParameters>(m, "CommandListParameters")
        .def(py::init<>())
        .def("setEnableImmediateExecution", [](nvrhi::CommandListParameters &self, bool value) -> nvrhi::CommandListParameters& {
            return self.setEnableImmediateExecution(value);
        }, py::arg("value"), py::return_value_policy::reference)
        .def("setQueueType", [](nvrhi::CommandListParameters &self, nvrhi::CommandQueue value) -> nvrhi::CommandListParameters& {
            return self.setQueueType(value);
        }, py::arg("value"), py::return_value_policy::reference)
        // The stored pointer is RAW and NON-OWNING (nvrhi.h:3135) -- the caller must keep the
        // tracker alive for as long as any command list built from these parameters is.
        .def("setLifetimeTracker", [](nvrhi::CommandListParameters &self, nvrhi::ICommandListLifetimeTracker* value) -> nvrhi::CommandListParameters& {
            return self.setLifetimeTracker(value);
        }, py::arg("value").none(true), py::return_value_policy::reference);
```

- [ ] **Step 6: Add the stubs**

In `src/pydonut/_pydonut.pyi`, immediately before `class CommandListParameters` (`:797`):

```python
# Per-queue command list lifetime tracker (nvrhi.h:3157). Each thread that submits work to a
# queue should own one for that queue: after a submission, the internal command lists and the
# resources they reference are held here until the GPU has finished with them. Constructed only
# by Device.createCommandListLifetimeTracker -- there is no Python constructor.
class CommandListLifetimeTracker():
    # Releases command lists that have finished executing on the GPU. Call it frequently, e.g.
    # once per simulation step. Releases the GIL -- it polls the GPU.
    def runGarbageCollection(self: CommandListLifetimeTracker) -> None: ...
```

Add to `class CommandListParameters`, after `setEnableImmediateExecution` (`:801`):

```python
    # Which queue a command list built from these parameters submits to. Requires the device to
    # have been created with DeviceCreationParameters.enableComputeQueue for CommandQueue.Compute.
    def setQueueType(self: CommandListParameters, value: CommandQueue) -> CommandListParameters: ...
    # WARNING: this stores a RAW, NON-OWNING pointer (nvrhi.h:3135). Keep your own reference to
    # the tracker for as long as any command list created from these parameters is alive --
    # letting it be collected is a use-after-free, not a Python exception. None means "use the
    # device's own internal trackers", which is the default.
    def setLifetimeTracker(self: CommandListParameters, value: CommandListLifetimeTracker | None) -> CommandListParameters: ...
```

Add to `class Device`, after `createCommandList` (`:880`):

```python
    def createCommandListLifetimeTracker(self: Device, executionQueue: CommandQueue) -> CommandListLifetimeTracker: ...
```

- [ ] **Step 7: Re-export the new name**

In `src/pydonut/__init__.py`, after `from pydonut._pydonut import CommandListParameters` (`:93`):

```python
from pydonut._pydonut import CommandListLifetimeTracker
```

And in `__all__`, after `'CommandListParameters',` (`:296`):

```python
    'CommandListLifetimeTracker',
```

- [ ] **Step 8: Rebuild and run the tests**

Run: `uv sync && uv run pytest test/test_async_compute_bindings.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 9: Run the full suite for regressions**

Run: `uv run pytest`
Expected: PASS, no new failures.

- [ ] **Step 10: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi src/pydonut/__init__.py test/test_async_compute_bindings.py
git commit -m "Bind CommandListLifetimeTracker and command list queue selection

Adds CommandListLifetimeTracker (device-constructed, runGarbageCollection),
Device.createCommandListLifetimeTracker, and CommandListParameters.setQueueType
/ setLifetimeTracker -- the surface async_compute.py needs to record and submit
on the compute queue from its own thread.

setLifetimeTracker stores a raw non-owning pointer, which the stub documents.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Cross-queue synchronisation and the binding-set cache

**Files:**
- Modify: `src/cpp/_pydonut.cpp` (near `:1448`, `:1988-1990`)
- Modify: `src/pydonut/_pydonut.pyi`
- Test: `test/test_async_compute_bindings.py`

**Interfaces:**
- Consumes: `pyd.CommandQueue` (pre-existing).
- Produces:
  - `pyd.Device.queueWaitForCommandList(waitQueue: CommandQueue, executionQueue: CommandQueue, instance: int) -> None`
  - `pyd.BindingCache.GetOrCreateBindingSet(desc: BindingSetDesc, layout: BindingLayout) -> BindingSet`

- [ ] **Step 1: Write the failing test**

Append to `test/test_async_compute_bindings.py`:

```python
def test_device_exposes_queue_wait_for_command_list() -> None:
    assert hasattr(pyd.Device, "queueWaitForCommandList")


def test_binding_cache_exposes_get_or_create_binding_set() -> None:
    # BindingCache previously bound only Clear(). GetOrCreateBindingSet is what lets the
    # compute thread build its per-texture UAV binding set without a device round-trip
    # every tick (BindingCache.h:53).
    assert callable(pyd.BindingCache.GetOrCreateBindingSet)


def test_binding_cache_still_exposes_clear() -> None:
    # Guards against the new .def() replacing the chain rather than extending it.
    assert callable(pyd.BindingCache.Clear)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_async_compute_bindings.py -k "queue_wait or get_or_create" -v`
Expected: FAIL — `AttributeError: type object 'Device' has no attribute 'queueWaitForCommandList'`.

- [ ] **Step 3: Bind queueWaitForCommandList**

In `src/cpp/_pydonut.cpp`, directly after the `executeCommandList` binding at `:1448-1450`:

```cpp
    // Cross-queue synchronisation (nvrhi.h:3760): makes waitQueue block until the submission
    // `instance` on executionQueue has completed. `instance` is the value executeCommandList
    // returned for that submission. Releases the GIL -- it waits on a GPU fence.
    device.def("queueWaitForCommandList", &nvrhi::IDevice::queueWaitForCommandList,
        py::arg("waitQueue"), py::arg("executionQueue"), py::arg("instance"),
        py::call_guard<py::gil_scoped_release>());
```

- [ ] **Step 4: Bind GetOrCreateBindingSet**

Extend the `BindingCache` chain at `src/cpp/_pydonut.cpp:1988-1990` so it reads:

```cpp
    py::class_<donut::engine::BindingCache>(m, "BindingCache")
        .def(py::init<nvrhi::IDevice*>(), py::arg("device"))
        // BindingCache is internally thread-safe (a std::shared_mutex; see BindingCache.h:38),
        // so this may block on that lock and may call into the device to create a set -- hence
        // the GIL release.
        .def("GetOrCreateBindingSet", [](donut::engine::BindingCache &self,
                const nvrhi::BindingSetDesc &desc, nvrhi::IBindingLayout* layout) {
            return DetachToShared(self.GetOrCreateBindingSet(desc, layout));
        }, py::arg("desc"), py::arg("layout"), py::call_guard<py::gil_scoped_release>())
        .def("Clear", &donut::engine::BindingCache::Clear);
```

- [ ] **Step 5: Add the stubs**

In `src/pydonut/_pydonut.pyi`, add to `class Device` after `executeCommandLists` (`:887`):

```python
    # Makes waitQueue block until submission `instance` on executionQueue has completed.
    # `instance` is the value executeCommandList returned for that submission.
    def queueWaitForCommandList(self: Device, waitQueue: CommandQueue, executionQueue: CommandQueue, instance: int) -> None: ...
```

Replace `class BindingCache` (`:945-947`) with:

```python
# Maps binding set descriptors to binding set objects, creating them on demand. All methods are
# thread-safe (BindingCache.h:38), so one cache can serve several threads -- though a cache per
# thread avoids lock contention entirely, which is what async_compute.py does.
class BindingCache():
    def __init__(self: BindingCache, device: Device) -> None: ...
    def GetOrCreateBindingSet(self: BindingCache, desc: BindingSetDesc, layout: BindingLayout) -> BindingSet: ...
    def Clear(self: BindingCache) -> None: ...
```

- [ ] **Step 6: Rebuild and run the tests**

Run: `uv sync && uv run pytest test/test_async_compute_bindings.py -v`
Expected: PASS, 11 tests.

- [ ] **Step 7: Run the full suite for regressions**

Run: `uv run pytest`
Expected: PASS, no new failures.

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp src/pydonut/_pydonut.pyi test/test_async_compute_bindings.py
git commit -m "Bind queueWaitForCommandList and BindingCache.GetOrCreateBindingSet

queueWaitForCommandList is the cross-queue fence async_compute.py uses in both
directions, keyed on the instance IDs executeCommandList already returned.
GetOrCreateBindingSet lets the compute thread reuse per-texture binding sets;
BindingCache is internally thread-safe, so both threads can hold their own.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Widen the GIL-release list

**Files:**
- Modify: `src/cpp/_pydonut.cpp:1448-1450` (`executeCommandList`), `:1639-1643` (the policy comment), `:1650` (`setComputeState`), `:1651-1652` (`dispatch`)

**Interfaces:**
- Consumes: nothing.
- Produces: no new names. Changes only the threading behaviour of existing bindings.

**Why this is its own task:** `executeCommandList` is called by all 18 existing examples (verified). This is the one change with blast radius beyond the new file, and it deserves a review gate a reviewer can reject independently of Tasks 1 and 2.

- [ ] **Step 1: Write the failing test**

Append to `test/test_async_compute_bindings.py`:

```python
def test_submit_path_bindings_are_still_callable_after_gil_change() -> None:
    """The GIL-release widening is a call_guard change only -- no signature may shift.

    This cannot observe GIL behaviour without a GPU. It is a guard against the edit
    accidentally dropping an argument name or a default while adding the call_guard.
    """
    import inspect

    # pybind11 records argument names in the docstring signature.
    assert "commandList" in pyd.Device.executeCommandList.__doc__
    assert "executionQueue" in pyd.Device.executeCommandList.__doc__
    assert "state" in pyd.CommandList.setComputeState.__doc__
    for name in ("groupsX", "groupsY", "groupsZ"):
        assert name in pyd.CommandList.dispatch.__doc__
    assert inspect is not None  # keeps the import meaningful if assertions are edited
```

- [ ] **Step 2: Run test to verify it passes already**

Run: `uv run pytest test/test_async_compute_bindings.py -k gil -v`
Expected: PASS. This test is a *regression guard*, not a red-then-green test — it must pass before and after, because there is no GPU-free way to observe GIL release. Record the pre-change result so the post-change result is meaningful.

- [ ] **Step 3: Add the call guard to executeCommandList**

At `src/cpp/_pydonut.cpp:1448-1450`, change the trailing arguments so it reads:

```cpp
    device.def("executeCommandList", [](nvrhi::IDevice &self, nvrhi::ICommandList* cmdList, nvrhi::CommandQueue executionQueue) {
        return self.executeCommandList(cmdList, executionQueue);
    }, py::arg("commandList"), py::arg("executionQueue") = nvrhi::CommandQueue::Graphics,
       py::call_guard<py::gil_scoped_release>());
```

- [ ] **Step 4: Add the call guard to setComputeState and dispatch**

At `src/cpp/_pydonut.cpp:1650-1652`:

```cpp
    commandList.def("setComputeState", &nvrhi::ICommandList::setComputeState, py::arg("state"),
        py::call_guard<py::gil_scoped_release>());
    commandList.def("dispatch", &nvrhi::ICommandList::dispatch,
        py::arg("groupsX"), py::arg("groupsY") = 1, py::arg("groupsZ") = 1,
        py::call_guard<py::gil_scoped_release>());
```

- [ ] **Step 5: Rewrite the policy comment**

Replace `src/cpp/_pydonut.cpp:1639-1643` with:

```cpp
    // GIL policy for this file: a binding gets py::call_guard<py::gil_scoped_release> when it
    // can BLOCK -- on a driver submit, on a GPU fence, or on a mutex. Releasing there is what
    // lets Python threads actually run in parallel instead of interleaving under the GIL.
    //
    // Two examples depend on this. threaded_rendering.py records six independent per-face
    // command lists on a thread pool (open/close/RenderCompositeView). async_compute.py runs a
    // compute thread that records and submits on the compute queue while the render thread
    // submits on the graphics queue (executeCommandList, setComputeState, dispatch,
    // queueWaitForCommandList, BindingCache.GetOrCreateBindingSet,
    // CommandListLifetimeTracker.runGarbageCollection).
    //
    // setPushConstants is deliberately NOT on the list: it is a small memcpy that cannot block,
    // and it holds a pointer obtained from py::buffer_info across the call -- releasing the GIL
    // there would let another Python thread mutate or resize a bytearray mid-copy, trading a
    // real safety property for nothing. Anything else not listed simply has no blocking call.
```

- [ ] **Step 6: Rebuild and run the full suite**

Run: `uv sync && uv run pytest`
Expected: PASS, no new failures. This is the regression check on `executeCommandList` for the other 18 examples.

- [ ] **Step 7: Smoke-test an existing example**

Run: `uv run basic_triangle.py -debug`
Expected: a window with a triangle; close it. No NVRHI validation errors in the console. This is the only pre-existing-example check that a GPU is present for; it confirms the `executeCommandList` guard did not break the ordinary single-threaded submit path.

- [ ] **Step 8: Commit**

```bash
git add src/cpp/_pydonut.cpp test/test_async_compute_bindings.py
git commit -m "Release the GIL on the blocking submit and dispatch bindings

executeCommandList, setComputeState and dispatch now release the GIL, so
async_compute.py's compute thread overlaps the render thread instead of
serialising behind it. setPushConstants is deliberately excluded: it cannot
block and it holds a py::buffer pointer across the call.

Rewrites the policy comment to state the rule -- release when the call can
block on a submit, a fence or a mutex -- rather than enumerating one example.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The shader, with a GPU-free compile test

**Files:**
- Create: `shaders/async_compute/shaders.hlsl`
- Test: `test/test_async_compute_bindings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: three HLSL entry points for Task 5 — `main_vs` (no inputs beyond `SV_VertexID`, outputs `SV_Position` + `TEXCOORD0`), `main_ps` (samples `t0`/`s0`, returns `SV_Target0`), `main_cs` (`[numthreads(8, 8, 1)]`, writes `u0`, reads a single `uint counter` push constant at slot 0).

- [ ] **Step 1: Write the failing test**

Append to `test/test_async_compute_bindings.py`:

```python
_DONUT_INCLUDE = str(pathlib.Path(__file__).resolve().parent.parent / "extern" / "donut" / "include")
_SHADER = pathlib.Path(__file__).resolve().parent.parent / "shaders" / "async_compute" / "shaders.hlsl"


@pytest.mark.skipif(pyd.CompileShader is None, reason="native module built without DXC")
@pytest.mark.parametrize(
    "entry,shader_type",
    [
        ("main_vs", pyd.ShaderType.Vertex),
        ("main_ps", pyd.ShaderType.Pixel),
        ("main_cs", pyd.ShaderType.Compute),
    ],
)
def test_shader_entry_points_compile_to_spirv(entry, shader_type) -> None:
    """Compiles for Vulkan, which needs no device and works on every platform.

    This is the one behavioural check available without a GPU: it proves the shader's
    binding_helpers.hlsli include resolves and that all three entry points exist with the
    names async_compute.py passes.
    """
    assert pyd.CompileShader is not None
    bytecode = pyd.CompileShader(
        _SHADER.read_text(encoding="utf-8"),
        entry,
        shader_type,
        pyd.GraphicsAPI.VULKAN,
        sourceName="shaders.hlsl",
        includePaths=[_DONUT_INCLUDE],
    )
    assert len(bytecode) > 0
```

Add `import pathlib` to the imports at the top of the file, beside `import pytest`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_async_compute_bindings.py -k spirv -v`
Expected: FAIL — `FileNotFoundError`, because `shaders/async_compute/shaders.hlsl` does not exist yet.

- [ ] **Step 3: Copy the shader**

```bash
mkdir -p shaders/async_compute
cp "E:/Gits/Donut-Samples/examples/async_compute/shaders.hlsl" shaders/async_compute/shaders.hlsl
```

Copy it verbatim — no edits. It is 108 lines: `main_vs` builds a full-screen triangle strip from `SV_VertexID`, `main_ps` samples `texture0`, and `main_cs` writes simplex noise into `rwTexture0` offset by the `counter` push constant. Do **not** port the sample's `shaders.cfg`; PyDonut compiles HLSL in-process rather than through ShaderMake.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest test/test_async_compute_bindings.py -k spirv -v`
Expected: PASS, 3 tests (or SKIPPED if this build has no DXC).

- [ ] **Step 5: Commit**

```bash
git add shaders/async_compute/shaders.hlsl test/test_async_compute_bindings.py
git commit -m "Add async_compute shader with a GPU-free compile test

Copied verbatim from the C++ sample. The test compiles all three entry points
to SPIR-V, which needs no device -- the only behavioural check available in a
GPU-free suite, and it proves the binding_helpers.hlsli include resolves.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The example

**Files:**
- Create: `async_compute.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything produced by Tasks 1, 2 and 4.
- Produces: the example. Nothing depends on it.

- [ ] **Step 1: Write the example**

Create `async_compute.py`. Begin with the 22-line MIT header copied verbatim from `meshlets.py:1-22`, then:

```python
"""Port of Donut's async_compute sample.

A compute thread rewrites a 512x512 noise texture at 100 Hz on the COMPUTE queue while the
render thread draws it as a full-screen quad on the GRAPHICS queue. Two textures ping-pong
between the threads, and the two GPU queues are synchronised in both directions with
queueWaitForCommandList, keyed on the submission instance IDs executeCommandList returns.

This is the only example that uses a second GPU queue. Three things make it work:

  * DeviceCreationParameters.enableComputeQueue -- without it the device has no compute queue
    and createCommandListLifetimeTracker(Compute) fails.
  * A per-queue CommandListLifetimeTracker, so the compute thread retires its own submissions
    without racing the device's internal trackers (nvrhi.h:3150).
  * A GIL released across executeCommandList/setComputeState/dispatch, so the compute thread
    genuinely overlaps the render thread rather than interleaving under the GIL.
"""

if __name__ == "__main__":
    import queue
    import struct
    import sys
    import threading
    import time
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Async Compute"
    folder = Path(__file__).resolve().parent
    donutIncludeDir = folder / "extern" / "donut" / "include"

    TEXTURE_SIZE = 512
    # Two, as async_compute.cpp:173: one being written by compute while the other is read by
    # the render thread. One would serialise the queues; more would only add latency.
    NUM_TEXTURES = 2
    # 100 Hz, matching async_compute.cpp:254.
    COMPUTE_INTERVAL_SECONDS = 0.01
    # main_cs is [numthreads(8, 8, 1)], so 512 / 8 = 64 groups per axis.
    DISPATCH_GROUPS = TEXTURE_SIZE // 8
    # How long a queue get() blocks before re-checking the stop event. Short enough that
    # Stop() returns promptly, long enough not to spin.
    QUEUE_POLL_SECONDS = 0.05

    class AsyncCompute(pyd.IRenderPass):
        def __init__(self: AsyncCompute, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.vertexShader: pyd.Shader | None = None
            self.pixelShader: pyd.Shader | None = None
            self.computeShader: pyd.Shader | None = None
            self.drawBindingLayout: pyd.BindingLayout | None = None
            self.computeBindingLayout: pyd.BindingLayout | None = None
            self.graphicsPipeline: pyd.GraphicsPipeline | None = None
            self.computePipeline: pyd.ComputePipeline | None = None
            self.drawBindings: pyd.BindingCache | None = None
            self.computeBindings: pyd.BindingCache | None = None
            self.drawCommandList: pyd.CommandList | None = None
            self.computeCommandList: pyd.CommandList | None = None
            # Held for the object's lifetime on purpose: CommandListParameters stores a RAW,
            # NON-OWNING pointer to this (nvrhi.h:3135), so letting it be collected while
            # computeCommandList is alive is a use-after-free rather than an exception.
            self.lifetimeTracker: pyd.CommandListLifetimeTracker | None = None
            # Built here rather than taken off self.m_CommonPasses: that property belongs to
            # ApplicationBase, and this class derives from IRenderPass. Same approach as
            # vertex_buffer.py:142-150.
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.sampler: pyd.Sampler | None = None
            # (texture, lastUseInstanceId) tuples. queue.Queue is the mutex-guarded FIFO the
            # C++ hand-rolls as TextureQueue (async_compute.cpp:39); Python refcounting makes
            # its handle-swapping unnecessary.
            self.renderToCompute: queue.Queue = queue.Queue()
            self.computeToRender: queue.Queue = queue.Queue()
            self.currentRenderTexture: pyd.Texture | None = None
            self.lastRenderTextureUse = 0
            self.stopEvent = threading.Event()
            self.computeThread: threading.Thread | None = None

        def Init(self: AsyncCompute) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "async_compute" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                vsBytecode = pyd.CompileShader(
                    source, "main_vs", pyd.ShaderType.Vertex, api,
                    sourceName=shaderPath.name, includePaths=[str(donutIncludeDir)],
                )
                psBytecode = pyd.CompileShader(
                    source, "main_ps", pyd.ShaderType.Pixel, api,
                    sourceName=shaderPath.name, includePaths=[str(donutIncludeDir)],
                )
                csBytecode = pyd.CompileShader(
                    source, "main_cs", pyd.ShaderType.Compute, api,
                    sourceName=shaderPath.name, includePaths=[str(donutIncludeDir)],
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.vertexShader = device.createShader(vsBytecode, "main_vs", pyd.ShaderType.Vertex)
            self.pixelShader = device.createShader(psBytecode, "main_ps", pyd.ShaderType.Pixel)
            self.computeShader = device.createShader(csBytecode, "main_cs", pyd.ShaderType.Compute)
            if not self.vertexShader or not self.pixelShader or not self.computeShader:
                return False

            # CommonRenderPasses' shaders are read as precompiled .bin files, exactly as
            # vertex_buffer.py:142-150 does -- this project builds Donut without
            # DONUT_WITH_STATIC_SHADERS.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            passesShaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, passesShaderFactory)
            # The C++ uses createSampler({}) (async_compute.cpp:127). Wrap vs clamp is
            # unobservable for a full-screen quad whose UVs are exactly [0, 1].
            self.sampler = self.commonPasses.m_LinearWrapSampler

            drawLayoutDesc = pyd.BindingLayoutDesc()
            drawLayoutDesc.visibility = pyd.ShaderType.Pixel
            drawLayoutDesc.bindings = [
                pyd.BindingLayoutItem.Texture_SRV(0),
                pyd.BindingLayoutItem.Sampler(0),
            ]
            self.drawBindingLayout = device.createBindingLayout(drawLayoutDesc)

            computeLayoutDesc = pyd.BindingLayoutDesc()
            computeLayoutDesc.visibility = pyd.ShaderType.Compute
            computeLayoutDesc.bindings = [
                pyd.BindingLayoutItem.PushConstants(0, 4),  # one uint32 counter
                pyd.BindingLayoutItem.Texture_UAV(0),
            ]
            self.computeBindingLayout = device.createBindingLayout(computeLayoutDesc)

            computePsoDesc = pyd.ComputePipelineDesc()
            computePsoDesc.CS = self.computeShader
            # addBindingLayout, NOT `.bindingLayouts = [...]` -- the desc exposes no such
            # attribute (see the same warning at aftermath.py:190).
            computePsoDesc.addBindingLayout(self.computeBindingLayout)
            self.computePipeline = device.createComputePipeline(computePsoDesc)

            # One cache per thread. BindingCache is internally thread-safe, so one shared cache
            # would also be correct -- two just means neither thread waits on the other's lock.
            self.drawBindings = pyd.BindingCache(device)
            self.computeBindings = pyd.BindingCache(device)

            self.lifetimeTracker = device.createCommandListLifetimeTracker(pyd.CommandQueue.Compute)

            self.drawCommandList = device.createCommandList()

            # setEnableImmediateExecution(False) is required for a command list recorded on one
            # thread and submitted from it while another thread submits elsewhere.
            computeParams = pyd.CommandListParameters()
            computeParams.setEnableImmediateExecution(False) \
                .setQueueType(pyd.CommandQueue.Compute) \
                .setLifetimeTracker(self.lifetimeTracker)
            self.computeCommandList = device.createCommandList(computeParams)

            texDesc = pyd.TextureDesc()
            texDesc.format = pyd.Format.RGBA8_UNORM
            texDesc.width = TEXTURE_SIZE
            texDesc.height = TEXTURE_SIZE
            texDesc.isUAV = True
            # The binding's spelling of enableAutomaticStateTracking(NonPixelShaderResource).
            texDesc.initialState = pyd.ResourceStates.NonPixelShaderResource
            texDesc.keepInitialState = True
            texDesc.debugName = "AsyncComputeTarget"

            for _ in range(NUM_TEXTURES):
                self.renderToCompute.put((device.createTexture(texDesc), 0))

            self.computeThread = threading.Thread(
                target=self.AsyncThreadProc, name="pydonut-async-compute", daemon=True
            )
            self.computeThread.start()
            return True

        def Stop(self: AsyncCompute) -> None:
            """Stops the compute thread. Called from __main__ before deviceManager.Shutdown().

            The C++ does this in ~AsyncCompute (async_compute.cpp:105). Python has no equivalent
            guarantee about when a destructor runs, and a worker still touching GPU objects
            during device teardown crashes -- so the shutdown is explicit and ordered here.
            """
            self.stopEvent.set()
            if self.computeThread is not None:
                self.computeThread.join(timeout=5.0)
                if self.computeThread.is_alive():
                    pyd.log.error("Compute thread did not stop within 5s.")
                self.computeThread = None
            self.GetDevice().waitForIdle()

        def BackBufferResizing(self: AsyncCompute) -> None:
            self.graphicsPipeline = None

        def Animate(self: AsyncCompute, elapsedTimeSeconds: float) -> None:
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def Render(self: AsyncCompute, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.drawCommandList is not None and self.drawBindings is not None
            assert self.drawBindingLayout is not None and self.sampler is not None

            if not self.graphicsPipeline:
                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.vertexShader
                psoDesc.PS = self.pixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleStrip
                psoDesc.renderState.depthStencilState.depthTestEnable = False
                psoDesc.addBindingLayout(self.drawBindingLayout)
                self.graphicsPipeline = device.createGraphicsPipeline(
                    psoDesc, framebuffer.getFramebufferInfo()
                )

            # Take the newest finished texture, if the compute thread has produced one, and
            # hand the outgoing one back for reuse.
            try:
                newTexture, newTextureLastUse = self.computeToRender.get_nowait()
            except queue.Empty:
                pass
            else:
                previous = self.currentRenderTexture
                self.currentRenderTexture = newTexture
                if previous is not None:
                    self.renderToCompute.put((previous, self.lastRenderTextureUse))
                # Graphics must not read the texture until compute has finished writing it.
                device.queueWaitForCommandList(
                    pyd.CommandQueue.Graphics, pyd.CommandQueue.Compute, newTextureLastUse
                )

            self.drawCommandList.open()
            pyd.ClearColorAttachment(self.drawCommandList, framebuffer, 0, pyd.Color(0.0))

            if self.currentRenderTexture is not None:
                bindingDesc = pyd.BindingSetDesc()
                bindingDesc.bindings = [
                    pyd.BindingSetItem.Texture_SRV(0, self.currentRenderTexture),
                    pyd.BindingSetItem.Sampler(0, self.sampler),
                ]
                bindings = self.drawBindings.GetOrCreateBindingSet(
                    bindingDesc, self.drawBindingLayout
                )

                state = pyd.GraphicsState()
                state.pipeline = self.graphicsPipeline
                state.framebuffer = framebuffer
                state.addBindingSet(bindings)
                state.viewport.addViewportAndScissorRect(
                    framebuffer.getFramebufferInfo().getViewport()
                )
                self.drawCommandList.setGraphicsState(state)

                args = pyd.DrawArguments()
                args.vertexCount = 4
                self.drawCommandList.draw(args)

            self.drawCommandList.close()
            # The returned instance ID is what the compute thread waits on before overwriting
            # this texture -- keep it.
            self.lastRenderTextureUse = device.executeCommandList(self.drawCommandList)

        def AsyncThreadProc(self: AsyncCompute) -> None:
            """The compute thread. Ports async_compute.cpp:249-296."""
            device = self.GetDevice()
            assert self.computeCommandList is not None and self.computeBindings is not None
            assert self.computeBindingLayout is not None and self.lifetimeTracker is not None
            counter = 0

            while not self.stopEvent.is_set():
                nextTime = time.monotonic() + COMPUTE_INTERVAL_SECONDS
                self.lifetimeTracker.runGarbageCollection()

                # The C++ spins here (async_compute.cpp:263). A Python spin would pin a core and
                # starve the render thread through the GIL, so block on the queue instead and
                # re-check the stop event each time it times out.
                try:
                    texture, textureLastUse = self.renderToCompute.get(timeout=QUEUE_POLL_SECONDS)
                except queue.Empty:
                    continue

                self.computeCommandList.open()

                bindingDesc = pyd.BindingSetDesc()
                bindingDesc.bindings = [
                    pyd.BindingSetItem.Texture_UAV(0, texture),
                    pyd.BindingSetItem.PushConstants(0, 4),
                ]
                bindings = self.computeBindings.GetOrCreateBindingSet(
                    bindingDesc, self.computeBindingLayout
                )

                state = pyd.ComputeState()
                state.pipeline = self.computePipeline
                state.addBindingSet(bindings)
                self.computeCommandList.setComputeState(state)
                self.computeCommandList.setPushConstants(struct.pack("<I", counter))
                self.computeCommandList.dispatch(DISPATCH_GROUPS, DISPATCH_GROUPS)
                self.computeCommandList.close()

                # Compute must not overwrite the texture until the graphics queue has finished
                # reading it. Instance 0 means "never used by graphics yet".
                if textureLastUse > 0:
                    device.queueWaitForCommandList(
                        pyd.CommandQueue.Compute, pyd.CommandQueue.Graphics, textureLastUse
                    )
                textureLastUse = device.executeCommandList(
                    self.computeCommandList, pyd.CommandQueue.Compute
                )
                self.computeToRender.put((texture, textureLastUse))

                counter += 1
                # Event.wait rather than sleep: shutdown must not wait out a full tick.
                remaining = nextTime - time.monotonic()
                if remaining > 0:
                    self.stopEvent.wait(remaining)

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    is_debug = "-debug" in sys.argv

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    # Without this the device has no compute queue at all and
    # createCommandListLifetimeTracker(Compute) fails. Matches async_compute.cpp:310.
    deviceParams.enableComputeQueue = True
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    example = AsyncCompute(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    # Before Shutdown(), and after the render pass is unhooked: the compute thread must not be
    # touching GPU objects while the device is being torn down.
    example.Stop()

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
```

- [ ] **Step 2: Typecheck it**

Run: `pyrefly check async_compute.py`
Expected: 0 errors.

Every API spelling in Step 1 was verified against the installed module while this plan was
written: `GraphicsState.addBindingSet`, `ComputeState.addBindingSet` / `.pipeline`,
`BindingLayoutDesc.visibility` / `.bindings` (assignable list), `BindingSetDesc.bindings`
(assignable list), `ComputePipelineDesc.CS` / `.addBindingLayout`,
`GraphicsPipelineDesc.addBindingLayout`, `BindingLayoutItem.Texture_UAV`,
`BindingSetItem.Texture_UAV`, `CommonRenderPasses.m_LinearWrapSampler`,
`Format.RGBA8_UNORM`, `ResourceStates.NonPixelShaderResource`,
`PrimitiveType.TriangleStrip`.

- [ ] **Step 3: Run it**

Run: `uv run async_compute.py`
Expected: a window showing a coloured simplex-noise field animating smoothly and continuously. Close it; the process must exit cleanly and print `Done.` with no hang (that verifies `Stop()` joins the thread).

- [ ] **Step 4: Run it with validation on**

Run: `uv run async_compute.py -debug`
Expected: same picture, and **no NVRHI validation errors** in the console — in particular none mentioning cross-queue resource state or a command list submitted to the wrong queue. Also expect no live-object reports at exit.

- [ ] **Step 5: Run it on the other backend**

Run: `uv run async_compute.py -vk` (and `-d3d12` on Windows)
Expected: identical behaviour on both backends.

- [ ] **Step 6: Add the README row**

In `README.md`, in the "Compute, work graphs and diagnostics" table, insert directly after the `headless.py` row:

```markdown
| [`async_compute.py`](async_compute.py) | A second GPU queue: a Python thread rewrites a noise texture at 100 Hz on the **compute queue** while the render thread draws it on the graphics queue, with `queueWaitForCommandList` synchronising the two in both directions. |
```

- [ ] **Step 7: Verify the README still validates**

Run:
```bash
uv run python -c "
import re, pathlib
s = pathlib.Path('README.md').read_text(encoding='utf-8')
missing = [u for _, u in re.findall(r'\[([^\]]*)\]\(([^)]+)\)', s)
           if not u.startswith(('http://','https://','mailto:','#')) and not pathlib.Path(u.split('#')[0]).exists()]
print('BROKEN:', missing or 'none')
"
```
Expected: `BROKEN: none`.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add async_compute.py README.md
git commit -m "Add the async_compute example

Ports Donut-Samples' async_compute.cpp: a compute thread rewrites a 512x512
noise texture at 100 Hz on the compute queue while the render thread draws it
on the graphics queue, with two textures ping-ponging between them and
queueWaitForCommandList synchronising both directions.

Diverges from the C++ where Python has a better answer: queue.Queue replaces
the hand-rolled mutex-guarded TextureQueue, a blocking get() replaces the spin
loop, and an explicit Stop() replaces destructor-timed thread teardown.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-review notes

Checked against the spec:

- Every "Missing, and added by this work" row maps to a task: rows 1-4 to Task 1, rows 5-6 to Task 2.
- The GIL table in the spec maps to Task 3, with the three tracker/wait/cache guards landing in Tasks 1-2 where those bindings are introduced rather than being deferred.
- Both spec substitutions are honoured: the sampler in Task 5 Step 1, and the absence of `shaders.cfg` in Task 4 Step 3.
- The spec's four "Verification" bullets map to Task 3 Step 6/7 (`pytest` + existing-example smoke) and Task 5 Steps 3-5 (smooth animation, `-debug` clean, both backends).
- The spec's "Documentation" section maps to the `.pyi` steps in Tasks 1-2 and the README row in Task 5.
- The `lifetimeTracker` raw-pointer hazard appears three times, deliberately: the binding comment (Task 1 Step 5), the stub warning (Task 1 Step 6), and the example's attribute comment (Task 5 Step 1).

Every API name and line reference in this plan was verified against the source or the installed
module. Two errors were caught and fixed during this self-review: the example code originally
used `psoDesc.bindingLayouts = [...]` on both `GraphicsPipelineDesc` and `ComputePipelineDesc`,
which do not have that attribute — the real API is `addBindingLayout(layout)`, and
`aftermath.py:190` already carries a comment warning against exactly that mistake.

Remaining risk is behavioural, not API-level, and cannot be reduced without a GPU: whether the
two queues actually overlap, and whether the cross-queue waits are correctly ordered, is
established only by Task 5 Steps 3-5.
