# Async Compute example port — design

## Goal

Port `Donut-Samples/examples/async_compute/async_compute.cpp` (337 lines) to a new top-level
`async_compute.py` plus `shaders/async_compute/shaders.hlsl`, following the conventions of the
existing 18 examples. It becomes the 19th.

The C++ sample runs a `std::thread` at 100 Hz that writes simplex noise into a 512x512 UAV
texture on the **compute queue**, while the render thread draws that texture as a full-screen
quad on the **graphics queue**. Two textures ping-pong between two mutex-guarded queues, and the
two GPU queues are synchronised in both directions with `queueWaitForCommandList`, keyed on the
submission instance IDs that `executeCommandList` returns. A per-queue
`CommandListLifetimeTracker` lets the worker thread retire its own submissions without racing
the device's internal trackers.

This is the first PyDonut example to use a second GPU queue. Multi-queue submission and
cross-queue synchronisation are not exposed by `_pydonut.cpp` at all today, so this port requires
new binding surface — which is why it went through the architectural brainstorming path rather
than being treated as another single-file example port.

## Binding audit

Verified against the vendored submodule before designing. Everything the sample needs exists in
NVRHI at the pinned revision; no submodule bump is required.

Already bound:

| C++ API | PyDonut |
| --- | --- |
| `nvrhi::CommandQueue::Compute` | `_pydonut.pyi:160` |
| `DeviceCreationParameters::enableComputeQueue` | `_pydonut.cpp:4198` |
| `executeCommandList(cl, queue) -> uint64_t` | `_pydonut.cpp:1448` — already returns the instance ID |
| `CommandListParameters::setEnableImmediateExecution` | `_pydonut.cpp:1428` |
| `BindingLayoutItem::PushConstants` / `BindingSetItem::PushConstants` | `_pydonut.cpp:1193`, `:1264` |
| `ICommandList::setPushConstants` | `_pydonut.cpp:1717` (takes `py::buffer`) |
| `TextureDesc::enableAutomaticStateTracking(state)` | expressed as `initialState` + `keepInitialState` |
| `nvrhi::utils::ClearColorAttachment` | `pyd.ClearColorAttachment` |

Missing, and added by this work:

| C++ API | Declared at |
| --- | --- |
| `CommandListParameters::setQueueType` | `nvrhi.h:3141` |
| `CommandListParameters::setLifetimeTracker` | `nvrhi.h:3142` |
| `ICommandListLifetimeTracker` + `runGarbageCollection()` | `nvrhi.h:3157-3165` |
| `IDevice::createCommandListLifetimeTracker(queue)` | `nvrhi.h:3764` |
| `IDevice::queueWaitForCommandList(waitQueue, executionQueue, instance)` | `nvrhi.h:3760` |
| `BindingCache::GetOrCreateBindingSet(desc, layout)` | `BindingCache.h:53` |

Two substitutions avoid further binding work:

- `GetDevice()->createSampler({})` becomes `self.m_CommonPasses.m_LinearWrapSampler`, which is
  already bound (`_pydonut.pyi:967`). No `createSampler`/`SamplerDesc` binding is needed. Wrap
  versus clamp addressing is unobservable for a full-screen quad whose UVs are exactly `[0, 1]`.
- The sample's `shaders.cfg` has no PyDonut equivalent: examples here compile HLSL in-process
  with `pyd.CompileShader` rather than through ShaderMake.

## Decisions made during brainstorming

- **Faithful threading, with a widened GIL-release list.** The worker becomes a real
  `threading.Thread`, and the calls it makes get `py::call_guard<py::gil_scoped_release>`.
  The alternatives — keeping the thread but letting it hold the GIL across every driver submit,
  or dropping the thread and dispatching from `Render()` — were both rejected: the first ships a
  file named `async_compute.py` in which nothing is actually asynchronous, and the second
  discards the structure the sample exists to teach.
- **Narrow GIL widening, not a sweep.** Only the calls the worker thread actually makes get the
  release. A blanket sweep over the whole `CommandList` surface would change the record and
  submit path of all 18 existing examples in the same change that adds a new feature, and the
  test suite is GPU-free, so nothing in CI would catch a regression.
- **`setPushConstants` is deliberately excluded from that list.** It is a 4-byte `memcpy` that
  cannot block, and it holds a pointer obtained from `py::buffer_info` across the call.
  Releasing the GIL there would let another Python thread mutate or resize a `bytearray` mid-copy
  — a real safety property traded away for no measurable gain.
- **Full binding surface over a minimal one.** Binding the lifetime tracker was optional in the
  narrow sense: `nvrhi.h:3156` says that without one, "the Device will add the command list to its
  own internal lifetime trackers". But the same comment block prescribes, at `nvrhi.h:3150`, that "each thread that submits
  work to the GPU ... should own its own command list tracker for each queue it submits work to".
  Shipping the discouraged pattern inside the one file people will read to learn multi-queue
  submission is worse than the handful of extra binding lines the tracker costs.
