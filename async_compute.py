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

"""Port of Donut's async_compute sample.

A compute thread targets a 100 Hz tick rewriting a 512x512 noise texture on the COMPUTE queue
while the render thread draws it as a full-screen quad on the GRAPHICS queue. Two textures
ping-pong between the threads, and the two GPU queues are synchronised in both directions with
queueWaitForCommandList, keyed on the submission instance IDs executeCommandList returns.

This is the only example that uses a second GPU queue. Four things make it work:

  * DeviceCreationParameters.enableComputeQueue -- without it the device has no compute queue
    and createCommandListLifetimeTracker(Compute) fails.
  * A per-queue CommandListLifetimeTracker, so the compute thread retires its own submissions
    without racing the device's internal trackers (nvrhi.h:3150).
  * A GIL released across executeCommandList/setComputeState/dispatch, so the compute thread
    genuinely overlaps the render thread rather than interleaving under the GIL.
  * A caveat, not a mechanism: RunMessageLoop doesn't release the GIL, so the compute thread
    only gets scheduled during the render thread's Python callbacks and the released calls
    above -- which bounds the achieved tick rate to roughly once per rendered frame at vsync.
    The GPU-side queue overlap this example demonstrates is real; 100 Hz is a ceiling on the
    compute thread's tick, not a guarantee.
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

    # Also hardcoded as 512 in shaders/async_compute/shaders.hlsl's main_cs (verbatim copy,
    # not parameterized) -- change both together.
    TEXTURE_SIZE = 512
    # Two, as async_compute.cpp:173: one being written by compute while the other is read by
    # the render thread. One would serialise the queues; more would only add latency.
    NUM_TEXTURES = 2
    # 100 Hz target, matching async_compute.cpp:254 -- the achieved rate is lower in practice;
    # see the module docstring.
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
            if self.lifetimeTracker is None:
                pyd.log.fatal("Device has no compute queue -- enable it or run on a GPU that supports one.")
                return False

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

            # Take the next finished texture (FIFO; with only two textures in flight this is
            # always the most recently produced one), if the compute thread has produced one,
            # and hand the outgoing one back for reuse.
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

                try:
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

                    # Compute must not overwrite the texture until the graphics queue has
                    # finished reading it. Instance 0 means "never used by graphics yet".
                    if textureLastUse > 0:
                        device.queueWaitForCommandList(
                            pyd.CommandQueue.Compute, pyd.CommandQueue.Graphics, textureLastUse
                        )
                    textureLastUse = device.executeCommandList(
                        self.computeCommandList, pyd.CommandQueue.Compute
                    )
                    self.computeToRender.put((texture, textureLastUse))
                except Exception as e:
                    # Nothing else observes this thread dying otherwise: Render()'s
                    # get_nowait() would just keep raising queue.Empty forever and silently
                    # keep redrawing the last successfully computed frame, with no indication
                    # anything failed. Log clearly and stop the thread instead of letting
                    # threading.excepthook's traceback (easy to miss) be the only sign.
                    pyd.log.error(f"Compute thread failed, stopping: {e}")
                    break

                counter += 1
                # Event.wait rather than sleep: shutdown must not wait out a full tick.
                remaining = nextTime - time.monotonic()
                if remaining > 0:
                    self.stopEvent.wait(remaining)

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures (including the new AsyncThreadProc
    # error path and the "did not stop within 5s" diagnostic in Stop()) are actually visible in
    # captured output rather than silently blocking on a modal. Same convention as
    # feature_demo.py and most other examples.
    pyd.log.ConsoleApplicationMode()

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
    try:
        if example.Init():
            deviceManager.AddRenderPassToBack(example)
            try:
                deviceManager.RunMessageLoop()
            finally:
                deviceManager.RemoveRenderPass(example)
    finally:
        # Runs even if Init()/RunMessageLoop() raised, and even if Init() returned False (in
        # which case self.computeThread is still None and Stop() is a safe no-op) -- the
        # compute thread must never still be touching GPU objects when Shutdown() runs below.
        example.Stop()

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
