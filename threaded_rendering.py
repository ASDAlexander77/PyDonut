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

if __name__ == "__main__":
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Threaded Rendering"
    folder = Path(__file__).resolve().parent

    def FindSponzaGltf() -> Path | None:
        # Same asset location/lookup as variable_shading.py/bindless_rendering.py.
        candidate = folder / "media" / "glTF-Sample-Assets" / "Models" / "Sponza" / "glTF" / "Sponza.gltf"
        return candidate if candidate.is_file() else None

    # Screen-space (column, row) layout of the 6 cube faces in the composite window,
    # transcribed verbatim from Donut-Samples/examples/threaded_rendering/threaded_rendering.cpp.
    _FACE_LAYOUT = [(3, 1), (1, 1), (2, 0), (2, 2), (2, 1), (0, 1)]
    _CUBE_RESOLUTION = 1024

    class ThreadedRendering(pyd.ApplicationBase):
        def __init__(self: ThreadedRendering, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.textureCache: pyd.TextureCache | None = None
            self.scene: pyd.Scene | None = None

            self.camera = pyd.FirstPersonCamera()
            self.cubemapView = pyd.CubemapView()

            self.forwardPass: pyd.ForwardShadingPass | None = None

            # One immediate command list for the composite blit, plus 6 deferred (non-
            # immediate-execution) command lists, one per cube face, recorded either on the
            # main thread or concurrently across a thread pool depending on self.useThreads.
            self.commandList: pyd.CommandList | None = None
            self.faceCommandLists: list[pyd.CommandList] = []

            self.colorCube: pyd.Texture | None = None
            self.depthCube: pyd.Texture | None = None
            self.framebufferFactory: pyd.FramebufferFactory | None = None

            self.executor: ThreadPoolExecutor | None = None
            self.useThreads = True

        def Init(self: ThreadedRendering) -> bool:
            device = self.GetDevice()

            sceneFileName = FindSponzaGltf()
            if sceneFileName is None:
                pyd.log.fatal("Could not find Sponza.gltf under media/glTF-Sample-Assets/")
                return False

            # CommonRenderPasses/ForwardShadingPass's own shaders are only statically linked in
            # when Donut is built with DONUT_WITH_STATIC_SHADERS, which this project's CMake
            # leaves off -- so read them as precompiled .bin files via the filesystem instead,
            # same as the other examples.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(device.getGraphicsAPI())
            rootFS = pyd.RootFileSystem()
            rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.shaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.bindingCache = pyd.BindingCache(device)

            nativeFS = pyd.NativeFileSystem()
            self.textureCache = pyd.TextureCache(device, nativeFS, None)

            # Mirrors the C++ sample's tf::Executor: created once and reused every frame, not
            # recreated per frame.
            self.executor = ThreadPoolExecutor(max_workers=6)

            # Runs LoadScene() (below) synchronously, followed by SceneLoaded() (below).
            self.SetAsynchronousLoadingEnabled(False)
            self.BeginLoadingScene(nativeFS, sceneFileName)
            if not self.IsSceneLoaded():
                return False

            # The C++ sample's (0, 1.8, 0) -> (1, 1.8, 0) is tuned for a different Sponza
            # distribution; this glTF-Sample-Assets version applies a 0.008 root-node scale,
            # putting its world-space bounds at roughly x:[-15,14] y:[-1,11] z:[-9,9] -- same
            # asset/scale adjustment as variable_shading.py/bindless_rendering.py. The camera's
            # orientation only rotates the whole cubemap basis (CubemapView still captures a
            # full 360 degrees around its position either way), so any reasonable vantage point
            # works.
            self.camera.LookAt(0.0, 1.8, 0.0, 1.0, 1.8, 0.0)
            self.camera.SetMoveSpeed(6.0)

            self.commandList = device.createCommandList()
            self.faceCommandLists = [
                device.createCommandList(pyd.CommandListParameters().setEnableImmediateExecution(False))
                for _ in range(6)
            ]

            self._create_render_targets()

            self.forwardPass = pyd.ForwardShadingPass(device, self.commonPasses)
            forwardParams = pyd.ForwardShadingPassCreateParameters()
            # Raised from the default 16: each of the 6 concurrently-recorded per-face command
            # lists needs its own volatile constant buffer version.
            forwardParams.numConstantBufferVersions = 128
            self.forwardPass.Init(self.shaderFactory, forwardParams)

            # Establish the initial cubemap transform, then render all 6 faces once,
            # sequentially, before the thread pool is ever used. FramebufferFactory's and
            # ForwardShadingPass's internal caches (framebuffers/pipelines/binding sets) are
            # lazily-populated maps with no locking around key insertion; warming them up here
            # means every subsequent concurrent frame only ever does concurrent *reads* of
            # those caches, never concurrent inserts. See docs/superpowers/specs/
            # 2026-07-30-threaded-rendering-example-design.md for the full rationale -- this is
            # a deliberate, narrow deviation from the C++ original (which doesn't warm up and
            # races on its very first frame).
            self.cubemapView.SetTransformFromCamera(self.camera, 0.1, 100.0)
            self.cubemapView.UpdateCache()
            for face in range(6):
                self._render_cube_face(face)

            return True

        def _create_render_targets(self: ThreadedRendering) -> None:
            device = self.GetDevice()

            colorDesc = pyd.TextureDesc()
            colorDesc.dimension = pyd.TextureDimension.TextureCube
            colorDesc.arraySize = 6
            colorDesc.width = _CUBE_RESOLUTION
            colorDesc.height = _CUBE_RESOLUTION
            colorDesc.clearValue = pyd.Color(0.0)
            colorDesc.useClearValue = True
            colorDesc.isRenderTarget = True
            colorDesc.keepInitialState = True
            colorDesc.debugName = "ColorBuffer"
            colorDesc.format = pyd.Format.SRGBA8_UNORM
            colorDesc.initialState = pyd.ResourceStates.RenderTarget
            self.colorCube = device.createTexture(colorDesc)

            depthDesc = pyd.TextureDesc()
            depthDesc.dimension = pyd.TextureDimension.TextureCube
            depthDesc.arraySize = 6
            depthDesc.width = _CUBE_RESOLUTION
            depthDesc.height = _CUBE_RESOLUTION
            depthDesc.clearValue = pyd.Color(0.0)
            depthDesc.useClearValue = True
            depthDesc.isRenderTarget = True
            depthDesc.keepInitialState = True
            depthDesc.debugName = "DepthBuffer"
            depthDesc.format = pyd.Format.D32
            depthDesc.initialState = pyd.ResourceStates.DepthWrite
            self.depthCube = device.createTexture(depthDesc)

            self.cubemapView.SetArrayViewports(_CUBE_RESOLUTION, 0)

            self.framebufferFactory = pyd.FramebufferFactory(device)
            self.framebufferFactory.SetRenderTargets([self.colorCube])
            self.framebufferFactory.depthTarget = self.depthCube

        def LoadScene(self: ThreadedRendering, fs: pyd.IFileSystem, sceneFileName: Path) -> bool:
            assert self.shaderFactory is not None
            assert self.textureCache is not None
            device = self.GetDevice()
            self.scene = pyd.Scene(device, self.shaderFactory, fs, self.textureCache, None)
            return self.scene.Load(sceneFileName)

        def SceneLoaded(self: ThreadedRendering) -> None:
            assert self.textureCache is not None
            assert self.commonPasses is not None
            assert self.scene is not None
            pyd.SceneLoaded(self.textureCache, self.commonPasses)
            self.scene.FinishedLoading(self.GetFrameIndex())

        def KeyboardUpdate(self: ThreadedRendering, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            if key == 32 and action == 1:  # GLFW_KEY_SPACE, GLFW_PRESS
                self.useThreads = not self.useThreads
            return True

        def MousePosUpdate(self: ThreadedRendering, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: ThreadedRendering, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def Animate(self: ThreadedRendering, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)
            suffix = "(With threads)" if self.useThreads else "(No threads)"
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE, extraInfo=suffix)

        def BackBufferResizing(self: ThreadedRendering) -> None:
            assert self.bindingCache is not None
            self.bindingCache.Clear()

        def _render_cube_face(self: ThreadedRendering, face: int) -> None:
            assert self.scene is not None
            assert self.forwardPass is not None
            assert self.framebufferFactory is not None
            assert self.colorCube is not None
            assert self.depthCube is not None

            view = self.cubemapView.GetFaceView(face)
            commandList = self.faceCommandLists[face]

            commandList.open()

            commandList.clearDepthStencilTexture(self.depthCube, True, 0.0, False, 0, view)
            commandList.clearTextureFloat(self.colorCube, pyd.Color(0.0), view)

            # Fresh per-call, never shared across faces/threads -- matches the C++ original,
            # which declares both as local variables inside RenderCubeFace.
            context = pyd.ForwardShadingPassContext()
            self.forwardPass.PrepareLights(context, commandList, [], 1.0, 1.0, 1.0, 0.3, 0.3, 0.3)

            commandList.setEnableAutomaticBarriers(False)
            commandList.setResourceStatesForFramebuffer(self.framebufferFactory.GetFramebuffer(view))
            commandList.commitBarriers()

            strategy = pyd.InstancedOpaqueDrawStrategy()

            pyd.RenderCompositeView(
                commandList, view, view, self.framebufferFactory,
                self.scene.GetSceneGraph().GetRootNode(), strategy, self.forwardPass, context,
            )

            commandList.setEnableAutomaticBarriers(True)
            commandList.close()

        def Render(self: ThreadedRendering, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            assert self.commandList is not None
            assert self.commonPasses is not None
            assert self.bindingCache is not None
            assert self.colorCube is not None
            assert self.executor is not None

            self.cubemapView.SetTransformFromCamera(self.camera, 0.1, 100.0)
            self.cubemapView.UpdateCache()

            futures = None
            if self.useThreads:
                futures = [self.executor.submit(self._render_cube_face, face) for face in range(6)]
            else:
                for face in range(6):
                    self._render_cube_face(face)

            self.commandList.open()

            fbinfo = framebuffer.getFramebufferInfo()
            faceSize = min(fbinfo.width // 4, fbinfo.height // 3)

            for face in range(6):
                col, row = _FACE_LAYOUT[face]
                viewport = pyd.Viewport(
                    float(col * faceSize), float(col * faceSize + faceSize),
                    float(row * faceSize), float(row * faceSize + faceSize),
                    0.0, 1.0,
                )

                blitParams = pyd.BlitParameters()
                blitParams.targetFramebuffer = framebuffer
                blitParams.targetViewport = viewport
                blitParams.sourceTexture = self.colorCube
                blitParams.sourceArraySlice = face
                self.commonPasses.BlitTexture(self.commandList, blitParams, self.bindingCache)

            self.commandList.close()

            if futures is not None:
                # .result() (not just waiting) so a face-render exception surfaces here instead
                # of being silently swallowed by the pool.
                for future in futures:
                    future.result()

            device.executeCommandLists([*self.faceCommandLists, self.commandList])

    is_debug = "-debug" in sys.argv

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures are actually visible here.
    pyd.log.ConsoleApplicationMode()

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")
    if api == pyd.GraphicsAPI.D3D11:
        pyd.log.fatal("The Threaded Rendering example does not support D3D11.")
        sys.exit(1)

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    # Window size matches the layout of the rendered cube faces.
    deviceParams.backBufferWidth = 1024
    deviceParams.backBufferHeight = 768
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        pyd.log.fatal(
            "Cannot initialize a graphics device with the requested parameters"
        )
        sys.exit(1)

    example = ThreadedRendering(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