- **Explicit `Stop()` rather than a destructor, `try/finally`, or a context manager.** The C++
  relies on `~AsyncCompute` (`async_compute.cpp:105`) setting a flag and joining. Python has no
  equivalent guarantee about when that runs, and a worker thread still touching GPU objects
  during device teardown crashes. `Stop()` is called explicitly from `__main__` between
  `RemoveRenderPass(example)` and `deviceManager.Shutdown()`, which both makes the ordering
  visible in the example source — it is part of what the example teaches — and matches the
  teardown sequence every other example already has.
- **Landed as two commits.** Commit 1: the six bindings, their `.pyi` entries and
  `test/test_async_compute_bindings.py`, verified with `uv run pytest`. Commit 2:
  `async_compute.py`, the shader, and the README row. Because the test suite creates no device, the binding layer can be fully
  surface-verified before any GPU debugging begins. If the example renders black, this gives a
  bisect point that separates a binding bug from a synchronisation bug.
- **`queue.Queue` replaces the C++ `TextureQueue`.** See the divergence table below.

## New native bindings (`src/cpp/_pydonut.cpp`)

Six new callables across five areas, each following an existing house pattern.

```cpp
// Placed with the other opaque resource handles. Held by shared_ptr like every other
// DetachToShared-returned handle in this file.
py::class_<nvrhi::ICommandListLifetimeTracker,
           std::shared_ptr<nvrhi::ICommandListLifetimeTracker>>(m, "CommandListLifetimeTracker")
    .def("runGarbageCollection", &nvrhi::ICommandListLifetimeTracker::runGarbageCollection,
         py::call_guard<py::gil_scoped_release>());

device.def("createCommandListLifetimeTracker", [](nvrhi::IDevice &self, nvrhi::CommandQueue q) {
    return DetachToShared(self.createCommandListLifetimeTracker(q));
}, py::arg("executionQueue"));

device.def("queueWaitForCommandList", &nvrhi::IDevice::queueWaitForCommandList,
    py::arg("waitQueue"), py::arg("executionQueue"), py::arg("instance"),
    py::call_guard<py::gil_scoped_release>());

// Chained setters, mirroring setEnableImmediateExecution at _pydonut.cpp:1428 exactly,
// including py::return_value_policy::reference.
commandListParameters
    .def("setQueueType", [](nvrhi::CommandListParameters &self, nvrhi::CommandQueue value)
            -> nvrhi::CommandListParameters& { return self.setQueueType(value); },
         py::arg("value"), py::return_value_policy::reference)
    .def("setLifetimeTracker", [](nvrhi::CommandListParameters &self,
            nvrhi::ICommandListLifetimeTracker* value) -> nvrhi::CommandListParameters& {
                return self.setLifetimeTracker(value);
         }, py::arg("value"), py::return_value_policy::reference);

bindingCache.def("GetOrCreateBindingSet", [](donut::engine::BindingCache &self,
        const nvrhi::BindingSetDesc &desc, nvrhi::IBindingLayout* layout) {
    return DetachToShared(self.GetOrCreateBindingSet(desc, layout));
}, py::arg("desc"), py::arg("layout"), py::call_guard<py::gil_scoped_release>());
```

### The `lifetimeTracker` raw-pointer hazard

`CommandListParameters::lifetimeTracker` is a **raw, non-owning** pointer (`nvrhi.h:3135`). The
Python `CommandListParameters` object in `Init()` is a temporary; the tracker it points at is not
kept alive by it. The Python code must therefore hold its own reference — `self.lifetimeTracker
= device.createCommandListLifetimeTracker(...)` — for as long as any command list created from
those parameters is alive.

Getting this wrong produces a use-after-free, not a Python exception. The `.pyi` entry for
`setLifetimeTracker` will state the ownership requirement explicitly, and `async_compute.py`
will carry a comment at the assignment saying why the handle is stored on `self` rather than
used inline.

## GIL policy (`src/cpp/_pydonut.cpp:1639`)

The existing comment states that the release list is deliberately scoped to what
`threaded_rendering.py` needs, and warns against assuming broader coverage. It is rewritten to
name both examples and to state the rule rather than the precedent: **a binding gets
`gil_scoped_release` when it can block — on a driver submit, on a GPU fence, or on a mutex.**

Added to the list:

| Binding | Why it qualifies |
| --- | --- |
| `Device.executeCommandList` | driver submit; the worker's hot path |
| `Device.queueWaitForCommandList` | cross-queue fence wait |
| `CommandList.setComputeState` | recording work, and validation-layer builds do real work here |
| `CommandList.dispatch` | recording work, symmetric with `setComputeState` |
| `BindingCache.GetOrCreateBindingSet` | takes a `std::shared_mutex`, and may call into the device |
| `CommandListLifetimeTracker.runGarbageCollection` | polls the GPU |

