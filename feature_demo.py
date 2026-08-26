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
    import math
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

    # Fixed rather than a UI slider: changing it needs the same recreate path as the cascade
    # count, and a demo learns nothing from a resolution slider that the cascade slider does not
    # already show.
    SHADOW_MAP_RESOLUTION = 2048

    # Minimum depth range of the shadow projection along the light direction, in world units:
    # CascadedShadowMap takes max(cascade's own half-extent, this) for each side
    # (CascadedShadowMap.cpp:137-138), so these only matter for the near cascades, where they are
    # what keeps a caster above the camera from falling outside the box. Sized to Sponza with
    # headroom; not UI controls, because the only correct setting is "big enough".
    SHADOW_LIGHT_SPACE_Z_UP = 20.0
    SHADOW_LIGHT_SPACE_Z_DOWN = 20.0

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
            # Not a field of TemporalAntiAliasingParameters -- the jitter pattern lives on
            # the pass itself (TemporalAntiAliasingPass.h:40-46), so it needs its own UI
            # field. MSAA matches both the pass's own default and the C++ sample's.
            self.TemporalAntiAliasingJitter = pyd.TemporalAntiAliasingJitter.MSAA
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
            self.EnableShadows = True
            self.UseStableCascades = True
            self.ShadowCascades = 4
            self.MaxShadowDistance = 50.0
            # Must stay > 1.0: CascadedShadowMap.cpp:83 asserts on it, so a debug build aborts
            # at exactly 1.0.
            self.ShadowExponent = 4.0
            self.ShadowFalloffDistance = 1.0
            self.ShadowLitOutOfBounds = True
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
            self.forwardPass: pyd.ForwardShadingPass | None = None
            self.skyPass: pyd.SkyPass | None = None
            self.ssaoPass: pyd.SsaoPass | None = None
            self.taaPass: pyd.TemporalAntiAliasingPass | None = None
            self.toneMappingPass: pyd.ToneMappingPass | None = None
            self.bloomPass: pyd.BloomPass | None = None
            self.shadowMap: pyd.CascadedShadowMap | None = None
            self.shadowFramebuffer: pyd.FramebufferFactory | None = None
            self.depthPass: pyd.DepthPass | None = None
            self.depthContext = pyd.DepthPassContext()
            self.shadowMapCascades = 0
            self.exposureResetRequired = True
            self.pendingExposureBuffer: pyd.Buffer | None = None
            self.opaqueDrawStrategy = pyd.InstancedOpaqueDrawStrategy()
            self.transparentDrawStrategy = pyd.TransparentDrawStrategy()
            self.descriptorTable: pyd.DescriptorTableManager | None = None
            self.bindlessLayout: pyd.BindingLayout | None = None
            self.previousViewsValid = False
            self.wallclockTime = 0.0

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

            self.forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
            self.forwardPass.Init(
                self.shaderFactory, pyd.ForwardShadingPassCreateParameters()
            )

            # Size-independent, like the other geometry passes: it is created once here and
            # only recreated on a shader reload. depthBias/slopeScaledDepthBias take effect at
            # Init(), which is why they are constants rather than sliders -- a bias slider would
            # mean recreating the pass on every drag.
            depthParams = pyd.DepthPassCreateParameters()
            depthParams.depthBias = 100
            depthParams.slopeScaledDepthBias = 2.0
            self.depthPass = pyd.DepthPass(device, self.m_CommonPasses)
            self.depthPass.Init(self.shaderFactory, depthParams)

            self.CreateShadowMap()

            return True

        def CreateRenderPasses(self: FeatureDemo) -> None:
            """Recreates every size-dependent pass. Called whenever RenderTargets is rebuilt."""
            device = self.GetDevice()
            assert self.renderTargets is not None

            self.bindingCache.Clear()
            self.gbufferPass.ResetBindingCache()
            self.deferredLightingPass.ResetBindingCache()
            self.forwardPass.ResetBindingCache()

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

            self.toneMappingPass = pyd.ToneMappingPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.LdrFramebuffer,
                self.view,
                toneMappingParams,
            )

            # Released only AFTER construction: exposureBufferOverride is a raw
            # nvrhi::IBuffer* (ToneMappingPasses.h:92) that the constructor is what AddRefs
            # (ToneMappingPasses.cpp:103), so this reference is the buffer's only owner right
            # up until the line above returns.
            self.pendingExposureBuffer = None

            self.bloomPass = pyd.BloomPass(
                device,
                self.shaderFactory,
                self.m_CommonPasses,
                self.renderTargets.ResolvedFramebuffer,
                self.view,
            )

        def ReloadShaders(self: FeatureDemo) -> None:
            """Drops every compiled shader and rebuilds the passes holding pipelines from them.

            ShaderFactory reads each .bin blob under bin/shaders once and caches the bytecode,
            and every pass compiles its pipelines at construction -- so a shader rebuilt on
            disk reaches the GPU only if the cache is cleared *and* the pipelines built from
            it are recreated. Doing one without the other silently keeps rendering the old
            shader, which is the failure this method exists to avoid.
            """
            device = self.GetDevice()

            # The outgoing pipelines can still be referenced by frames in flight -- NVRHI
            # retires a released object only once the fence it was last used behind has
            # passed -- and the replacements are built immediately below. Drain first.
            device.waitForIdle()

            self.shaderFactory.ClearCache()

            # CommonRenderPasses compiles the blit and material shaders in its constructor,
            # so it is part of the reload, and it has to be rebuilt before the passes below,
            # which each capture it. Every holder of the outgoing instance is either recreated
            # here or by CreateRenderPasses, so no pass is left rendering against a mix of old
            # and new. (ApplicationBase.m_CommonPasses is a settable property precisely so a
            # Python subclass can do this -- see _pydonut.cpp:2945-2949.)
            self.m_CommonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)

            self.gbufferPass = pyd.GBufferFillPass(device, self.m_CommonPasses)
            self.gbufferPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())

            self.deferredLightingPass = pyd.DeferredLightingPass(device, self.m_CommonPasses)
            self.deferredLightingPass.Init(self.shaderFactory)

            self.forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
            self.forwardPass.Init(
                self.shaderFactory, pyd.ForwardShadingPassCreateParameters()
            )

            # Holds pipelines compiled from the bytecode ClearCache just dropped, so it is
            # rebuilt with the other geometry passes. The shadow map itself holds no shaders and
            # is left alone.
            depthParams = pyd.DepthPassCreateParameters()
            depthParams.depthBias = 100
            depthParams.slopeScaledDepthBias = 2.0
            self.depthPass = pyd.DepthPass(device, self.m_CommonPasses)
            self.depthPass.Init(self.shaderFactory, depthParams)

            # BlitTexture's cached binding sets were built against the *old* CommonRenderPasses'
            # binding layout, so they cannot be reused with the instance created above.
            self.bindingCache.Clear()

            # The size-dependent passes -- sky, SSAO, TAA, tone mapping, bloom -- are rebuilt
            # by Render()'s render-target path rather than here: dropping renderTargets routes
            # the reload through the one release-then-reallocate block that already gets the
            # ordering right (stale binding sets cleared before reallocation, the exposure
            # buffer handed to the replacement tone-mapping pass, TAA history invalidated).
            # Rebuilding them here would duplicate every one of those steps. The cost is one
            # extra render-target reallocation, on a manual button press.
            self.renderTargets = None

        def CreateShadowMap(self: FeatureDemo) -> None:
            """(Re)builds the cascaded shadow map and the framebuffer factory over it.

            Deliberately NOT part of CreateRenderPasses. That runs off
            RenderTargets.IsUpdateRequired(width, height, sampleCount), and this map's size comes
            from the UI, not the back buffer -- folding it in would destroy and reallocate a
            64 MB texture array on every window resize and every AA-mode change, for nothing.

            Called from Init, and again whenever the cascade count changes. The cascade count is
            a construction parameter because the composite view GetView() returns is built once
            in the constructor and never rebuilt (CascadedShadowMap.cpp:67).
            """
            device = self.GetDevice()

            # Dropping self.shadowMap and sunLight.shadowMap is not enough to release the
            # outgoing 64 MB array: DeferredLightingPass.m_BindingSets and
            # ForwardShadingPass.m_ShadingBindingSets are unbounded caches keyed on (among other
            # things) the shadow texture (BindingCache.h:34-36, used at
            # DeferredLightingPass.cpp:266,286; ForwardShadingPass.cpp:395-399 keys directly on
            # the texture handle), so a stale binding set referencing the old texture keeps it
            # GPU-resident until that cache is cleared -- there is no size/count change here for
            # IsUpdateRequired to catch, so nothing else evicts it. ResetBindingCache() on both
            # lighting passes, mirroring the render-target rebuild block below, is what actually
            # makes "the two arrays are never both resident" true: it drops those stale sets
            # before the replacement map is allocated. The light is unhooked first -- it holds a
            # shared_ptr to the outgoing map, so dropping only this reference would keep it
            # alive.
            #
            # depthPass.ResetBindingCache() is deliberately NOT called: it clears material
            # bindings and vertex-buffer SRVs (DepthPass.cpp:91-95), neither of which references
            # the shadow texture. Nothing the pass caches becomes stale when this map is
            # replaced.
            self.shadowMap = None
            self.shadowFramebuffer = None
            if self.sunLight is not None:
                self.sunLight.shadowMap = None
            self.deferredLightingPass.ResetBindingCache()
            self.forwardPass.ResetBindingCache()

            self.shadowMapCascades = self.ui.ShadowCascades
            self.shadowMap = pyd.CascadedShadowMap(
                device,
                SHADOW_MAP_RESOLUTION,
                self.shadowMapCascades,
                0,  # no per-object shadows: they need light types stage 2b binds
                pyd.Format.D32,
                False,
            )
            self.shadowMap.SetFalloffDistance(self.ui.ShadowFalloffDistance)
            self.shadowMap.SetLitOutOfBounds(self.ui.ShadowLitOutOfBounds)

            # One factory serves every cascade: it caches framebuffers per subresource set
            # (FramebufferFactory.cpp:30) and each cascade view carries its own array slice.
            self.shadowFramebuffer = pyd.FramebufferFactory(device)
            self.shadowFramebuffer.depthTarget = self.shadowMap.GetTexture()

        def RenderShadowMap(self: FeatureDemo, commandList: pyd.CommandList) -> None:
            """Fits the cascades to the current view, clears the map and fills every cascade.

            Runs before the G-buffer fill or forward opaque pass: the lighting passes sample this
            texture in the same frame.
            """
            assert self.shadowMap is not None and self.sunLight is not None

            # The two fits differ in what they take off the view -- the tight one the view
            # frustum, the stable one the projection frustum plus the inverse view matrix -- but
            # the binding hides that, so both take the view itself.
            setup = (
                self.shadowMap.SetupForPlanarViewStable
                if self.ui.UseStableCascades
                else self.shadowMap.SetupForPlanarView
            )
            setup(
                self.sunLight,
                self.view,
                self.ui.MaxShadowDistance,
                SHADOW_LIGHT_SPACE_Z_UP,
                SHADOW_LIGHT_SPACE_Z_DOWN,
                self.ui.ShadowExponent,
            )

            self.shadowMap.Clear(commandList)

            # One call fills every cascade: GetView() is the composite of the per-cascade planar
            # views, and RenderCompositeView iterates it. viewPrev is None -- a shadow map has no
            # history, and nothing in a depth-only pass reads motion vectors.
            pyd.RenderCompositeView(
                commandList,
                self.shadowMap.GetView(),
                None,
                self.shadowFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                self.depthPass,
                self.depthContext,
                self.ui.EnableMaterialEvents,
                "ShadowMap",
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
            # UIData.ShowUI is read by UIRenderer.buildUI but had nothing to set it -- without
            # a binding the settings panel can never be dismissed to see the frame behind it.
            # Raw GLFW codes with a comment, the convention the other examples already use
            # (rt_bindless.py:198, threaded_rendering.py:197): no keycode enum is bound.
            if key == 258 and action == 1:  # GLFW_KEY_TAB, GLFW_PRESS
                self.ui.ShowUI = not self.ui.ShowUI

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

            # Pushed every frame rather than only when the checkbox changes: DeviceManager
            # owns the swap-chain present interval and there is no change notification from
            # the UI, so re-asserting the UI's value is what makes the toggle take effect.
            self.GetDeviceManager().SetVsyncEnabled(self.ui.EnableVsync)
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

            # sponza-plus.scene.json's two BrainStem instances ("DancingRobot1/2") carry the
            # only animation clips in the scene; without this they stand frozen in their bind
            # pose. Same wallclock-modulo-duration loop as rt_bindless.py:212-221, including
            # the per-clip offset that keeps the two robots out of lockstep.
            #
            # Apply() only writes scene-graph node transforms. The GPU-side consequences --
            # transform propagation, the skinning compute dispatch, the instance-buffer
            # upload -- all happen in Scene.Refresh(), which Render() calls once the command
            # list is open. The duration guard is for clips that sample to a single keyframe:
            # math.fmod(t, 0.0) raises ValueError rather than returning 0.
            if self.ui.EnableAnimations and self.scene is not None:
                self.wallclockTime += elapsedTimeSeconds
                offset = 0.0
                for anim in self.scene.GetSceneGraph().GetAnimations():
                    duration = anim.GetDuration()
                    if duration > 0.0:
                        anim.Apply(math.fmod(self.wallclockTime + offset, duration))
                    offset += 1.0

            if self.toneMappingPass is not None:
                self.toneMappingPass.AdvanceFrame(elapsedTimeSeconds)

        def SetupView(self: FeatureDemo, width: int, height: int) -> None:
            if self.view is None:
                self.view = pyd.PlanarView()
                self.viewPrevious = pyd.PlanarView()

            # TAA needs a different sub-pixel offset every frame, otherwise TemporalResolve
            # accumulates identical samples and a static camera gets no anti-aliasing at all.
            # Jitter only in TEMPORAL mode, and clear it to (0, 0) in every other mode, so
            # switching away does not leave a stale offset skewing the projection matrix
            # (View.cpp:68-70 folds it into m_PixelOffsetMatrix on UpdateCache).
            # taaPass is None on the first frame, before CreateRenderPasses has run.
            if self.ui.AntiAliasingMode == AntiAliasingMode.TEMPORAL and self.taaPass is not None:
                pixelOffsetX, pixelOffsetY = self.taaPass.GetCurrentPixelOffset()
            else:
                pixelOffsetX, pixelOffsetY = 0.0, 0.0

            viewport = pyd.Viewport(float(width), float(height))
            self.view.SetViewport(viewport)
            self.view.SetPixelOffset(pixelOffsetX, pixelOffsetY)
            self.view.SetMatricesFromCamera(self.camera, width / height)
            self.view.UpdateCache()

        def Render(self: FeatureDemo, framebuffer: pyd.Framebuffer) -> None:
            device = self.GetDevice()
            fbInfo = framebuffer.getFramebufferInfo()
            width, height = fbInfo.width, fbInfo.height
            sampleCount = SAMPLE_COUNTS[self.ui.AntiAliasingMode]

            # Cleared before the reload rather than after, so a pass that throws on rebuild
            # does not re-enter ReloadShaders on every subsequent frame.
            if self.ui.ShaderReloadRequested:
                self.ui.ShaderReloadRequested = False
                self.ReloadShaders()

            # A discrete UI change, not a per-frame check that could thrash: shadowMapCascades is
            # what the current map was built with, so this fires once per slider change.
            if self.ui.ShadowCascades != self.shadowMapCascades:
                self.GetDevice().waitForIdle()
                self.CreateShadowMap()

            # GetCurrentPixelOffset switches on the pass's current jitter mode
            # (TemporalAntiAliasingPass.cpp:335), so the mode has to be pushed in before
            # SetupView reads the offset back out.
            if self.taaPass is not None:
                self.taaPass.SetJitter(self.ui.TemporalAntiAliasingJitter)

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
                # No waitForIdle is needed: NVRHI command lists hold refcounted references to
                # every resource they touch until runGarbageCollection retires the fence, so
                # releasing a Python-side reference cannot free a resource the GPU is still
                # reading.
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
                self.deferredLightingPass.ResetBindingCache()

                # gbufferPass and forwardPass are recreated here, not just reset. Both cache
                # graphics pipelines keyed on the target FramebufferInfo -- sample count
                # included -- and ResetBindingCache() (used above for deferredLightingPass) only
                # drops cached *binding sets*; it does not touch that pipeline cache. On a second
                # MSAA->MSAA rebuild (AA mode 4x -> 8x) the framebuffer's sample count changes
                # under a forwardPass pipeline still cached from the previous rebuild, and
                # NVRHI's validation layer reports exactly that: "The framebuffer used in the
                # draw call does not match the framebuffer used to create the pipeline"
                # (nvrhi/src/validation/validation-commandlist.cpp:640).
                #
                # Measured over a two-switch run (TEMPORAL -> MSAA_4X -> MSAA_8X), counting that
                # message and "Push constant size" separately:
                #
                #   feature_demo.py under test          framebuffer errs   push-constant errs
                #   this file, passes recreated                        0                    0
                #   this file, ResetBindingCache only          1,215,158            1,467,081
                #   stage-1 tip 6b246ae, no shadow code        1,568,414                    0
                #
                # (Counts are per run and the runs differ in length, so they compare only as
                # zero vs. millions.) The framebuffer mismatch is therefore NOT something the
                # shadow work introduced: it reproduces on the stage-1 tip, which contains no
                # shadow code at all. What the shadow work adds is the *second* message.
                # setGraphicsState logs the framebuffer error and returns early
                # (validation-commandlist.cpp:645-648) before it reaches
                # evaluatePushConstantSize (:651), so m_PipelinePushConstantSize keeps the last
                # successful setGraphicsState's value -- with shadows on that is the shadow
                # depth pass (DepthPushConstants, 16 bytes) and the forward pass then pushes 24.
                # With shadows off nothing interleaves, so that counter reads 0 even while the
                # framebuffer mismatch is flooding identically. Recreating the passes zeroes
                # both, which is what says the mismatch itself is gone rather than hidden
                # (.superpowers/sdd/2026-08-26-feature-demo-stage2a-shadows/msaa-regression.md).
                #
                # gbufferPass has the identical pipeline-caching structure; it is only spared
                # today because MSAA forces the deferred path off, leaving its stale-pipeline
                # case unreachable. It is recreated here anyway, symmetrically with forwardPass,
                # so that stays true by construction rather than by an unenforced assumption
                # that nothing will ever flip the deferred path back on under MSAA.
                self.gbufferPass = pyd.GBufferFillPass(device, self.m_CommonPasses)
                self.gbufferPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())
                self.forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
                self.forwardPass.Init(
                    self.shaderFactory, pyd.ForwardShadingPassCreateParameters()
                )
                self.skyPass = None
                self.ssaoPass = None
                self.taaPass = None
                self.bloomPass = None

                # GetExposureBuffer hands Python an owning reference (the binding wraps the
                # returned BufferHandle in DetachToShared), so the buffer survives the old
                # pass's destruction below and stays alive until CreateRenderPasses drops
                # this reference -- after the replacement pass's constructor has AddRef'd it.
                self.pendingExposureBuffer = (
                    self.toneMappingPass.GetExposureBuffer()
                    if self.toneMappingPass is not None
                    else None
                )
                self.toneMappingPass = None

                # TemporalFeedback1/2 come back from Init() with undefined contents --
                # RenderTargets.Clear only clears the G-buffer and HdrColor -- and
                # self.viewPrevious still carries the pre-resize viewport. Both make the
                # history invalid, so the next frame must resolve with feedbackIsValid=False
                # and skip RenderMotionVectors, exactly as on the very first frame.
                self.previousViewsValid = False

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

            # Propagates the node transforms Animate() just wrote through the scene graph and
            # re-runs the skinning compute pass for the animated instances: Scene::Refresh is
            # RefreshSceneGraph + RefreshBuffers (Scene.cpp:793-796), and UpdateSkinnedMeshes
            # (Scene.cpp:707) lives inside the latter -- SceneGraph.Refresh() alone would move
            # the joints without re-skinning the vertices they drive.
            #
            # Unconditional rather than gated on EnableAnimations, matching rt_bindless.py:475.
            # SceneGraph::Refresh walks the whole graph every call -- that walk is what rolls
            # each node's current transform into its previous one (SceneGraph.cpp:979-981),
            # which is in turn what the G-buffer pass differences into motion vectors -- but
            # the per-node work beyond that is gated on dirty flags, and UpdateSkinnedMeshes
            # skips every instance not touched this frame or last (Scene.cpp:718-720). A still
            # scene therefore costs the walk and nothing else, while anything that dirties the
            # graph from outside the animation path still reaches the GPU the frame it happens.
            self.scene.Refresh(self.commandList, self.GetFrameIndex())

            if self.exposureResetRequired:
                self.toneMappingPass.ResetExposure(self.commandList, 0.5)

            self.renderTargets.Clear(self.commandList)

            # Assigning the map to the light is the entire wiring -- both lighting passes read
            # light->shadowMap themselves. None is the off switch, and costs nothing but a null
            # check inside those passes, so the toggle needs no pass rebuild.
            if self.ui.EnableShadows:
                self.RenderShadowMap(self.commandList)
                self.sunLight.shadowMap = self.shadowMap
            else:
                self.sunLight.shadowMap = None

            # RenderCompositeView takes a FramebufferFactory, NOT a Framebuffer
            # (src/cpp/_pydonut.cpp:2473), so pass GBufferFramebuffer -- the factory exposed by
            # Task 6 -- rather than calling GetFramebuffer(view) on it.
            #
            # The UI forces UseDeferredShading off under MSAA, but the UI is not the only path
            # here -- ShowUI can be false, and UIData's defaults are set before any frame runs.
            # Recompute the invariant at the point of use so the deferred path can never be
            # entered with a multisampled, non-UAV HdrColor (FeatureDemo.cpp:1543-1544).
            ambient = self.ui.AmbientIntensity
            useDeferred = (
                self.ui.UseDeferredShading
                and self.renderTargets.gbuffer.GetSampleCount() == 1
            )
            if useDeferred:
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
                    ambient * 0.2, ambient * 0.2, ambient * 0.2,
                    ambient * 0.1, ambient * 0.1, ambient * 0.1,
                )
                deferredInputs.ambientOcclusion = (
                    self.renderTargets.AmbientOcclusion
                    if (self.ui.EnableSsao and self.ssaoPass is not None)
                    else None
                )
                deferredInputs.output = self.renderTargets.HdrColor
                self.deferredLightingPass.Render(self.commandList, self.view, deferredInputs)
            else:
                # Forward opaque. PrepareLights takes the light list plus the same ambient
                # top/bottom colours the deferred path passes to SetAmbientColors.
                forwardContext = pyd.ForwardShadingPassContext()
                self.forwardPass.PrepareLights(
                    forwardContext,
                    self.commandList,
                    self.scene.GetSceneGraph().GetLights(),
                    ambient * 0.2, ambient * 0.2, ambient * 0.2,
                    ambient * 0.1, ambient * 0.1, ambient * 0.1,
                )
                pyd.RenderCompositeView(
                    self.commandList,
                    self.view,
                    self.viewPrevious,
                    self.renderTargets.ForwardFramebuffer,
                    self.scene.GetSceneGraph().GetRootNode(),
                    self.opaqueDrawStrategy,
                    self.forwardPass,
                    forwardContext,
                    self.ui.EnableMaterialEvents,
                )

                if self.ui.EnableTranslucency:
                    pyd.RenderCompositeView(
                        self.commandList,
                        self.view,
                        self.viewPrevious,
                        self.renderTargets.ForwardFramebuffer,
                        self.scene.GetSceneGraph().GetRootNode(),
                        self.transparentDrawStrategy,
                        self.forwardPass,
                        forwardContext,
                        self.ui.EnableMaterialEvents,
                    )

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
                # Paired 1:1 with TemporalResolve, not with the frame: AdvanceFrame also
                # ping-pongs the two resolve binding sets, which is what swaps the feedback
                # pair's history and output roles (TemporalAntiAliasingPass.cpp:300-317).
                # TEMPORAL and NONE share a sample count, so switching between them does not
                # rebuild the pass -- calling this unconditionally would desynchronise the
                # ping-pong from the resolves it belongs to.
                self.taaPass.AdvanceFrame()
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

            # try/finally: SimpleRender is expected to signal GPU-validation failures through
            # log callbacks rather than exceptions (that's why the MSAA runs above logged
            # NVRHI errors instead of raising), but nothing guarantees that stays true --
            # a bare post-call restore would leave the UI's shared params permanently zeroed
            # on any exception, which is exactly the corruption this save/restore exists to
            # prevent.
            try:
                self.toneMappingPass.SimpleRender(
                    self.commandList, toneMappingParams, self.view, finalHdrColor
                )
            finally:
                if savedSpeeds is not None:
                    (
                        toneMappingParams.eyeAdaptationSpeedUp,
                        toneMappingParams.eyeAdaptationSpeedDown,
                    ) = savedSpeeds

            self.m_CommonPasses.BlitTexture(
                self.commandList, framebuffer, self.renderTargets.LdrColor, self.bindingCache
            )

            self.commandList.close()
            device.executeCommandList(self.commandList)

            self.viewPrevious = pyd.PlanarView(self.view)

    class UIRenderer(pyd.ImGui_Renderer):
        def __init__(
            self: UIRenderer, deviceManager: pyd.DeviceManager, app: FeatureDemo, ui: UIData
        ) -> None:
            super().__init__(deviceManager)
            self.app = app
            self.ui = ui
            pyd.ImGui.DisableIniFile()

        def buildUI(self: UIRenderer) -> None:
            if not self.ui.ShowUI:
                return

            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Settings", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            # Rebuild the shaders on disk first (ShaderMake, or another `uv sync`) -- this
            # re-reads the .bin blobs, it does not compile HLSL.
            if pyd.ImGui.Button("Reload Shaders"):
                self.ui.ShaderReloadRequested = True

            aaNames = [m.name for m in AntiAliasingMode]
            changed, index = pyd.ImGui.Combo(
                "AA Mode", int(self.ui.AntiAliasingMode), aaNames
            )
            if changed:
                self.ui.AntiAliasingMode = AntiAliasingMode(index)

            # Deferred shading does not work with MSAA: DeferredLightingPass is a compute
            # pass writing to `output`, but HdrColor is created with isUAV = (sampleCount
            # == 1), so under MSAA there is no UAV to write to and NVRHI validation fires.
            # FeatureDemo.cpp:1543-1544 resolves this by forcing the toggle off, with the
            # comment "Deferred shading doesn't work with MSAA". Mirror that here.
            msaaActive = self.ui.AntiAliasingMode >= AntiAliasingMode.MSAA_2X
            if msaaActive:
                self.ui.UseDeferredShading = False

            _, self.ui.UseDeferredShading = pyd.ImGui.Checkbox(
                "Deferred Shading", self.ui.UseDeferredShading
            )
            if msaaActive:
                pyd.ImGui.SameLine()
                pyd.ImGui.Text("(forced off under MSAA)")

            _, self.ui.AmbientIntensity = pyd.ImGui.SliderFloat(
                "Ambient Intensity", self.ui.AmbientIntensity, 0.0, 2.0
            )

            _, self.ui.EnableVsync = pyd.ImGui.Checkbox("VSync", self.ui.EnableVsync)

            _, self.ui.EnableAnimations = pyd.ImGui.Checkbox(
                "Animations", self.ui.EnableAnimations
            )

            _, self.ui.EnableMaterialEvents = pyd.ImGui.Checkbox(
                "Material Events", self.ui.EnableMaterialEvents
            )

            # Translucent geometry is drawn by a second RenderCompositeView over the
            # transparent draw strategy, which only the forward path issues -- the deferred
            # path has no equivalent, so say so rather than leaving a toggle that silently
            # does nothing.
            _, self.ui.EnableTranslucency = pyd.ImGui.Checkbox(
                "Translucency", self.ui.EnableTranslucency
            )
            if self.ui.UseDeferredShading:
                pyd.ImGui.SameLine()
                pyd.ImGui.Text("(forward path only)")

            if pyd.ImGui.CollapsingHeader("Shadows"):
                _, self.ui.EnableShadows = pyd.ImGui.Checkbox("Enabled", self.ui.EnableShadows)

                _, self.ui.UseStableCascades = pyd.ImGui.Checkbox(
                    "Stable Cascades", self.ui.UseStableCascades
                )
                pyd.ImGui.SameLine()
                pyd.ImGui.Text("(off = tighter fit, edges shimmer when turning)")

                # Changing the count recreates the shadow map: the composite view is built once
                # in the constructor, so the count cannot be lowered in place without leaving
                # GetView() rendering slices that were never set up.
                #
                # A Combo, not a slider: ImGui.SliderInt is not bound (only SliderFloat is), and
                # four discrete values do not need one. The index is the count minus one.
                changed, cascadeIndex = pyd.ImGui.Combo(
                    "Cascades", self.ui.ShadowCascades - 1, ["1", "2", "3", "4"]
                )
                if changed:
                    self.ui.ShadowCascades = cascadeIndex + 1

                _, self.ui.MaxShadowDistance = pyd.ImGui.SliderFloat(
                    "Max Distance", self.ui.MaxShadowDistance, 5.0, 200.0
                )
                # Lower bound is 1.01, not 1.0: CascadedShadowMap.cpp:83 asserts exponent > 1,
                # so a debug build aborts at exactly 1.0.
                _, self.ui.ShadowExponent = pyd.ImGui.SliderFloat(
                    "Cascade Distribution", self.ui.ShadowExponent, 1.01, 8.0
                )

                changed, falloff = pyd.ImGui.SliderFloat(
                    "Falloff Distance", self.ui.ShadowFalloffDistance, 0.0, 10.0
                )
                if changed and self.app.shadowMap is not None:
                    self.ui.ShadowFalloffDistance = falloff
                    self.app.shadowMap.SetFalloffDistance(falloff)

                changed, litOutOfBounds = pyd.ImGui.Checkbox(
                    "Lit Out Of Bounds", self.ui.ShadowLitOutOfBounds
                )
                if changed and self.app.shadowMap is not None:
                    self.ui.ShadowLitOutOfBounds = litOutOfBounds
                    self.app.shadowMap.SetLitOutOfBounds(litOutOfBounds)

            if pyd.ImGui.CollapsingHeader("Sky"):
                _, self.ui.EnableProceduralSky = pyd.ImGui.Checkbox(
                    "Procedural Sky", self.ui.EnableProceduralSky
                )
                _, self.ui.SkyParams.brightness = pyd.ImGui.SliderFloat(
                    "Brightness", self.ui.SkyParams.brightness, 0.0, 1.0
                )
                _, self.ui.SkyParams.glowSize = pyd.ImGui.SliderFloat(
                    "Glow Size", self.ui.SkyParams.glowSize, 0.0, 90.0
                )
                _, self.ui.SkyParams.glowIntensity = pyd.ImGui.SliderFloat(
                    "Glow Intensity", self.ui.SkyParams.glowIntensity, 0.0, 1.0
                )

            if pyd.ImGui.CollapsingHeader("SSAO"):
                _, self.ui.EnableSsao = pyd.ImGui.Checkbox("Enabled", self.ui.EnableSsao)
                if self.app.ssaoPass is None:
                    pyd.ImGui.SameLine()
                    pyd.ImGui.Text("(unavailable under MSAA)")
                _, self.ui.SsaoParams.amount = pyd.ImGui.SliderFloat(
                    "Amount", self.ui.SsaoParams.amount, 0.0, 8.0
                )
                _, self.ui.SsaoParams.radiusWorld = pyd.ImGui.SliderFloat(
                    "Radius", self.ui.SsaoParams.radiusWorld, 0.01, 2.0
                )
                _, self.ui.SsaoParams.surfaceBias = pyd.ImGui.SliderFloat(
                    "Surface Bias", self.ui.SsaoParams.surfaceBias, 0.0, 1.0
                )
                _, self.ui.SsaoParams.powerExponent = pyd.ImGui.SliderFloat(
                    "Power Exponent", self.ui.SsaoParams.powerExponent, 1.0, 4.0
                )

            if pyd.ImGui.CollapsingHeader("Temporal AA"):
                if self.ui.AntiAliasingMode != AntiAliasingMode.TEMPORAL:
                    pyd.ImGui.Text("(inactive -- AA Mode is not TEMPORAL)")

                # Indexed through the member list rather than by .value: the enum is bound as
                # a plain enum.Enum (not IntEnum), so its members do not convert to the combo's
                # int index on their own and nothing guarantees the values stay 0..n-1.
                jitterModes = list(pyd.TemporalAntiAliasingJitter)
                changed, jitterIndex = pyd.ImGui.Combo(
                    "Jitter",
                    jitterModes.index(self.ui.TemporalAntiAliasingJitter),
                    [j.name for j in jitterModes],
                )
                if changed:
                    self.ui.TemporalAntiAliasingJitter = jitterModes[jitterIndex]

                taaParams = self.ui.TemporalAntiAliasingParams
                _, taaParams.newFrameWeight = pyd.ImGui.SliderFloat(
                    "New Frame Weight", taaParams.newFrameWeight, 0.001, 1.0
                )
                _, taaParams.enableHistoryClamping = pyd.ImGui.Checkbox(
                    "History Clamping", taaParams.enableHistoryClamping
                )
                _, taaParams.clampingFactor = pyd.ImGui.SliderFloat(
                    "Clamping Factor", taaParams.clampingFactor, 0.0, 3.0
                )
                # DragFloat, not SliderFloat: the useful range spans four orders of magnitude
                # around the 10000 default, which a linear slider cannot resolve at the low end.
                _, taaParams.maxRadiance = pyd.ImGui.DragFloat(
                    "Max Radiance", taaParams.maxRadiance, 10.0, 1.0, 100000.0
                )
                # useHistoryClampRelax is deliberately not offered: it needs the
                # historyClampRelax mask texture, which nothing in this repo builds and which
                # is left unbound for that reason (src/pydonut/_pydonut.pyi:1357-1358).

            if pyd.ImGui.CollapsingHeader("Bloom"):
                _, self.ui.EnableBloom = pyd.ImGui.Checkbox("Enabled", self.ui.EnableBloom)
                _, self.ui.BloomSigma = pyd.ImGui.SliderFloat(
                    "Sigma", self.ui.BloomSigma, 1.0, 100.0
                )
                _, self.ui.BloomAlpha = pyd.ImGui.SliderFloat(
                    "Alpha", self.ui.BloomAlpha, 0.0, 1.0
                )

            if pyd.ImGui.CollapsingHeader("Tone Mapping"):
                _, self.ui.ToneMappingParams.exposureBias = pyd.ImGui.SliderFloat(
                    "Exposure Bias", self.ui.ToneMappingParams.exposureBias, -4.0, 4.0
                )
                _, self.ui.ToneMappingParams.whitePoint = pyd.ImGui.SliderFloat(
                    "White Point", self.ui.ToneMappingParams.whitePoint, 0.1, 10.0
                )
                _, self.ui.ToneMappingParams.eyeAdaptationSpeedUp = pyd.ImGui.SliderFloat(
                    "Adaptation Up", self.ui.ToneMappingParams.eyeAdaptationSpeedUp, 0.0, 4.0
                )
                _, self.ui.ToneMappingParams.eyeAdaptationSpeedDown = pyd.ImGui.SliderFloat(
                    "Adaptation Down", self.ui.ToneMappingParams.eyeAdaptationSpeedDown, 0.0, 4.0
                )

            pyd.ImGui.End()

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
    gui = UIRenderer(deviceManager, example, uiData)

    if example.Init() and gui.Init(example.shaderFactory):
        deviceManager.AddRenderPassToBack(example)
        deviceManager.AddRenderPassToBack(gui)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(gui)
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    # Same placement and gating as deferred_shading.py:383-384 -- after Shutdown(), so
    # anything still reported is genuinely leaked rather than merely not yet torn down.
    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
