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

"""Port of Donut's FeatureDemo sample -- stage 1 of 3.

Renders media/sponza-plus.scene.json through the full HDR pipeline: deferred or forward
shading, a procedural sky, SSAO, TAA or MSAA, bloom, and tone mapping with eye adaptation.

Stage 1 deliberately omits shadows, light probes, material/light editors, the scene-camera
dropdown, MaterialID readback, MipMapGen, stereo and screenshots -- those arrive in stages 2
and 3. DLSS, taskflow and the ImGui console are out of scope permanently: see
docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md.

NOTE: sponza-plus.scene.json declares no lights at all, so the directional "Sun" light this
example renders with is created here and attached to the scene graph, not loaded.
"""

from __future__ import annotations

if __name__ == "__main__":
    import sys
    from enum import IntEnum
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Feature Demo"
    folder = Path(__file__).resolve().parent

    _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE = 64

    class AntiAliasingMode(IntEnum):
        """No DLSS entry -- it needs the NGX SDK, which this repo does not vendor."""

        NONE = 0
        TEMPORAL = 1
        MSAA_2X = 2
        MSAA_4X = 3
        MSAA_8X = 4

    SAMPLE_COUNTS = {
        AntiAliasingMode.NONE: 1,
        AntiAliasingMode.TEMPORAL: 1,
        AntiAliasingMode.MSAA_2X: 2,
        AntiAliasingMode.MSAA_4X: 4,
        AntiAliasingMode.MSAA_8X: 8,
    }

    class UIData:
        """Shared by reference between FeatureDemo and UIRenderer.

        Same convention as work_graphs.py, rt_particles.py and aftermath.py: one plain object
        held by both, rather than the C++ original's UIRenderer-holds-FeatureDemo& plus setters.
        """

        def __init__(self: UIData) -> None:
            self.ShowUI = True
            self.UseDeferredShading = True
            self.EnableSsao = True
            self.SsaoParams = pyd.SsaoParameters()
            self.ToneMappingParams = pyd.ToneMappingParameters()
            self.TemporalAntiAliasingParams = pyd.TemporalAntiAliasingParameters()
            self.SkyParams = pyd.SkyParameters()
            self.AntiAliasingMode = AntiAliasingMode.TEMPORAL
            self.EnableVsync = True
            self.EnableProceduralSky = True
            self.EnableBloom = True
            self.BloomSigma = 32.0
            self.BloomAlpha = 0.05
            self.EnableTranslucency = True
            self.EnableMaterialEvents = False
            self.AmbientIntensity = 1.0
            self.EnableAnimations = False
            self.ShaderReloadRequested = False

    class RenderTargets:
        """Composes a pyd.GBufferRenderTargets with the extra HDR/LDR targets the sample needs.

        The C++ original derives from GBufferRenderTargets and overrides Init. Composition
        works here because the one place the object is used polymorphically --
        DeferredLightingPassInputs.SetGBuffer -- takes the base class, which .gbuffer is.
        """

        def __init__(self: RenderTargets) -> None:
            self.gbuffer = pyd.GBufferRenderTargets()
            self.HdrColor: pyd.Texture | None = None
            self.LdrColor: pyd.Texture | None = None
            self.ResolvedColor: pyd.Texture | None = None
            self.TemporalFeedback1: pyd.Texture | None = None
            self.TemporalFeedback2: pyd.Texture | None = None
            self.AmbientOcclusion: pyd.Texture | None = None
            self.ForwardFramebuffer: pyd.FramebufferFactory | None = None
            self.HdrFramebuffer: pyd.FramebufferFactory | None = None
            self.LdrFramebuffer: pyd.FramebufferFactory | None = None
            self.ResolvedFramebuffer: pyd.FramebufferFactory | None = None
            self.width = 0
            self.height = 0
            self.sampleCount = 0

        def Init(
            self: RenderTargets, device: pyd.Device, width: int, height: int, sampleCount: int
        ) -> None:
            self.gbuffer.Init(device, width, height, sampleCount, True, True)
            self.width, self.height, self.sampleCount = width, height, sampleCount

            isMultisampled = sampleCount > 1

            def makeColor(fmt: pyd.Format, name: str, allowUav: bool) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = width
                desc.height = height
                desc.isRenderTarget = True
                desc.useClearValue = True
                desc.clearValue = pyd.Color(0.0)
                desc.sampleCount = sampleCount
                desc.dimension = (
                    pyd.TextureDimension.Texture2DMS
                    if isMultisampled
                    else pyd.TextureDimension.Texture2D
                )
                desc.keepInitialState = True
                desc.isTypeless = False
                desc.isUAV = allowUav and not isMultisampled
                desc.format = fmt
                desc.initialState = pyd.ResourceStates.RenderTarget
                desc.debugName = name
                return device.createTexture(desc)

            self.HdrColor = makeColor(pyd.Format.RGBA16_FLOAT, "HdrColor", True)

            # ResolvedColor and the TAA feedback pair are always single-sampled: they are the
            # *output* of resolving, so they must not themselves be multisampled.
            def makeSingleSampled(fmt: pyd.Format, name: str, isUav: bool) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = width
                desc.height = height
                desc.isRenderTarget = True
                desc.useClearValue = True
                desc.clearValue = pyd.Color(0.0)
                desc.sampleCount = 1
                desc.dimension = pyd.TextureDimension.Texture2D
                desc.keepInitialState = True
                desc.isTypeless = False
                desc.isUAV = isUav
                desc.format = fmt
                desc.initialState = pyd.ResourceStates.RenderTarget
                desc.debugName = name
                return device.createTexture(desc)

            self.ResolvedColor = makeSingleSampled(pyd.Format.RGBA16_FLOAT, "ResolvedColor", True)
            self.TemporalFeedback1 = makeSingleSampled(pyd.Format.RGBA16_SNORM, "TemporalFeedback1", True)
            self.TemporalFeedback2 = makeSingleSampled(pyd.Format.RGBA16_SNORM, "TemporalFeedback2", True)
            self.LdrColor = makeSingleSampled(pyd.Format.SRGBA8_UNORM, "LdrColor", False)
            self.AmbientOcclusion = makeSingleSampled(pyd.Format.R8_UNORM, "AmbientOcclusion", True)

            depth = self.gbuffer.Depth

            self.ForwardFramebuffer = pyd.FramebufferFactory(device)
            self.ForwardFramebuffer.SetRenderTargets([self.HdrColor])
            self.ForwardFramebuffer.depthTarget = depth

            self.HdrFramebuffer = pyd.FramebufferFactory(device)
            self.HdrFramebuffer.SetRenderTargets([self.HdrColor])

            self.LdrFramebuffer = pyd.FramebufferFactory(device)
            self.LdrFramebuffer.SetRenderTargets([self.LdrColor])

            self.ResolvedFramebuffer = pyd.FramebufferFactory(device)
            self.ResolvedFramebuffer.SetRenderTargets([self.ResolvedColor])

        def IsUpdateRequired(
            self: RenderTargets, width: int, height: int, sampleCount: int
        ) -> bool:
            """Not a GBufferRenderTargets method -- the C++ sample defines this on its own
            derived class (FeatureDemo.cpp:213), so it lives in Python here."""
            return (
                self.width != width
                or self.height != height
                or self.sampleCount != sampleCount
            )

        def Clear(self: RenderTargets, commandList: pyd.CommandList) -> None:
            self.gbuffer.Clear(commandList)
            commandList.clearTextureFloat(self.HdrColor, pyd.Color(0.0))

    class FeatureDemo(pyd.ApplicationBase):
        def __init__(self: FeatureDemo, deviceManager: pyd.DeviceManager, ui: UIData) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            self.rootFS = pyd.RootFileSystem()
            self.nativeFS = pyd.NativeFileSystem()
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.scene: pyd.Scene | None = None
            self.sunLight: pyd.DirectionalLight | None = None
            self.renderTargets: RenderTargets | None = None
            self.view: pyd.PlanarView | None = None
            self.viewPrevious: pyd.PlanarView | None = None
            self.camera = pyd.FirstPersonCamera()
            self.commandList: pyd.CommandList | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.gbufferPass: pyd.GBufferFillPass | None = None
            self.deferredLightingPass: pyd.DeferredLightingPass | None = None
            self.skyPass: pyd.SkyPass | None = None
            self.ssaoPass: pyd.SsaoPass | None = None
            self.taaPass: pyd.TemporalAntiAliasingPass | None = None
            self.toneMappingPass: pyd.ToneMappingPass | None = None
            self.bloomPass: pyd.BloomPass | None = None
            self.exposureResetRequired = True
            self.pendingExposureBuffer: pyd.Buffer | None = None
            self.opaqueDrawStrategy = pyd.InstancedOpaqueDrawStrategy()
            self.transparentDrawStrategy = pyd.TransparentDrawStrategy()
            self.descriptorTable: pyd.DescriptorTableManager | None = None
            self.bindlessLayout: pyd.BindingLayout | None = None
            self.previousViewsValid = False

        def Init(self: FeatureDemo) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            frameworkShaderPath = (
                folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            )
            self.rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.shaderFactory = pyd.ShaderFactory(device, self.rootFS, Path("/shaders"))

            self.commandList = device.createCommandList()
            self.bindingCache = pyd.BindingCache(device)

            # DescriptorTableManager takes (device, layout) -- it needs a bindless layout, not
            # just a device. Same construction as bindless_rendering.py:116-124.
            bindlessLayoutDesc = pyd.BindlessLayoutDesc()
            bindlessLayoutDesc.visibility = pyd.ShaderType.All
            bindlessLayoutDesc.firstSlot = 0
            bindlessLayoutDesc.maxCapacity = 1024
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.RawBuffer_SRV(1))
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.Texture_SRV(2))
            self.bindlessLayout = device.createBindlessLayout(bindlessLayoutDesc)
            self.descriptorTable = pyd.DescriptorTableManager(device, self.bindlessLayout)

            self.m_CommonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.m_TextureCache = pyd.TextureCache(device, self.nativeFS, self.descriptorTable)

            # Synchronous load: the async path is not exercised by any existing example.
            self.SetAsynchronousLoadingEnabled(False)

            scenePath = folder / "media" / "sponza-plus.scene.json"
            self.scene = pyd.Scene(
                device,
                self.shaderFactory,
                self.nativeFS,
                self.m_TextureCache,
                self.descriptorTable,
            )
            if not self.scene.Load(scenePath):
                pyd.log.fatal(f"Failed to load {scenePath}")
                return False

            self.CreateSunLight()
            self.scene.FinishedLoading(self.GetFrameIndex())

            self.camera.LookAt(0.0, 1.8, 0.0, 1.0, 1.8, 0.0)
            self.camera.SetMoveSpeed(3.0)

            self.gbufferPass = pyd.GBufferFillPass(device, self.m_CommonPasses)
            self.gbufferPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())

            self.deferredLightingPass = pyd.DeferredLightingPass(device, self.m_CommonPasses)
            self.deferredLightingPass.Init(self.shaderFactory)

            return True

        def CreateRenderPasses(self: FeatureDemo) -> None:
            """Recreates every size-dependent pass. Called whenever RenderTargets is rebuilt."""
            device = self.GetDevice()
            assert self.renderTargets is not None

            self.bindingCache.Clear()
            self.gbufferPass.ResetBindingCache()
            self.deferredLightingPass.ResetBindingCache()

            self.skyPass = pyd.SkyPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.ForwardFramebuffer,
                self.view,
            )

            # SSAO is only available without MSAA: its compute path reads a single-sampled
            # depth buffer (FeatureDemo.cpp:825 guards on GetSampleCount() == 1).
            if self.renderTargets.gbuffer.GetSampleCount() == 1:
                self.ssaoPass = pyd.SsaoPass(
                    device,
                    self.shaderFactory,
                    self.m_CommonPasses,
                    self.renderTargets.gbuffer.Depth,
                    self.renderTargets.gbuffer.GBufferNormals,
                    self.renderTargets.AmbientOcclusion,
                )
            else:
                self.ssaoPass = None

            taaParams = pyd.TemporalAntiAliasingCreateParameters()
            taaParams.sourceDepth = self.renderTargets.gbuffer.Depth
            taaParams.motionVectors = self.renderTargets.gbuffer.MotionVectors
            taaParams.unresolvedColor = self.renderTargets.HdrColor
            taaParams.resolvedColor = self.renderTargets.ResolvedColor
            taaParams.feedback1 = self.renderTargets.TemporalFeedback1
            taaParams.feedback2 = self.renderTargets.TemporalFeedback2
            self.taaPass = pyd.TemporalAntiAliasingPass(
                device, self.shaderFactory, self.m_CommonPasses, self.view, taaParams
            )

            # Carry the outgoing pass's exposure buffer into its replacement, so eye
            # adaptation survives the resize instead of re-adapting from black
            # (FeatureDemo.cpp:831-840). Driven from self.pendingExposureBuffer, captured
            # in the release block in Render() -- NOT from self.toneMappingPass, which has
            # already been set to None by the time this runs.
            toneMappingParams = pyd.ToneMappingPassCreateParameters()
            if self.pendingExposureBuffer is not None:
                toneMappingParams.exposureBufferOverride = self.pendingExposureBuffer
                self.exposureResetRequired = False
            else:
                self.exposureResetRequired = True
            self.pendingExposureBuffer = None

            self.toneMappingPass = pyd.ToneMappingPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.LdrFramebuffer,
                self.view,
                toneMappingParams,
            )

            self.bloomPass = pyd.BloomPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.ResolvedFramebuffer,
                self.view,
            )

        def CreateSunLight(self: FeatureDemo) -> None:
            """sponza-plus.scene.json declares no lights, so the sun is always synthesised
            here -- this mirrors FeatureDemo.cpp:619-627, which treats it as a fallback.

            AttachLeafNode(parent, leaf) takes the SceneGraphLeaf directly (DirectionalLight
            IS-A Light IS-A SceneGraphLeaf) and creates/returns the wrapping SceneGraphNode
            itself -- see deferred_shading.py:242-247 for the identical working pattern. A
            separately-constructed SceneGraphNode is never passed as the `leaf` argument; that
            is a type mismatch against the bound signature (src/pydonut/_pydonut.pyi:1121).
            """
            assert self.scene is not None
            graph = self.scene.GetSceneGraph()

            for light in graph.GetLights():
                if isinstance(light, pyd.DirectionalLight):
                    self.sunLight = light
                    if self.sunLight.irradiance <= 0.0:
                        self.sunLight.irradiance = 1.0
                    return

            self.sunLight = pyd.DirectionalLight()
            self.sunLight.angularSize = 0.53
            self.sunLight.irradiance = 1.0
            self.sunLight.SetName("Sun")

            graph.AttachLeafNode(graph.GetRootNode(), self.sunLight)
            self.sunLight.SetDirection(0.1, -0.9, 0.1)

            graph.Refresh(0)

        def KeyboardUpdate(self: FeatureDemo, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            return True

        def MousePosUpdate(self: FeatureDemo, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: FeatureDemo, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def BackBufferResizing(self: FeatureDemo) -> None:
            self.renderTargets = None
            self.bindingCache.Clear()

        def Animate(self: FeatureDemo, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

            if self.toneMappingPass is not None:
                self.toneMappingPass.AdvanceFrame(elapsedTimeSeconds)

        def SetupView(self: FeatureDemo, width: int, height: int) -> None:
            if self.view is None:
                self.view = pyd.PlanarView()
                self.viewPrevious = pyd.PlanarView()

            viewport = pyd.Viewport(float(width), float(height))
            self.view.SetViewport(viewport)
            self.view.SetMatricesFromCamera(self.camera, width / height)
            self.view.UpdateCache()

        def Render(self: FeatureDemo, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            fbInfo = framebuffer.getFramebufferInfo()
            width, height = fbInfo.width, fbInfo.height
            sampleCount = SAMPLE_COUNTS[self.ui.AntiAliasingMode]

            # CreateRenderPasses reads self.view (SkyPass's constructor takes the composite
            # view), so SetupView must run before it -- and before the rebuild block below,
            # since that block calls CreateRenderPasses once the new targets exist.
            self.SetupView(width, height)

            if self.renderTargets is None or self.renderTargets.IsUpdateRequired(
                width, height, sampleCount
            ):
                # Release the old targets and drop every cached binding set that references
                # them BEFORE allocating replacements, mirroring FeatureDemo.cpp:899-904.
                # The binding caches hold nvrhi BindingSetHandles pointing at the old
                # textures, so dropping the Python reference alone does not free them --
                # without clearing first, the old and new render-target sets are both
                # resident during Init(), doubling peak VRAM on every resize and AA switch
                # (worst at 8x MSAA, where the G-buffer and HdrColor are all multisampled).
                # No waitForIdle is needed: nvrhi defers destruction of in-flight resources.
                #
                # skyPass and ssaoPass hold the same kind of stale binding sets (referencing
                # ForwardFramebuffer/HdrColor, gbuffer.Depth, gbuffer.GBufferNormals and
                # AmbientOcclusion) but expose no ResetBindingCache/Clear method -- dropping
                # the Python reference is the only way to release them, so they must be set to
                # None here too, not just reassigned in CreateRenderPasses() below. Any future
                # size-dependent pass added to CreateRenderPasses needs the same treatment: if
                # it has no cache-reset method, release it here before Init() rather than only
                # reassigning it later.
                self.renderTargets = None
                self.bindingCache.Clear()
                self.gbufferPass.ResetBindingCache()
                self.deferredLightingPass.ResetBindingCache()
                self.skyPass = None
                self.ssaoPass = None
                self.taaPass = None
                self.bloomPass = None

                # GetExposureBuffer is return_value_policy::reference_internal, so holding the
                # buffer keeps the old pass alive until the new one AddRefs it -- capturing
                # before releasing is what makes this safe rather than a dangling handle.
                self.pendingExposureBuffer = (
                    self.toneMappingPass.GetExposureBuffer()
                    if self.toneMappingPass is not None
                    else None
                )
                self.toneMappingPass = None

                self.renderTargets = RenderTargets()
                self.renderTargets.Init(device, width, height, sampleCount)

                # CreateRenderPasses asserts self.renderTargets is not None and reads its
                # freshly-allocated textures, so it must run after Init() above, not in place
                # of the clear-before-allocate block -- otherwise the sky/SSAO passes would be
                # built one frame too early and the VRAM-doubling ordering above would be lost.
                # Its own bindingCache.Clear()/ResetBindingCache() calls are therefore a cheap,
                # idempotent no-op here (the caches are already empty); this only runs on
                # resize/AA-mode change, not per frame.
                self.CreateRenderPasses()

            self.commandList.open()

            if self.exposureResetRequired:
                self.toneMappingPass.ResetExposure(self.commandList, 0.5)

            self.renderTargets.Clear(self.commandList)

            # RenderCompositeView takes a FramebufferFactory, NOT a Framebuffer
            # (src/cpp/_pydonut.cpp:2473), so pass GBufferFramebuffer -- the factory exposed by
            # Task 6 -- rather than calling GetFramebuffer(view) on it.
            gbufferContext = pyd.GBufferFillPassContext()
            pyd.RenderCompositeView(
                self.commandList,
                self.view,
                self.viewPrevious,
                self.renderTargets.gbuffer.GBufferFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                self.gbufferPass,
                gbufferContext,
                self.ui.EnableMaterialEvents,
            )

            if self.ui.EnableSsao and self.ssaoPass is not None:
                self.ssaoPass.Render(self.commandList, self.ui.SsaoParams, self.view)

            deferredInputs = pyd.DeferredLightingPassInputs()
            deferredInputs.SetGBuffer(self.renderTargets.gbuffer)
            deferredInputs.SetLights(self.scene.GetSceneGraph().GetLights())
            deferredInputs.SetAmbientColors(
                self.ui.AmbientIntensity * 0.2,
                self.ui.AmbientIntensity * 0.2,
                self.ui.AmbientIntensity * 0.2,
                self.ui.AmbientIntensity * 0.1,
                self.ui.AmbientIntensity * 0.1,
                self.ui.AmbientIntensity * 0.1,
            )
            deferredInputs.ambientOcclusion = (
                self.renderTargets.AmbientOcclusion
                if (self.ui.EnableSsao and self.ssaoPass is not None)
                else None
            )
            deferredInputs.output = self.renderTargets.HdrColor
            self.deferredLightingPass.Render(self.commandList, self.view, deferredInputs)

            if self.ui.EnableProceduralSky and self.sunLight is not None:
                self.skyPass.Render(
                    self.commandList, self.view, self.sunLight, self.ui.SkyParams
                )

            finalHdrColor = self.renderTargets.HdrColor
            finalHdrFramebuffer = self.renderTargets.HdrFramebuffer

            if self.ui.AntiAliasingMode == AntiAliasingMode.TEMPORAL:
                if self.previousViewsValid:
                    self.taaPass.RenderMotionVectors(
                        self.commandList, self.view, self.viewPrevious
                    )
                self.taaPass.TemporalResolve(
                    self.commandList,
                    self.ui.TemporalAntiAliasingParams,
                    self.previousViewsValid,
                    self.view,
                    self.view,
                )
                finalHdrColor = self.renderTargets.ResolvedColor
                finalHdrFramebuffer = self.renderTargets.ResolvedFramebuffer
                self.previousViewsValid = True
            else:
                if self.renderTargets.gbuffer.GetSampleCount() > 1:
                    self.commandList.resolveTexture(
                        self.renderTargets.ResolvedColor, self.renderTargets.HdrColor
                    )
                    finalHdrColor = self.renderTargets.ResolvedColor
                    finalHdrFramebuffer = self.renderTargets.ResolvedFramebuffer
                self.previousViewsValid = False

            if self.ui.EnableBloom:
                self.bloomPass.Render(
                    self.commandList,
                    finalHdrFramebuffer,
                    self.view,
                    finalHdrColor,
                    self.ui.BloomSigma,
                    self.ui.BloomAlpha,
                )

            # self.ui.ToneMappingParams is aliased, not copied: pyd.ToneMappingParameters has
            # no copy constructor, and unlike the C++ original's local struct copy
            # ("ToneMappingParameters toneMappingParams = m_ui.ToneMappingParams;"),
            # `toneMappingParams = self.ui.ToneMappingParams` in Python binds the *same*
            # object. Mutating the speed fields directly would therefore permanently zero
            # eye adaptation on the UI's shared params the first time a reset fires (frame 1
            # of every run) -- save/restore around the single SimpleRender call instead, so
            # the one-frame-zero-speed effect stays local like the C++ copy achieves for free.
            toneMappingParams = self.ui.ToneMappingParams
            savedSpeeds = None
            if self.exposureResetRequired:
                savedSpeeds = (
                    toneMappingParams.eyeAdaptationSpeedUp,
                    toneMappingParams.eyeAdaptationSpeedDown,
                )
                toneMappingParams.eyeAdaptationSpeedUp = 0.0
                toneMappingParams.eyeAdaptationSpeedDown = 0.0
                self.exposureResetRequired = False

            self.toneMappingPass.SimpleRender(
                self.commandList, toneMappingParams, self.view, finalHdrColor
            )

            if savedSpeeds is not None:
                toneMappingParams.eyeAdaptationSpeedUp, toneMappingParams.eyeAdaptationSpeedDown = savedSpeeds

            self.m_CommonPasses.BlitTexture(
                self.commandList, framebuffer, self.renderTargets.LdrColor, self.bindingCache
            )

            self.commandList.close()
            device.executeCommandList(self.commandList)

            self.viewPrevious = pyd.PlanarView(self.view)

    is_debug = "-debug" in sys.argv

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures are actually visible here (same
    # convention as deferred_shading.py and most other examples).
    pyd.log.ConsoleApplicationMode()

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    deviceParams.backBufferWidth = 1920
    deviceParams.backBufferHeight = 1080
    deviceParams.swapChainSampleCount = 1
    deviceParams.swapChainBufferCount = 3
    deviceParams.startFullscreen = False
    deviceParams.vsyncEnabled = True
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    uiData = UIData()
    example = FeatureDemo(deviceManager, uiData)

    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager

    print("Done.")
