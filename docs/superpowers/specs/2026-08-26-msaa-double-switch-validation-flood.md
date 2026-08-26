# A second runtime AA-mode switch draws against a stale cached pipeline

**Conclusion (established; see SECOND CORRECTION at the bottom for the measurements that settle it):**

`ForwardShadingPass` caches graphics pipelines keyed on a framebuffer's `FramebufferInfo`, sample
count included. `ResetBindingCache()` clears binding sets but *not* those pipelines, so a second
runtime AA-mode change — an MSAA→MSAA rebuild — draws against a pipeline built for the previous
sample count and NVRHI's validation layer floods. One switch at any sample count is clean; it takes
two. **The defect is pre-existing: it reproduces on the stage-1 tip (`6b246ae`), which contains no
shadow code at all, and the same fix should be backported to the stage-1 branch.** Shadows are not
required to trigger it — only to make the secondary push-constant symptom appear.

The fix is to recreate the pass on a render-target rebuild rather than reset its binding cache; it
takes 1.57M framebuffer errors to 0. See `feature_demo.py`, `Render`'s render-target release block.

> **The two sections below are the historical investigation record and their numbers are wrong.**
> Every "validation errors" count in them came from a grep that could only match the *push-constant*
> message, never the framebuffer one. The conclusions those sections draw from a 0 in that column
> ("not pre-existing", "shadows are required") were overturned by the re-measurement at the bottom.
> They are kept because the isolation sequence and the harness they describe are still useful, and
> because a corrected record should show what the error was.

Established by the controller with four runs, all `-debug` (D3D12 debug runtime + NVRHI validation),
each ~60-90s, AA mode driven from the frame loop by temporary instrumentation:

| Run | feature_demo.py from | Shadows | AA behaviour | Validation errors |
| --- | --- | --- | --- | --- |
| 1 | 6b246ae (stage-1 tip, no shadow code at all) | n/a | switched NONE -> MSAA_4X -> MSAA_8X at runtime | **0** |
| 2 | HEAD (5309eb0) | ON | switched NONE -> MSAA_4X -> MSAA_8X at runtime | **1,158,166** |
| 3 | HEAD | OFF (EnableShadows=False) | switched NONE -> MSAA_4X -> MSAA_8X at runtime | **0** |
| 4 | HEAD | ON | started up directly in MSAA_2X, then separately in MSAA_4X | **0** and **0** |

Conclusions, in order of how much they narrow it:

1. NOT pre-existing. Run 1 rules that out — this branch introduced it. Task 7's report concluded
   "pre-existing" from a repro on f35b37b, which is Task 6, still inside this branch.
2. NOT "MSAA plus shadows". Run 4 rules that out — both MSAA modes are clean from a cold start.
3. It is the **runtime transition into MSAA while shadows are enabled**. Runs 2 vs 3 vs 4 isolate it
   to exactly that combination.

The two repeating errors (**the first string is paraphrased, not quoted** -- that paraphrase is
what later became the bad grep; the real text is at `validation-commandlist.cpp:640`):

- `framebuffer used in draw call does not match pipeline`
- `Push constant size (24 bytes) doesn't match the size expected by the pipeline (16 bytes)`

Both read as a pass drawing with a pipeline built against a different framebuffer than the one bound
— i.e. a cached pipeline surviving a render-target rebuild that changed framebuffer info.

Prime suspect, and it is a decision this plan made deliberately: Task 5 does NOT add
`depthPass.ResetBindingCache()` to the render-target release block in `Render`. The spec argues that
`DepthPass::ResetBindingCache` clears only material bindings and vertex-buffer SRVs
(`extern/donut/src/render/DepthPass.cpp:91-95`), which reference neither the render targets nor the
shadow map. That argument is about *binding sets*; these errors are about *pipelines*, which donut's
geometry passes cache separately (`m_Pipelines[PipelineKey::Count]`, keyed on cull mode / alpha test /
winding / reverse depth — notably NOT on framebuffer info). So the spec's reasoning may be sound and
still not cover this. Do not assume the suspect is the cause; it is where to look first.