Explicitly **not** added: `CommandList.setPushConstants` — see the decision above.

`Device.executeCommandList` is on the list and is called by every existing example, so this is
the one change with blast radius beyond the new file. It is a pure `call_guard` addition with no
change to argument conversion (which completes before the guard applies), so no existing caller's
semantics change; the risk is confined to code that could re-enter Python during the submit,
and no `IDevice` method has a Python trampoline.

## `async_compute.py` structure

Mirrors the C++ class layout — `Init`, `BackBufferResizing`, `Animate`, `Render`,
`AsyncThreadProc` — with a `Stop()` added. Divergences, all deliberate:

| C++ | Python | Why |
| --- | --- | --- |
| `TextureQueue` (`async_compute.cpp:39`): `std::mutex` + `std::queue`, handle swapping | `queue.Queue` of `(texture, lastUse)` tuples | The swap dance exists to move ownership without an AddRef/Release pair. Python refcounting gives that for free, and `queue.Queue` is already the mutex-guarded FIFO being hand-rolled. |
| `while (!m_Terminate && !TryPop(...)) {}` (`:263`) | `q.get(timeout=0.05)` inside a loop on a `threading.Event` | Transliterating the spin would pin a core and starve the render thread through the GIL. |
| `createSampler({})` (`:127`) | `self.m_CommonPasses.m_LinearWrapSampler` | Avoids a `createSampler`/`SamplerDesc` binding; addressing mode is unobservable here. |
| `~AsyncCompute()` (`:105`) | `Stop()` called from `__main__` | Python has no deterministic destructor; see the decision above. |
| `std::this_thread::sleep_until` (`:294`) | `time.monotonic()` deadline + `Event.wait(remaining)` | Shutdown must not wait out a full 10 ms tick. |

Retained from the C++ without change: two textures (`:173`), two separate `BindingCache`
instances (`BindingCache` is thread-safe per `BindingCache.h:38`, but one per thread means no
lock contention), the bidirectional `queueWaitForCommandList` pattern (`:218` graphics-waits-on-
compute, `:288` compute-waits-on-graphics), and the deferred compute command list
(`setEnableImmediateExecution(False)` + `setQueueType(Compute)` + `setLifetimeTracker(...)`).

`DeviceCreationParameters.enableComputeQueue = True` is set in `__main__`, matching
`async_compute.cpp:310`. A device without an available compute queue family exits with a clear
diagnostic rather than crashing.

## `shaders/async_compute/shaders.hlsl`

Copied verbatim, no edits. It has three entry points (`main_vs`, `main_ps`, `main_cs`) and
includes `<donut/shaders/binding_helpers.hlsli>` for `REGISTER_SRV` / `REGISTER_UAV` /
`DECLARE_PUSH_CONSTANTS`. `pyd.CompileShader` already accepts `includePaths`, and
`bindless_rendering.py:33,77` establishes the precedent of passing
`folder / "extern" / "donut" / "include"`.

## Verification

`test/test_async_compute_bindings.py`, GPU-free like the other nine suites (they construct no
device and render nothing — see the docstring of `test_camera_bindings.py`):

- every new name is re-exported from `src/pydonut/__init__.py`
- `setQueueType` and `setLifetimeTracker` return the same `CommandListParameters` object, so
  chaining works
- `CommandListLifetimeTracker` has no Python constructor (device-only construction)
- `Device.queueWaitForCommandList` accepts the documented three arguments

Behaviour cannot be covered by that suite. Manual verification, recorded in the plan:

1. `uv run async_compute.py` — the noise field animates smoothly, not in stutters.
2. `uv run async_compute.py -debug` — no NVRHI validation errors, in particular none about
   cross-queue resource state or a command list submitted to the wrong queue.
3. Same on both backends: `-d3d12` and `-vk`.
4. `uv run pytest` stays green — this is the regression check on the `executeCommandList`
   GIL change, since every other example's submit path goes through it.

## Documentation

- `src/pydonut/_pydonut.pyi`: stub entries for all five bindings, with the ownership warning on
  `setLifetimeTracker`.
- `README.md`: one row in the "Compute, work graphs and diagnostics" example table.

## Out of scope

- `createSampler` / `SamplerDesc` bindings — substituted, see above.
- `BindingCache.GetCachedBindingSet` (the non-creating variant, `BindingCache.h:52`) — unused by
  this sample; bind it when something needs it.
- `executeCommandLists` (plural) on a non-graphics queue — already bound, already takes a queue,
  untouched here.
- Any broader GIL sweep over `CommandList`.