Repro harness: copy feature_demo.py to a scratch probe, append to the end of `Render`:

    self._f = getattr(self, "_f", 0) + 1
    for _n, _m in [(600, "MSAA_2X"), (1200, "MSAA_4X"), (1800, "MSAA_8X")]:
        if self._f == _n:
            self.ui.AntiAliasingMode = AntiAliasingMode[_m]; print(f"=== {_m} ===", flush=True)

then `PYTHONUNBUFFERED=1 timeout 90 uv run <probe>.py -debug > log 2>&1` and
`grep -icE 'does not match pipeline|Push constant size' log`. PYTHONUNBUFFERED matters: a
timeout-killed run otherwise loses buffered stdout.

**That grep is wrong** -- see SECOND CORRECTION. Count the two messages separately, with
`does not match the framebuffer used to create the pipeline` and `Push constant size`. Two further
harness notes learned the hard way: always `grep -c SWITCH` the log and confirm every switch marker
fired before reading any count (a run whose switches did not fire is void, not clean), and override
`ShouldRenderUnfocused()` to return True in the probe -- `DeviceManager.cpp:685` skips `Render()`
entirely while the window is unfocused, which silently stalls the frame counter to a crawl and is
why a trigger at frame 600 was once thought unreliable.

---

## CORRECTION AND ROOT CAUSE (controller, second investigation)

The first section's conclusion 3 ("the runtime transition into MSAA") was **too broad**, and the
"prime suspect" named there is **disproved**. Six further runs, same harness, same `-debug` build:

| Probe | What it did | Validation errors |
| --- | --- | --- |
| ctx | HEAD + a fresh `DepthPassContext` per shadow render; ONE switch TEMPORAL -> MSAA_4X | 0 |
| ctl | control: HEAD unchanged, ONE switch TEMPORAL -> MSAA_4X | **0** |
| A | HEAD, ONE switch TEMPORAL -> MSAA_8X | 0 |
| B | HEAD, TWO switches TEMPORAL -> MSAA_4X -> MSAA_8X | **1,040,391** |
| C | B + `depthPass.ResetBindingCache()` in the render-target release block | **1,040,094** |
| D | B + `ForwardShadingPass` recreated in the render-target release block | **0** |

What each one settles:

- **ctl vs ctx**: the shared `DepthPassContext` is NOT the cause. The control with the committed
  shared context is equally clean, so the first fix hypothesis was a false positive produced by
  comparing against a run with a different switch sequence. Always run the control.
- **A vs B**: ONE switch is clean at any sample count. It takes a **second** render-target rebuild —
  an MSAA -> MSAA transition, where the sample count changes while the forward path is already the
  active one — to trigger it.
- **C**: the spec's decision NOT to add `depthPass.ResetBindingCache()` to the render-target release
  block is **correct and now evidence-backed**. Adding it changes nothing (1,040,094 vs 1,040,391 is
  run-to-run noise). The ruling offered for overturning stands unoverturned.
- **D**: **root cause.** `ForwardShadingPass` caches graphics pipelines, and `ResetBindingCache()`
  clears binding sets but not those pipelines. A pipeline is built against a specific framebuffer's
  `FramebufferInfo`, sample count included. On the second switch the framebuffer's sample count
  changes under a pipeline that is still cached from the previous one, and NVRHI's validation layer
  says exactly that: `framebuffer used in draw call does not match pipeline`.

The push-constant fingerprint, for whoever reads the second error: `DepthPushConstants` is 4 uints =
**16 bytes** (`donut/shaders/depth_cb.h:45`), `ForwardPushConstants` is 6 uints = **24 bytes**
(`donut/shaders/forward_cb.h:84`). So "Push constant size (24 bytes) doesn't match the size expected
by the pipeline (16 bytes)" is a forward-pass draw issuing against a pipeline whose layout is not the
forward pass's — the same stale-pipeline story, seen from the binding-layout side.

Why shadows are required to trigger it (shadows-off with two switches is clean) is NOT established.
The plausible reading is that the shadow map changes which pipeline permutation the forward pass
builds and caches, making the stale slot reachable — but that is a hypothesis, not a result. What is
established is that this branch makes the latent weakness reachable, and that D fixes it.

## The fix D proves

In `Render`'s render-target release block, alongside the existing `ResetBindingCache` calls, the
forward pass is not reset but **recreated**:

    self.forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
    self.forwardPass.Init(self.shaderFactory, pyd.ForwardShadingPassCreateParameters())

Open question for the implementer: whether `gbufferPass` needs the same treatment. It has the same
pipeline-caching structure, and is only spared because MSAA forces the deferred path off — so the
stale-pipeline case is unreachable for it today. Evidence-only says leave it; symmetry says take it.
Decide it and say which, with the reason.

---

## SECOND CORRECTION (final review): the counted string never matched the primary error

Every count in the two sections above came from `grep -icE 'does not match pipeline|Push constant
size'`. **The string `does not match pipeline` appears nowhere in NVRHI.** The real message is

    The framebuffer used in the draw call does not match the framebuffer used to create the pipeline.

at `extern/donut/nvrhi/src/validation/validation-commandlist.cpp:640`. So every number above is a
**push-constant count only**, and the primary (framebuffer) error was never counted in any of them.

That matters because the push-constant message is a *downstream artifact* of the framebuffer one.
In `CommandListWrapper::setGraphicsState` the framebuffer check logs and returns early
(`validation-commandlist.cpp:645-648`) **before** `evaluatePushConstantSize()` at `:651`, so
`m_PipelinePushConstantSize` keeps the last *successful* `setGraphicsState`'s value. With shadows on
that is the shadow depth pass (`DepthPushConstants`, 16 bytes, `depth_cb.h:45`) and the forward pass
then pushes 24 (`forward_cb.h:84`) -> mismatch. With shadows off nothing interleaves, so the counter
reads 0 **even when the framebuffer mismatch is occurring identically**.

## Re-measured, both strings counted separately

Same harness, same `-debug` build, two switches (TEMPORAL -> MSAA_4X -> MSAA_8X) driven from the
frame loop at frames 1200 and 2400. Both switch markers were confirmed present in every log before
any count was read. Greps:

- framebuffer: `does not match the framebuffer used to create the pipeline`
- pushconst:   `Push constant size`

| Run | feature_demo.py from | Shadows | Switch markers | Framebuffer errors | Push-constant errors |
| --- | --- | --- | --- | --- | --- |
| 1 | 855487c (HEAD, passes recreated) | ON | 2/2 | **0** | **0** |
| 2 | 5309eb0 (pre-fix, ResetBindingCache only) | ON | 2/2 | **1,215,158** | **1,467,081** |
| 3 | 6b246ae (stage-1 tip, no shadow code) | n/a | 2/2 | **1,568,414** | **0** |

Run lengths differ (240s / 120s / 150s), so the counts compare only as zero vs. millions, not to
each other.

Method note for run 3: it ran the stage-1 tip's own `feature_demo.py`, unmodified apart from the
harness, against **this** branch's compiled `_pydonut` module rather than a fresh build of 6b246ae.
The binding delta between the two commits is purely additive plus two widenings (`RenderView` to
`IView`, `RenderCompositeView` to `ICompositeView`, `passEvent` appended last with a nullptr
default), so every call stage-1's script makes reaches the same Donut C++ with the same arguments.
Holding the native module fixed and varying only the Python is in fact the better-controlled
comparison here: a worktree build of 6b246ae would also have dropped the working tree's local
`extern/donut` DeviceManager patch, changing more than the variable under test.

## What this overturns

1. **"NOT pre-existing / this branch introduced it" is wrong.** The first section's run 1 read 0 for
   the stage-1 tip because it was counting push-constant messages, which stage-1 cannot produce (no
   shadow pass to leave a 16-byte push-constant size behind). Counted correctly, the stage-1 tip
   floods with 1.57M framebuffer errors. **The stale-pipeline bug is pre-existing and the same fix
   should be backported to the stage-1 branch.**
2. **"Why shadows are required to trigger it is not established" dissolves.** Shadows are not
   required. They are required only for the *push-constant* symptom, for the ordering reason above.
3. **The fix is unaffected.** Run 1 shows 0 framebuffer errors and 0 push-constant errors, i.e.
   `setGraphicsState` stopped early-returning at all: the mismatch is gone, not merely unreported.
4. Probe C's conclusion (that `depthPass.ResetBindingCache()` is not needed) rested on the same bad
   grep, so its *number* is void, but its conclusion is untouched: C and B differed by noise on a
   metric that, we now know, was measuring the downstream symptom of a mismatch neither run fixed.
   Nothing about it argued for adding the call.
