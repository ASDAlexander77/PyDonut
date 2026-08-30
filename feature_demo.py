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

"""Port of Donut's FeatureDemo sample -- stages 1, 2a, 2b, 2c, 3a and 3b.

Renders media/sponza-plus.scene.json through the full HDR pipeline: deferred or forward
shading, a procedural sky, SSAO, TAA or MSAA, bloom, and tone mapping with eye adaptation,
with cascaded sun shadows, a spot and a point light, a switchable first-person/third-person/
scene camera, live light and material editors, right-click material picking, screenshots, a
MipMapGen test pass, a side-by-side stereo mode and four capturable light probes.

This completes the port. DLSS, taskflow and the ImGui console are out of scope permanently:
see docs/superpowers/specs/2026-08-25-feature-demo-stage1-design.md.

Scenes load ASYNCHRONOUSLY, as in the C++ sample. Init() only starts the load; the class
then follows ApplicationBase's lifecycle rather than driving it:

    BeginLoadingScene  ->  SceneUnloading()      (render thread, if a scene is already up)
                           LoadScene()           (LOADING THREAD)
                           SceneLoaded()         (render thread, once textures are finalized)

and ApplicationBase::Render calls RenderSplashScreen() instead of RenderScene() until that
finishes -- which is why this class overrides RenderScene, not Render. The Settings panel's
"Scene" combo re-enters the whole cycle, so any scene FindScenes turns up under media/ can
be loaded at runtime.

NOTE: sponza-plus.scene.json declares no lights and no cameras at all, so the "Sun",
"Point" and "Spot" lights and the "Nave" and "Gallery" cameras this example offers are all
created here and attached to the scene graph, not loaded. SceneLoaded() re-creates them for
every scene, including ones that do declare their own.
"""

from __future__ import annotations

if __name__ == "__main__":
    import math
    import sys
    import time
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

    # Depth bias for the shadow-map depth pass, in depth-buffer units and in units per unit of
    # depth slope. Tuned against Sponza at the resolution above; they are the first thing to
    # change if the shadows show acne (too little) or peter-panning (too much). Applied in one
    # place only, CreateDepthPass.
    SHADOW_DEPTH_BIAS = 100
    SHADOW_SLOPE_SCALED_DEPTH_BIAS = 2.0

    # Minimum depth range of the shadow projection along the light direction, in world units:
    # CascadedShadowMap takes max(cascade's own half-extent, this) for each side
    # (CascadedShadowMap.cpp:137-138), so these only matter for the near cascades, where they are
    # what keeps a caster above the camera from falling outside the box. Sized to Sponza with
    # headroom; not UI controls, because the only correct setting is "big enough".
    SHADOW_LIGHT_SPACE_Z_UP = 20.0
    SHADOW_LIGHT_SPACE_Z_DOWN = 20.0

    # The light probes this example adds. All four share one diffuse and one specular cube-map
    # ARRAY, indexed by slice -- not a private texture pair each. That is load-bearing:
    # DeferredLightingPass logs an error and returns *without rendering the frame* if two
    # submitted probes present different maps (DeferredLightingPass.cpp:246-253), the same
    # failure mode CreateSceneLights documents for two lights with different shadow maps.
    #
    # Sizes and mip counts from FeatureDemo.cpp:1252-1256. The specular chain's 8 levels are
    # the roughness axis: RenderLightProbe filters one level per roughness step.
    LIGHT_PROBE_COUNT = 4
    LIGHT_PROBE_DIFFUSE_SIZE = 256
    LIGHT_PROBE_DIFFUSE_MIPS = 1
    LIGHT_PROBE_SPECULAR_SIZE = 512
    LIGHT_PROBE_SPECULAR_MIPS = 8

    # The throwaway environment cube map each capture renders into, before it is filtered down
    # into the probe's array slices (FeatureDemo.cpp:1304-1305). Bigger than either output: the
    # filtering reduces it.
    LIGHT_PROBE_ENVIRONMENT_SIZE = 1024
    LIGHT_PROBE_ENVIRONMENT_MIPS = 8
    # Near plane and far cull distance for the capture's six face views, and the half-extent of
    # the box the probe's bounds are built from (FeatureDemo.cpp:1347-1348, :1430).
    LIGHT_PROBE_Z_NEAR = 0.1
    LIGHT_PROBE_CULL_DISTANCE = 100.0
    LIGHT_PROBE_BOUNDS_EXTENT = 10.0

    # The two demonstration lights this example adds to Sponza. Intensity is luminous intensity
    # in lm/sr, multiplied by the light's colour; radius is the light sphere's radius in world
    # units. Starting points tuned by eye against Sponza's metre scale -- the Lights UI section
    # is how they are explored further, so they are constants rather than UI state.
    POINT_LIGHT_INTENSITY = 20.0
    SPOT_LIGHT_INTENSITY = 60.0
    LOCAL_LIGHT_RADIUS = 0.05

    # The two demonstration scene cameras this example adds to Sponza. Vertical FOV is in
    # RADIANS here, unlike the spot light's degrees -- PerspectiveCamera.verticalFov is what
    # Donut reads directly. Written with math.radians so the unit is visible at the call site.
    # Positions tuned by eye against Sponza's metre scale, like the light intensities above.
    NAVE_CAMERA_FOV = math.radians(60.0)
    GALLERY_CAMERA_FOV = math.radians(40.0)
    SCENE_CAMERA_Z_NEAR = 0.1

    # The vertical FOV the view shim actually uses -- PlanarView.SetMatricesFromSwitchableCamera
    # defaults verticalFovRadians to PI/4, and SetupView does not override it. The C++ sample
    # uses 60 degrees (FeatureDemo.cpp:323); matching the shim instead keeps the pick framing
    # consistent with what is actually on screen.
    #
    # Caveat: this only holds while a user (first/third-person) camera is active.
    # SetMatricesFromSwitchableCamera defers to GetSceneCameraProjectionParams when a scene
    # camera (Nave/Gallery) is active, which overrides verticalFovRadians with that camera's own
    # FOV -- so a pick made through a scene camera can frame at a slightly different distance
    # than this constant implies. Harmless: PointThirdPersonCameraAt always switches to
    # third-person on a hit, so the discrepancy is invisible past that first reframe.
    CAMERA_VERTICAL_FOV = math.pi / 4.0

    def _nextScreenshotPath() -> str:
        """First unused screenshot_NNNN.bmp beside this script.

        The fallback when FileDialog returns None. That return does not distinguish "user
        cancelled" from "no dialog available" -- on Linux the dialog shells out to `zenity`,
        which may not be installed -- so a cancelled dialog also writes a file. That is
        deliberate: the alternative is a button that silently does nothing under WSL, and the
        file is trivially deleted.
        """
        directory = Path(__file__).parent
        index = 1
        while True:
            candidate = directory / f"screenshot_{index:04d}.bmp"
            if not candidate.exists():
                return str(candidate)
            index += 1

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
            # Written by the MaterialID readback each time a pick resolves. SelectedMaterial
            # drives the Material Editor window; SelectedNode drives the picked-node readout and
            # the third-person camera reframe.
            self.SelectedMaterial: pyd.Material | None = None
            self.SelectedNode: pyd.SceneGraphNode | None = None
            self.TestMipMapGen = False
            # Set by the Screenshot button, consumed and cleared by the next Render.
            self.ScreenshotFileName = ""
            # Side-by-side split viewport, not stereo hardware -- both eyes render into the one
            # back buffer (FeatureDemo.cpp:726-744).
            self.Stereo = False
            # Light probes. The two scales are pushed onto every enabled probe each frame in
            # Render -- LightProbe::FillLightProbeConstants reads them off the struct, so the UI
            # has no other route to them.
            self.EnableLightProbe = True
            self.LightProbeDiffuseScale = 1.0
            self.LightProbeSpecularScale = 1.0

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
            self.MaterialIDs: pyd.Texture | None = None
            self.MaterialIDFramebuffer: pyd.FramebufferFactory | None = None
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

            # MSAA-matched alongside HdrColor, and non-UAV: the pick pass only ever renders into
            # it (FeatureDemo.cpp:124-127). RG16_UINT holds a material ID in .x and an instance
            # index in .y.
            self.MaterialIDs = makeColor(pyd.Format.RG16_UINT, "MaterialIDs", False)

            # ResolvedColor and the TAA feedback pair are always single-sampled: they are the
            # *output* of resolving, so they must not themselves be multisampled.
            def makeSingleSampled(
                fmt: pyd.Format, name: str, isUav: bool, mipLevels: int = 1
            ) -> pyd.Texture:
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
                desc.mipLevels = mipLevels
                return device.createTexture(desc)

            # A full mip chain purely so the MipMapGen test pass has something to reduce
            # (FeatureDemo.cpp:135). MipMapGenPass binds one UAV per level at construction, so a
            # single-level texture would give it nothing to write.
            self.ResolvedColor = makeSingleSampled(
                pyd.Format.RGBA16_FLOAT,
                "ResolvedColor",
                True,
                int(math.floor(math.log2(max(width, height)))) + 1,
            )
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

            self.MaterialIDFramebuffer = pyd.FramebufferFactory(device)
            self.MaterialIDFramebuffer.SetRenderTargets([self.MaterialIDs])
            # Shares the gbuffer's depth so the pick pass depth-tests against the same geometry
            # the visible frame did (FeatureDemo.cpp:208-210).
            self.MaterialIDFramebuffer.depthTarget = depth

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
            # Scene picker state, mirroring FeatureDemo.cpp:286-288. sceneFilesAvailable is
            # every scene found under sceneDir; currentSceneName is the one SetCurrentSceneName
            # last handed to BeginLoadingScene. `scene` is None until the loading thread has
            # built one, and is replaced wholesale by each load -- so every reader outside
            # SceneLoaded()/RenderScene() has to tolerate None, which is what IsSceneLoaded()
            # and the UI's IsSceneLoading() early-return are for.
            self.sceneDir = folder / "media"
            self.sceneFilesAvailable: list[str] = []
            self.currentSceneName = ""
            self.scene: pyd.Scene | None = None
            self.sunLight: pyd.DirectionalLight | None = None
            self.renderTargets: RenderTargets | None = None
            self.view: pyd.PlanarView | pyd.StereoPlanarView | None = None
            self.viewPrevious: pyd.PlanarView | pyd.StereoPlanarView | None = None
            # SwitchableCamera owns a first-person camera, a third-person camera and the
            # optional active scene camera, and routes input to whichever is active. Init
            # picks the starting one -- a fresh SwitchableCamera is in *third* person.
            self.camera = pyd.SwitchableCamera()
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
            self.materialIDPass: pyd.MaterialIDPass | None = None
            self.pixelReadbackPass: pyd.PixelReadbackPass | None = None
            self.mipMapGenPass: pyd.MipMapGenPass | None = None
            self.lightProbePass: pyd.LightProbeProcessingPass | None = None
            self.lightProbes: list[pyd.LightProbe] = []
            # Held so the shared arrays outlive the probes that index into them: LightProbe's
            # diffuseMap/specularMap are nvrhi handles, but nothing else on the Python side
            # keeps a reference.
            self.lightProbeDiffuseTexture: pyd.Texture | None = None
            self.lightProbeSpecularTexture: pyd.Texture | None = None
            # Armed by a right mouse press, consumed by the next Render. pickPosition is updated
            # on every mouse move, so it is already correct when the press arrives.
            self.pick = False
            self.pickPosition = (0, 0)
            # Hoisted, unlike gbufferContext/forwardContext which are built per frame: the
            # shadow depth pass is this context's only user, and RenderCompositeView is done
            # with it by the time it returns, so one instance serves every frame. The
            # inconsistency with the other two is cosmetic, and measured: the ctx probe in the
            # MSAA dossier ran a fresh DepthPassContext per shadow render and came out identical
            # to the control, so the sharing causes nothing.
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

            # Scene discovery for the picker, mirroring FeatureDemo.cpp:354-361. FindScenes
            # walks sceneDir recursively for .scene.json/.gltf/.glb, so media/ yields
            # sponza-plus.scene.json alongside the two glTF-Sample-Assets models.
            self.sceneFilesAvailable = pyd.FindScenes(self.nativeFS, self.sceneDir)
            if not self.sceneFilesAvailable:
                pyd.log.fatal(
                    f"No scene file found in media folder '{self.sceneDir}'. "
                    "Please make sure that folder contains valid scene files."
                )
                return False

            self.gbufferPass = pyd.GBufferFillPass(device, self.m_CommonPasses)
            self.gbufferPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())

            # Size-independent, like gbufferPass: it holds pipelines, not render targets, so it
            # belongs here and in ReloadShaders rather than in CreateRenderPasses. (The C++
            # sample builds it in CreateRenderPasses, FeatureDemo.cpp:800-801, but this port
            # already keeps its geometry passes out of that method.)
            self.materialIDPass = pyd.MaterialIDPass(device, self.m_CommonPasses)
            self.materialIDPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())

            self.deferredLightingPass = pyd.DeferredLightingPass(device, self.m_CommonPasses)
            self.deferredLightingPass.Init(self.shaderFactory)

            self.forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
            self.forwardPass.Init(
                self.shaderFactory, pyd.ForwardShadingPassCreateParameters()
            )

            # Size-independent, like the other geometry passes: it is created once here and
            # only recreated on a shader reload.
            self.CreateDepthPass(device)

            self.CreateShadowMap()

            # Size-independent, like the geometry passes above: it holds shaders and an
            # intermediate texture of its own, not anything sized to the back buffer, so it
            # belongs here rather than in CreateRenderPasses. (The C++ sample builds it in
            # CreateRenderPasses, FeatureDemo.cpp:830.)
            self.lightProbePass = pyd.LightProbeProcessingPass(
                device, self.shaderFactory, self.m_CommonPasses
            )
            self.CreateLightProbes(LIGHT_PROBE_COUNT)

            # Started LAST, once every pass exists. BeginLoadingScene() runs LoadScene() on its
            # own thread, so from here on Init() would be racing the loader for the device --
            # the C++ sample gets away with kicking the load off mid-constructor
            # (FeatureDemo.cpp:407-412, with CreateLightProbes after it) because its remaining
            # work is a handful of allocations, but there is nothing to gain by copying that.
            # SceneUnloading() also touches passes that must already exist for a *re*-load.
            self.SetAsynchronousLoadingEnabled(True)

            # sponza-plus.scene.json, not the sample's "Sponza.gltf": this demo is built around
            # it -- it is the one scene here with the BrainStem robots the animation toggle
            # drives. FindPreferredScene falls back to the first entry if it is ever missing.
            self.SetCurrentSceneName(
                pyd.FindPreferredScene(self.sceneFilesAvailable, "sponza-plus.scene.json")
            )

            return True

        def GetAvailableScenes(self: FeatureDemo) -> list[str]:
            return self.sceneFilesAvailable

        def GetCurrentSceneName(self: FeatureDemo) -> str:
            return self.currentSceneName

        def SetCurrentSceneName(self: FeatureDemo, sceneName: str) -> None:
            """Switches scenes, asynchronously. Mirrors FeatureDemo.cpp:442-450.

            The no-op guard is what makes this safe to call from the UI every frame the combo
            is open: re-selecting the active scene must not restart a load. BeginLoadingScene
            does the rest -- SceneUnloading() if a scene is already up, then the loader thread.
            """
            if self.currentSceneName == sceneName:
                return

            self.currentSceneName = sceneName
            self.BeginLoadingScene(self.nativeFS, Path(sceneName))

        def CreateRenderPasses(self: FeatureDemo) -> None:
            """Recreates every size-dependent pass. Called whenever RenderTargets is rebuilt."""
            device = self.GetDevice()
            assert self.renderTargets is not None

            # RGBA32_UINT is the readback *buffer's* layout and the compute shader variant that
            # fills it -- not the source texture's format, which is RG16_UINT. The mismatch is
            # deliberate and matches FeatureDemo.cpp:803.
            self.pixelReadbackPass = pyd.PixelReadbackPass(
                device,
                self.shaderFactory,
                self.renderTargets.MaterialIDs,
                pyd.Format.RGBA32_UINT,
            )

            # MODE_COLOR: ResolvedColor is an RGB target, so it wants the bilinear RGB reduction
            # rather than the single-channel min/max ones (MipMapGenPass.h:47-52).
            self.mipMapGenPass = pyd.MipMapGenPass(
                device,
                self.shaderFactory,
                self.renderTargets.ResolvedColor,
                pyd.MipMapGenPassMode.MODE_COLOR,
            )

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

            self.materialIDPass = pyd.MaterialIDPass(device, self.m_CommonPasses)
            self.materialIDPass.Init(self.shaderFactory, pyd.GBufferFillPassCreateParameters())

            self.deferredLightingPass = pyd.DeferredLightingPass(device, self.m_CommonPasses)
            self.deferredLightingPass.Init(self.shaderFactory)

            self.forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
            self.forwardPass.Init(
                self.shaderFactory, pyd.ForwardShadingPassCreateParameters()
            )

            # Holds pipelines compiled from the bytecode ClearCache just dropped, so it is
            # rebuilt with the other geometry passes. The shadow map itself holds no shaders and
            # is left alone.
            self.CreateDepthPass(device)

            # Recreated, not merely ResetCaches()'d: the constructor is what compiles this pass's
            # five shaders, so a reload that only cleared its caches would keep running the old
            # ones. Recreating it invalidates every probe -- probe.environmentBrdf points at the
            # OUTGOING pass's internally-owned BRDF texture, which dies with it -- so every probe
            # is disabled too. That mirrors what the sample does in SceneUnloading
            # (FeatureDemo.cpp:563-573); this port has no SceneUnloading, and a shader reload is
            # the analogous "everything built from shaders is stale now" point.
            #
            # The two cube-map arrays are NOT reallocated: they hold rendered pixels, not
            # anything derived from shader bytecode, and CreateLightProbes' probe objects still
            # index them correctly. Only the captured content is stale, which is what disabling
            # expresses.
            self.lightProbePass = pyd.LightProbeProcessingPass(
                device, self.shaderFactory, self.m_CommonPasses
            )
            for probe in self.lightProbes:
                probe.enabled = False
                probe.environmentBrdf = None

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

        def CreateDepthPass(self: FeatureDemo, device: pyd.Device) -> None:
            """Builds the shadow-map depth pass. Called from Init and CreateRenderPasses.

            One function rather than two copies because the two bias values are the tuning knob
            here: shadow acne is the most likely reason a first shadowed frame looks wrong, and
            the fix is a different constant. Split across two call sites, tuning one and not the
            other would leave a shader reload silently changing the bias.

            The biases are baked into the pass's pipelines at Init(), which is why they are
            constants rather than sliders -- a bias slider would mean recreating the pass on
            every drag.
            """
            depthParams = pyd.DepthPassCreateParameters()
            depthParams.depthBias = SHADOW_DEPTH_BIAS
            depthParams.slopeScaledDepthBias = SHADOW_SLOPE_SCALED_DEPTH_BIAS
            self.depthPass = pyd.DepthPass(device, self.m_CommonPasses)
            self.depthPass.Init(self.shaderFactory, depthParams)

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
            # before the replacement map is allocated. The light is unhooked first, before
            # self.shadowMap -- it holds a shared_ptr to the outgoing map, so dropping only this
            # object's reference would keep it alive.
            #
            # depthPass.ResetBindingCache() is deliberately NOT called: it clears material
            # bindings and vertex-buffer SRVs (DepthPass.cpp:91-95), neither of which references
            # the shadow texture. Nothing the pass caches becomes stale when this map is
            # replaced.
            if self.sunLight is not None:
                self.sunLight.shadowMap = None
            self.shadowMap = None
            self.shadowFramebuffer = None
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

        def CreateLightProbes(self: FeatureDemo, numProbes: int) -> None:
            """Allocates the two shared cube-map arrays and the probes that index into them.

            Ports FeatureDemo.cpp:1249-1299. One diffuse array and one specular array serve every
            probe, sliced by index -- see LIGHT_PROBE_COUNT's comment for why that sharing is
            required rather than merely economical.

            Every probe starts disabled AND with empty bounds. Either alone would be enough to
            keep it out of the lighting passes (LightProbe::IsActive checks both,
            SceneTypes.cpp:379-389); both are set because a probe with no captured content in its
            slices must not light anything, and RenderLightProbe is what flips both back.
            """
            device = self.GetDevice()

            def makeCubemapArray(size: int, mipLevels: int, name: str) -> pyd.Texture:
                desc = pyd.TextureDesc()
                desc.width = size
                desc.height = size
                desc.mipLevels = mipLevels
                desc.arraySize = 6 * numProbes
                desc.dimension = pyd.TextureDimension.TextureCubeArray
                desc.isRenderTarget = True
                desc.format = pyd.Format.RGBA16_FLOAT
                # ShaderResource, not RenderTarget: these are only ever written by
                # LightProbeProcessingPass and read by the lighting passes.
                desc.initialState = pyd.ResourceStates.ShaderResource
                desc.keepInitialState = True
                desc.debugName = name
                return device.createTexture(desc)

            self.lightProbeDiffuseTexture = makeCubemapArray(
                LIGHT_PROBE_DIFFUSE_SIZE, LIGHT_PROBE_DIFFUSE_MIPS, "LightProbeDiffuse"
            )
            self.lightProbeSpecularTexture = makeCubemapArray(
                LIGHT_PROBE_SPECULAR_SIZE, LIGHT_PROBE_SPECULAR_MIPS, "LightProbeSpecular"
            )

            self.lightProbes = []
            for index in range(numProbes):
                probe = pyd.LightProbe()
                # The UI labels each button with this, so it is "1".."4", not a zero-based index.
                probe.name = str(index + 1)
                probe.diffuseMap = self.lightProbeDiffuseTexture
                probe.specularMap = self.lightProbeSpecularTexture
                probe.diffuseArrayIndex = index
                probe.specularArrayIndex = index
                probe.SetBoundsEmpty()
                probe.enabled = False
                self.lightProbes.append(probe)

        def RenderLightProbe(self: FeatureDemo, probe: pyd.LightProbe) -> None:
            """Captures the scene into `probe` from the active camera's position.

            Ports FeatureDemo.cpp:1301-1433. Stands up a throwaway render graph -- its own
            cube-map colour and depth targets, framebuffer, view, sky pass, forward pass and
            command list -- renders one omnidirectional frame, filters it into the probe's array
            slices, and tears the whole thing down again.

            Called DIRECTLY from the UI button handler, not through a flag like the screenshot.
            Two things make that safe, and they are worth stating because the screenshot's
            deferred path invites the opposite assumption:

              * ImGui_Renderer::Render calls buildUI() BEFORE it opens its own command list
                (imgui_renderer.cpp:360-367), and this app's Render has already closed and
                executed its own by then -- no command list is open on the immediate context.
              * This method creates, executes and drains its own command list, so it needs
                nothing from the caller's frame.

            The screenshot needs a flag only because it must run at one specific point inside
            Render, after executeCommandList, with the back buffer in hand. A capture has no
            such constraint, so a flag would buy nothing and cost a frame of latency.
            """
            assert self.scene is not None and self.sunLight is not None
            assert self.lightProbePass is not None
            device = self.GetDevice()

            # The environment map this capture renders into. Discarded at the end of the method;
            # only its filtered reduction survives, in the probe's array slices.
            colorDesc = pyd.TextureDesc()
            colorDesc.width = LIGHT_PROBE_ENVIRONMENT_SIZE
            colorDesc.height = LIGHT_PROBE_ENVIRONMENT_SIZE
            colorDesc.mipLevels = LIGHT_PROBE_ENVIRONMENT_MIPS
            colorDesc.arraySize = 6
            colorDesc.dimension = pyd.TextureDimension.TextureCube
            colorDesc.isRenderTarget = True
            colorDesc.format = pyd.Format.RGBA16_FLOAT
            colorDesc.initialState = pyd.ResourceStates.RenderTarget
            colorDesc.keepInitialState = True
            colorDesc.useClearValue = True
            colorDesc.clearValue = pyd.Color(0.0)
            colorDesc.debugName = "LightProbeEnvironment"
            colorTexture = device.createTexture(colorDesc)

            # D32 rather than the sample's nvrhi::utils::ChooseFormat over
            # {D24S8, D32, D16, D32S8} (FeatureDemo.cpp:1384-1395). D32 is in that candidate
            # list, is universally supported, and is already what CreateShadowMap uses -- binding
            # ChooseFormat plus the FormatSupport flag enum to reach a format we can name
            # directly is not worth it. Consequence: there is never a stencil aspect, so the
            # clear below passes clearStencil=False rather than computing it.
            depthDesc = pyd.TextureDesc()
            depthDesc.width = LIGHT_PROBE_ENVIRONMENT_SIZE
            depthDesc.height = LIGHT_PROBE_ENVIRONMENT_SIZE
            depthDesc.mipLevels = 1
            depthDesc.arraySize = 6
            depthDesc.dimension = pyd.TextureDimension.TextureCube
            depthDesc.isRenderTarget = True
            depthDesc.format = pyd.Format.D32
            depthDesc.initialState = pyd.ResourceStates.DepthWrite
            depthDesc.keepInitialState = True
            depthDesc.debugName = "LightProbeDepth"
            depthTexture = device.createTexture(depthDesc)

            framebuffer = pyd.FramebufferFactory(device)
            framebuffer.SetRenderTargets([colorTexture])
            framebuffer.depthTarget = depthTexture

            # The probe sits wherever the camera is. A scene camera's position comes off its
            # node; a user camera's off the camera itself.
            if self.camera.IsSceneCameraActive():
                probeX, probeY, probeZ = self.camera.GetSceneCamera().GetPosition()
            else:
                probeX, probeY, probeZ = self.camera.GetActiveUserCamera().GetPosition()

            view = pyd.CubemapView()
            view.SetArrayViewports(LIGHT_PROBE_ENVIRONMENT_SIZE, 0)
            view.SetTransformFromPosition(
                probeX, probeY, probeZ, LIGHT_PROBE_Z_NEAR, LIGHT_PROBE_CULL_DISTANCE
            )
            view.UpdateCache()

            skyPass = pyd.SkyPass(
                device, self.shaderFactory, self.m_CommonPasses, framebuffer, view
            )

            # A fresh forward pass rather than self.forwardPass, and this is not an oversight:
            # the app's pass has singlePassCubemap False and caches its pipelines against the
            # back buffer's FramebufferInfo, neither of which suits a cube-map target. This runs
            # on a button press, so two pass constructions cost nothing.
            forwardParams = pyd.ForwardShadingPassCreateParameters()
            forwardParams.singlePassCubemap = device.queryFeatureSupport(
                pyd.Feature.FastGeometryShader
            )
            forwardPass = pyd.ForwardShadingPass(device, self.m_CommonPasses)
            forwardPass.Init(self.shaderFactory, forwardParams)

            commandList = device.createCommandList()
            commandList.open()
            commandList.clearTextureFloat(colorTexture, pyd.Color(0.0))
            # clearDepth=True, depth=0.0: reverse-Z, as everywhere else in this file.
            # clearStencil=False -- D32 has no stencil aspect, see the format comment above.
            commandList.clearDepthStencilTexture(depthTexture, True, 0.0, False, 0)

            # Refit the cascades around the probe rather than around the camera frustum. This
            # CLOBBERS the fit the current frame's RenderShadowMap made -- harmless, because
            # RenderShadowMap refits from scratch at the top of every Render, so the damage
            # lasts until the next frame begins. The sample behaves identically.
            minX, minY, minZ, maxX, maxY, maxZ = (
                self.scene.GetSceneGraph().GetRootNode().GetGlobalBoundingBox()
            )
            dx, dy, dz = maxX - minX, maxY - minY, maxZ - minZ
            zRange = math.sqrt(dx * dx + dy * dy + dz * dz) * 0.5
            self.shadowMap.SetupForCubemapView(
                self.sunLight,
                view,
                LIGHT_PROBE_CULL_DISTANCE,
                zRange,
                zRange,
                self.ui.ShadowExponent,
            )
            self.shadowMap.Clear(commandList)

            shadowContext = pyd.DepthPassContext()
            pyd.RenderCompositeView(
                commandList,
                self.shadowMap.GetView(),
                None,
                self.shadowFramebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                self.depthPass,
                shadowContext,
                self.ui.EnableMaterialEvents,
                "ShadowMap",
            )

            forwardContext = pyd.ForwardShadingPassContext()
            # An EMPTY probe list, deliberately: a probe capture must not be lit by other
            # probes, or probes would feed back into each other (FeatureDemo.cpp:1388-1389).
            ambient = self.ui.AmbientIntensity
            forwardPass.PrepareLights(
                forwardContext,
                commandList,
                self.scene.GetSceneGraph().GetLights(),
                ambient * 0.2, ambient * 0.2, ambient * 0.2,
                ambient * 0.1, ambient * 0.1, ambient * 0.1,
                [],
            )

            # viewPrev is None throughout: a one-off capture has no history, and nothing here
            # reads motion vectors.
            pyd.RenderCompositeView(
                commandList,
                view,
                None,
                framebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.opaqueDrawStrategy,
                forwardPass,
                forwardContext,
                self.ui.EnableMaterialEvents,
                "ForwardOpaque",
            )

            skyPass.Render(commandList, view, self.sunLight, self.ui.SkyParams)

            pyd.RenderCompositeView(
                commandList,
                view,
                None,
                framebuffer,
                self.scene.GetSceneGraph().GetRootNode(),
                self.transparentDrawStrategy,
                forwardPass,
                forwardContext,
                self.ui.EnableMaterialEvents,
                "ForwardTransparent",
            )

            # levelsToGenerate is mips - 1: level 0 is the rendered image, the rest are reduced
            # from it.
            self.lightProbePass.GenerateCubemapMips(
                commandList, colorTexture, 0, 0, LIGHT_PROBE_ENVIRONMENT_MIPS - 1
            )

            # * 6 on both array indices: a cube "slice" is six faces.
            self.lightProbePass.RenderDiffuseMap(
                commandList, colorTexture, probe.diffuseMap, probe.diffuseArrayIndex * 6, 0
            )

            # One specular mip per roughness step, squared so the low-roughness levels get the
            # resolution (FeatureDemo.cpp:1416-1420).
            for mipLevel in range(LIGHT_PROBE_SPECULAR_MIPS):
                roughness = (mipLevel / (LIGHT_PROBE_SPECULAR_MIPS - 1)) ** 2.0
                self.lightProbePass.RenderSpecularMap(
                    commandList,
                    roughness,
                    colorTexture,
                    probe.specularMap,
                    probe.specularArrayIndex * 6,
                    mipLevel,
                )

            self.lightProbePass.RenderEnvironmentBrdfTexture(commandList)

            commandList.close()
            device.executeCommandList(commandList)
            # Both are the sample's (FeatureDemo.cpp:1426-1427). The wait is what makes the
            # capture synchronous with the button press; the collection retires the throwaway
            # colour, depth and framebuffer objects now rather than at some later frame.
            device.waitForIdle()
            device.runGarbageCollection()

            probe.environmentBrdf = self.lightProbePass.GetEnvironmentBrdfTexture()
            # Bounds must become non-empty or IsActive() stays false and the probe lights
            # nothing, whatever `enabled` says.
            probe.SetBoundsFromBox(
                probeX - LIGHT_PROBE_BOUNDS_EXTENT,
                probeY - LIGHT_PROBE_BOUNDS_EXTENT,
                probeZ - LIGHT_PROBE_BOUNDS_EXTENT,
                probeX + LIGHT_PROBE_BOUNDS_EXTENT,
                probeY + LIGHT_PROBE_BOUNDS_EXTENT,
                probeZ + LIGHT_PROBE_BOUNDS_EXTENT,
            )
            probe.enabled = True

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
                    # A scene-declared light is already attached, so GetName()/SetName() work
                    # here same as below -- but the scene may not have named it, and an empty
                    # name would show up as a blank, ID-colliding Selectable("") in the Lights
                    # dropdown. Sponza declares no lights today, so this is latent, not currently
                    # triggered.
                    if not self.sunLight.GetName():
                        self.sunLight.SetName("Sun")
                    return

            self.sunLight = pyd.DirectionalLight()
            self.sunLight.angularSize = 0.53
            self.sunLight.irradiance = 1.0

            graph.AttachLeafNode(graph.GetRootNode(), self.sunLight)
            # SetName after AttachLeafNode, not next to the constructor above: SceneGraphLeaf.
            # SetName only takes effect once the leaf is attached to a scene-graph node and
            # silently no-ops otherwise (SceneGraph.cpp:40-47) -- with asserts compiled out in
            # this project's Release build, moving this call back up would silently reintroduce
            # a blank sun label in the Lights dropdown instead of failing loudly.
            self.sunLight.SetName("Sun")
            self.sunLight.SetDirection(0.1, -0.9, 0.1)

        def CreateSceneLights(self: FeatureDemo) -> None:
            """Adds the spot and point light this stage demonstrates.

            Unlike CreateSunLight there is no "reuse what the scene declared" branch. The sun is
            the light the renderer needs and another scene might supply one; these two are the
            example's own demonstration objects and are always synthesised.

            Attach first, then place. Light.SetPosition, Light.SetDirection and
            SceneGraphLeaf.SetName all assert (or silently no-op) when the light has no node
            (SceneTypes.cpp:82, :100; SceneGraph.cpp:40-47), because all three work by writing
            the owning node's transform or name. They do not clobber each other: SetDirection
            writes only rotation and scaling (SceneGraph.cpp:282-291).

            Neither light gets a shadow map, and that is load-bearing rather than unfinished.
            DeferredLightingPass logs an error and returns *without rendering the frame* if two
            lights present different shadow textures (DeferredLightingPass.cpp:172-175), and a
            CascadedShadowMap cannot be shared with a local light -- that needs
            SetupPerObjectShadow, which is unbound. Only the sun casts.

            Nothing else changes to light the scene with these: both shading paths already
            submit the whole GetLights() list, and both build their constants through the
            virtual FillLightConstants, which SpotLight and PointLight override.
            """
            assert self.scene is not None
            graph = self.scene.GetSceneGraph()
            root = graph.GetRootNode()

            point = pyd.PointLight()
            point.intensity = POINT_LIGHT_INTENSITY
            point.radius = LOCAL_LIGHT_RADIUS
            graph.AttachLeafNode(root, point)
            point.SetName("Point")
            point.SetPosition(-4.0, 2.0, 0.0)

            spot = pyd.SpotLight()
            spot.intensity = SPOT_LIGHT_INTENSITY
            spot.radius = LOCAL_LIGHT_RADIUS
            spot.innerAngle = 20.0
            spot.outerAngle = 35.0
            graph.AttachLeafNode(root, spot)
            spot.SetName("Spot")
            spot.SetPosition(4.0, 5.0, 0.0)
            spot.SetDirection(-0.2, -1.0, 0.0)

        def CreateSceneCameras(self: FeatureDemo) -> None:
            """Adds the two scene cameras the camera dropdown demonstrates.

            sponza-plus.scene.json declares no cameras at all, so without these the dropdown
            would offer only First-Person and Third-Person and nothing would exercise the
            SceneCamera bindings -- the same reason CreateSunLight synthesises the sun.

            Attach first, then name and place. SceneGraphLeaf.SetName writes through the
            owning node and silently does nothing when the leaf has no node yet
            (SceneGraph.cpp:40-47), and this project builds Release, so the assert meant to
            catch that is compiled out.

            SceneGraph::RegisterLeaf routes any SceneCamera into the graph's camera list
            (SceneGraph.cpp:577-582), so an attached camera reaches GetCameras() with no
            further registration -- exactly as an attached light reaches GetLights().

            The two differ in vertical FOV as well as position, so switching between them
            visibly changes the projection and not merely the viewpoint.
            """
            assert self.scene is not None
            graph = self.scene.GetSceneGraph()
            root = graph.GetRootNode()

            nave = pyd.PerspectiveCamera()
            nave.verticalFov = NAVE_CAMERA_FOV
            nave.zNear = SCENE_CAMERA_Z_NEAR
            naveNode = graph.AttachLeafNode(root, nave)
            nave.SetName("Nave")
            naveNode.SetPositionAndDirection(-8.0, 2.0, 0.0, 1.0, 0.0, 0.0)

            gallery = pyd.PerspectiveCamera()
            gallery.verticalFov = GALLERY_CAMERA_FOV
            gallery.zNear = SCENE_CAMERA_Z_NEAR
            galleryNode = graph.AttachLeafNode(root, gallery)
            gallery.SetName("Gallery")
            galleryNode.SetPositionAndDirection(0.0, 8.0, -4.0, 0.0, -0.4, 1.0)

        def PointThirdPersonCameraAt(
            self: FeatureDemo, node: pyd.SceneGraphNode | None
        ) -> None:
            """Orbits the third-person camera around `node`, framed to its bounding box.

            Mirrors FeatureDemo.cpp:659-667. Does nothing for a node with no geometry: an empty
            box3 is mins = FLT_MAX / maxs = -FLT_MAX, which would give an infinite radius and
            throw the camera to infinity. The C++ never hits that case because it only ever
            calls this with loaded geometry, so the guard is an addition, not a port.
            """
            if node is None:
                return

            minX, minY, minZ, maxX, maxY, maxZ = node.GetGlobalBoundingBox()
            if minX > maxX or minY > maxY or minZ > maxZ:
                return

            dx, dy, dz = maxX - minX, maxY - minY, maxZ - minZ
            radius = math.sqrt(dx * dx + dy * dy + dz * dz) * 0.5
            if radius <= 0.0:
                return

            thirdPerson = self.camera.GetThirdPersonCamera()
            thirdPerson.SetTargetPosition(
                (minX + maxX) * 0.5, (minY + maxY) * 0.5, (minZ + maxZ) * 0.5
            )
            thirdPerson.SetDistance(radius / math.sin(CAMERA_VERTICAL_FOV * 0.5))
            # Load-bearing: SetTargetPosition and SetDistance only stage the values. Without
            # this the camera stays exactly where it was, with no error.
            thirdPerson.Animate(0.0)

        def KeyboardUpdate(self: FeatureDemo, key: int, scancode: int, action: int, mods: int) -> bool:
            # UIData.ShowUI is read by UIRenderer.buildUI but had nothing to set it -- without
            # a binding the settings panel can never be dismissed to see the frame behind it.
            # Raw GLFW codes with a comment, the convention the other examples already use
            # (rt_bindless.py:198, threaded_rendering.py:197): no keycode enum is bound.
            if key == 258 and action == 1:  # GLFW_KEY_TAB, GLFW_PRESS
                self.ui.ShowUI = not self.ui.ShowUI

            # T cycles the camera, matching FeatureDemo.cpp:486-499: from a scene camera it
            # returns to a user camera, otherwise it swaps first and third person. copyView
            # defaults to True here (unlike Init), which is the point -- the new camera picks
            # up where the old one was looking.
            if key == 84 and action == 1:  # GLFW_KEY_T, GLFW_PRESS
                if self.camera.IsFirstPersonActive():
                    self.camera.SwitchToThirdPerson()
                else:
                    self.camera.SwitchToFirstPerson()
                return True

            self.camera.KeyboardUpdate(key, scancode, action, mods)
            return True

        def MousePosUpdate(self: FeatureDemo, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            # Recorded unconditionally, so the position is already right when a press arrives
            # (FeatureDemo.cpp:511). The sample guards its camera call with
            # `if (!m_ui.ActiveSceneCamera)`; SwitchableCamera already routes input away from
            # the user cameras when a scene camera is active, so there is no guard here.
            self.pickPosition = (int(xpos), int(ypos))
            return True

        def MouseButtonUpdate(self: FeatureDemo, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            # No GLFW keycode enum is bound -- raw codes with a comment, the convention the other
            # examples use. Matches FeatureDemo.cpp:521-522.
            if button == 1 and action == 1:  # GLFW_MOUSE_BUTTON_2, GLFW_PRESS
                self.pick = True
            return True

        def MouseScrollUpdate(self: FeatureDemo, xoffset: float, yoffset: float) -> bool:
            # The example had no scroll handler while it only had a first-person camera, which
            # does not use the wheel. The third-person camera zooms with it.
            self.camera.MouseScrollUpdate(xoffset, yoffset)
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
            if self.IsSceneLoaded() and self.ui.EnableAnimations:
                self.wallclockTime += elapsedTimeSeconds
                offset = 0.0
                for anim in self.scene.GetSceneGraph().GetAnimations():
                    duration = anim.GetDuration()
                    if duration > 0.0:
                        anim.Apply(math.fmod(self.wallclockTime + offset, duration))
                    offset += 1.0

            if self.toneMappingPass is not None:
                self.toneMappingPass.AdvanceFrame(elapsedTimeSeconds)

        def SceneUnloading(self: FeatureDemo) -> None:
            """Drops everything pointing into the outgoing scene, before the next load starts.

            Called by BeginLoadingScene (ApplicationBase.cpp:125-126) on the render thread,
            with the old scene still alive -- so this is the last safe moment to touch it.
            Mirrors FeatureDemo.cpp:558-572.

            Every binding cache here holds nvrhi BindingSetHandles built against the outgoing
            scene's material and geometry buffers. Left in place they would be handed to the
            new scene's draw calls, which is not a crash but silently wrong geometry.
            """
            self.gbufferPass.ResetBindingCache()
            self.materialIDPass.ResetBindingCache()
            self.deferredLightingPass.ResetBindingCache()
            self.forwardPass.ResetBindingCache()
            self.depthPass.ResetBindingCache()
            self.lightProbePass.ResetCaches()
            self.bindingCache.Clear()

            # All three are leaves of / references into the outgoing scene graph. sunLight is
            # re-derived by CreateSunLight on the next SceneLoaded; the two UI selections have
            # no counterpart in a different scene and must not survive as dangling picks.
            self.sunLight = None
            self.ui.SelectedMaterial = None
            self.ui.SelectedNode = None

            # The active scene camera is also a leaf of the outgoing graph. The C++ keeps it in
            # UIData and simply overwrites it in SceneLoaded (FeatureDemo.cpp:631-637); here
            # SwitchableCamera owns it, so the only way to let go is to switch away.
            if self.camera.IsSceneCameraActive():
                self.camera.SwitchToFirstPerson(copyView=False)

            # Their captured cube-map faces show the scene that is going away. The arrays
            # themselves are kept -- only the content is stale, which is what disabling says.
            for probe in self.lightProbes:
                probe.enabled = False

        def LoadScene(self: FeatureDemo, fs: pyd.IFileSystem, sceneFileName: Path) -> bool:
            """Builds the scene. Runs on the LOADING THREAD, not the render thread.

            ApplicationBase::BeginLoadingScene starts a std::thread whose whole body is this
            call (ApplicationBase.cpp:140-143), and pybind11 holds the GIL around a Python
            override -- so the only reason the render thread makes any progress meanwhile is
            that the Scene.Load binding releases the GIL for the duration of the load. Nothing
            else added here may block: this method is otherwise pure Python and holds the GIL.

            The new scene is published to self.scene only on success, so a failed load leaves
            the previous one in place rather than half-replacing it.
            """
            scene = pyd.Scene(
                self.GetDevice(),
                self.shaderFactory,
                fs,
                self.m_TextureCache,
                self.descriptorTable,
            )

            startTime = time.perf_counter()
            if not scene.Load(sceneFileName):
                pyd.log.error(f"Failed to load {sceneFileName}")
                return False

            self.scene = scene
            elapsedMs = (time.perf_counter() - startTime) * 1e3
            pyd.log.info(f"Scene loading time: {elapsedMs:.0f} ms")
            return True

        def SceneLoaded(self: FeatureDemo) -> None:
            """Finalises the scene the loading thread just built. Mirrors FeatureDemo.cpp:599.

            Runs on the RENDER thread: ApplicationBase::Render joins the loading thread and
            calls this once every deferred texture upload has drained
            (ApplicationBase.cpp:70-78).
            """
            # GltfImporter never loads textures fully synchronously -- every path it has goes
            # through LoadTextureFrom*Deferred/Async (GltfImporter.cpp:820-831), which only
            # decodes the pixels and queues the GPU upload. Draining that queue is what actually
            # creates the textures, and this base call is what drains it
            # (ApplicationBase.cpp:98-105).
            #
            # Without it every texture stays null and MaterialBindingCache silently swaps in its
            # flat fallback texture (MaterialBindingCache.cpp:110) -- no error, no warning, just
            # untextured geometry that still lights and shades correctly. Sponza rendered
            # entirely grey; the BrainStem robots looked fine only because they have no textures
            # at all (0 images, 59 constant-colour materials), which is what made the bug read as
            # "Sponza's assets are broken".
            #
            # Placement is load-bearing: after Load(), before FinishedLoading(). This assigns
            # each texture its bindless descriptor index, and FinishedLoading() is what bakes
            # those indices into the material buffer.
            super().SceneLoaded()

            assert self.scene is not None

            self.CreateSunLight()
            self.CreateSceneLights()
            self.CreateSceneCameras()

            # After the lights and cameras above, not before: FinishedLoading uploads the
            # instance/geometry/material buffers for the graph as it stands.
            #
            # This is also the ONLY scene-graph refresh in the sequence, and that is
            # load-bearing for skinned meshes. SceneGraph::Refresh stamps each skinned
            # instance with the frame index it was last dirtied on and then clears the dirty
            # flags (SceneGraph.cpp:1027-1038), and UpdateSkinnedMeshes skips any instance
            # whose stamp is more than one frame stale (Scene.cpp:718-720). An earlier refresh
            # at a different index -- the hardcoded graph.Refresh(0) the three helpers above
            # used to end with -- consumes the flags and stamps 0, so the skinning dispatch
            # never runs and every skinned mesh renders as nothing at all. That was invisible
            # while these ran from Init() at frame 0; SceneLoaded() runs at a live frame index
            # (8 or so), where 0 + 1 < 8 skips the dispatch and DancingRobot1/2 vanish until
            # an animation dirties their joints again.
            self.scene.FinishedLoading(self.GetFrameIndex())

            # A new scene restarts the animation clock, and its first frame has no predecessor
            # for TAA or motion vectors to reproject from (FeatureDemo.cpp:603-604).
            self.wallclockTime = 0.0
            self.previousViewsValid = False

            graph = self.scene.GetSceneGraph()

            # CreateSceneCameras always synthesises two cameras, so the sample's "cameras[0]
            # becomes the active scene camera" branch (FeatureDemo.cpp:631-636) would start
            # every scene looking through "Nave". This port starts in first person instead, as
            # it always has; the scene cameras stay one dropdown pick or T press away.
            #
            # copyView=False matters: a fresh SwitchableCamera is in third person
            # (Camera.h:259-261), so copying the view would take it from the
            # default-constructed third-person camera -- 30 units back, aimed at the origin --
            # and overwrite the LookAt below.
            self.camera.SwitchToFirstPerson(copyView=False)
            firstPerson = self.camera.GetFirstPersonCamera()
            firstPerson.LookAt(0.0, 1.8, 0.0, 1.0, 1.8, 0.0)
            firstPerson.SetMoveSpeed(3.0)

            # Framed on the new scene's bounds, so the third-person camera is already useful
            # the first time T is pressed (FeatureDemo.cpp:646-647).
            self.camera.GetThirdPersonCamera().SetRotation(
                math.radians(135.0), math.radians(20.0)
            )
            self.PointThirdPersonCameraAt(graph.GetRootNode())

            # A bare .gltf/.glb is a single model rather than a walkable environment, so the
            # sample frames it from outside instead (FeatureDemo.cpp:651-652). copyView=False
            # again -- the third-person camera was just aimed above and must keep that framing
            # rather than inherit the first-person view.
            if self.currentSceneName.endswith((".gltf", ".glb")):
                self.camera.SwitchToThirdPerson(copyView=False)

        def RenderSplashScreen(self: FeatureDemo, framebuffer: pyd.Framebuffer) -> None:
            """Clears to black while the loading thread works. Mirrors FeatureDemo.cpp:862-870.

            ApplicationBase::Render calls this instead of RenderScene until the scene is loaded
            AND every deferred texture upload has drained. Clearing is all it can do: the render
            targets, views and per-frame passes are all built by RenderScene, which has not run.
            The progress text is drawn on top by UIRenderer.buildUI, a separate render pass.
            """
            self.commandList.open()
            self.commandList.clearTextureFloat(
                framebuffer.getDesc().getColorAttachment(0).texture, pyd.Color(0.0)
            )
            self.commandList.close()
            self.GetDevice().executeCommandList(self.commandList)

            # Nothing here is worth spinning the GPU for. Animate() re-asserts the UI's own
            # VSync setting every frame once the scene is up, so this does not stick.
            self.GetDeviceManager().SetVsyncEnabled(True)

        def SetupView(self: FeatureDemo, width: int, height: int) -> bool:
            """Updates self.view/self.viewPrevious for this frame's viewport.

            Returns whether the view's TOPOLOGY changed (planar <-> stereo) this frame --
            Render uses this to decide whether the size-independent passes need rebuilding,
            matching FeatureDemo.cpp:895-921's needNewPasses pattern. BloomPass in particular
            sizes an internal per-view-child vector at construction from
            compositeView.GetNumChildViews(ViewType::PLANAR) and indexes it per child every
            Render call -- a topology change without a pass rebuild leaves it indexing past
            the end of that vector.
            """
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

            # Swapping the view type mid-run leaves viewPrevious holding the *other* kind, which
            # TAA would then resolve against. Rebuild both together and copy across, as
            # FeatureDemo.cpp:722-726 and :753 do.
            topologyChanged = False
            if self.ui.Stereo:
                if not isinstance(self.view, pyd.StereoPlanarView):
                    self.view = pyd.StereoPlanarView()
                    topologyChanged = True
            else:
                if not isinstance(self.view, pyd.PlanarView):
                    self.view = pyd.PlanarView()
                    topologyChanged = True

            if self.ui.Stereo:
                # Left eye owns the left half, right eye the right half of one back buffer.
                self.view.LeftView.SetViewport(pyd.Viewport(width * 0.5, float(height)))
                self.view.RightView.SetViewport(
                    pyd.Viewport(width * 0.5, float(width), 0.0, float(height), 0.0, 1.0)
                )
                self.view.LeftView.SetPixelOffset(pixelOffsetX, pixelOffsetY)
                self.view.RightView.SetPixelOffset(pixelOffsetX, pixelOffsetY)
                # PER-EYE aspect ratio: each eye is half the framebuffer wide
                # (FeatureDemo.cpp:736). The shim does not halve it internally.
                self.view.SetMatricesFromSwitchableCamera(
                    self.camera, width / height * 0.5
                )
                # StereoPlanarView has no cache of its own -- each eye is updated individually.
                self.view.LeftView.UpdateCache()
                self.view.RightView.UpdateCache()
                # The third-person camera converts mouse drags into orbit and pan amounts using
                # the view's own projection and viewport, so it needs one concrete eye, not the
                # composite (FeatureDemo.cpp:751).
                self.camera.GetThirdPersonCamera().SetView(self.view.LeftView)
            else:
                self.view.SetViewport(pyd.Viewport(float(width), float(height)))
                self.view.SetPixelOffset(pixelOffsetX, pixelOffsetY)
                self.view.SetMatricesFromSwitchableCamera(self.camera, width / height)
                self.view.UpdateCache()
                # As in FeatureDemo.cpp:773.
                self.camera.GetThirdPersonCamera().SetView(self.view)

            if topologyChanged:
                # Seed viewPrevious from the view just built, so the first frame after a switch
                # does not resolve this frame against the other topology's leftovers.
                self.viewPrevious = self._snapshotView()
                # TAA history built against the old topology is meaningless now.
                self.previousViewsValid = False

            return topologyChanged

        def _snapshotView(self: FeatureDemo) -> pyd.PlanarView | pyd.StereoPlanarView:
            """Copies the current view, preserving its topology.

            The copy constructor is the only way to snapshot a view -- neither type exposes its
            matrices to Python -- and each type has its own, so this has to switch.
            """
            if isinstance(self.view, pyd.StereoPlanarView):
                return pyd.StereoPlanarView(self.view)
            return pyd.PlanarView(self.view)

        def RenderScene(self: FeatureDemo, framebuffer: pyd.Framebuffer) -> None:
            """The real frame. Called by ApplicationBase::Render only once the scene is loaded
            and every deferred texture upload has drained (ApplicationBase.cpp:64-80) -- until
            then RenderSplashScreen runs instead. That inherited Render is also what drains the
            texture queue each frame and joins the loading thread, which is why this class
            overrides RenderScene rather than Render (FeatureDemo.cpp:872).
            """
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
            #
            # The waitForIdle is not here for safety -- the render-target block below is right
            # that NVRHI command lists keep every resource they touch alive until the fence
            # retires, so releasing a Python reference can never free something in flight. It is
            # here for peak VRAM: those same in-flight references are what would otherwise keep
            # the outgoing 64 MB cascade array resident while CreateShadowMap allocates its
            # replacement, and "the two arrays are never both resident" is a claim that method
            # makes. Draining is affordable precisely because this is a discrete UI event.
            #
            # The block below has the SAME transient overlap -- dropping CPU-side references does
            # not retire the in-flight command lists still holding the outgoing render targets --
            # but it makes no never-both-resident claim and runs on every resize and AA change,
            # so it absorbs the overlap rather than stall the pipeline on a drag.
            if self.ui.ShadowCascades != self.shadowMapCascades:
                device.waitForIdle()
                self.CreateShadowMap()

            # GetCurrentPixelOffset switches on the pass's current jitter mode
            # (TemporalAntiAliasingPass.cpp:335), so the mode has to be pushed in before
            # SetupView reads the offset back out.
            if self.taaPass is not None:
                self.taaPass.SetJitter(self.ui.TemporalAntiAliasingJitter)

            # CreateRenderPasses reads self.view (SkyPass's constructor takes the composite
            # view), so SetupView must run before it -- and before the rebuild block below,
            # since that block calls CreateRenderPasses once the new targets exist.
            topologyChanged = self.SetupView(width, height)

            needNewPasses = False

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
                # (docs/superpowers/specs/2026-08-26-msaa-double-switch-validation-flood.md).
                #
                # The recreation is unconditional: it happens on every pass through this block,
                # not only when the sample count changed, and because ReloadShaders() sets
                # renderTargets = None a shader reload builds both passes twice, once there and
                # once here. Deliberate. The measurement above shows the stale pipeline is
                # reachable more broadly than the "MSAA -> MSAA with shadows on" story it was
                # first pinned to, so a narrower trigger risks letting the flood back in for a
                # case nobody enumerated. This block runs on a resize, an AA-mode change or a
                # shader reload -- never per frame -- so being unconditional costs two pass
                # constructions on a discrete user action.
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
                needNewPasses = True

            # A topology-only change (Stereo toggled with no resize/AA change) does NOT need a
            # RenderTargets reallocation, but DOES need the size-independent passes rebuilt --
            # matching FeatureDemo.cpp:906-909. BloomPass in particular caches state sized to the
            # OLD view's child-view count at construction (see SetupView's docstring above); the
            # crash this fixes is BloomPass indexing past that cached vector's end after Stereo
            # is ticked with no other setting changed.
            #
            # A topology-only change here also re-triggers CreateRenderPasses's exposure-reset
            # path (pendingExposureBuffer is already None from the last CreateRenderPasses call,
            # so exposureResetRequired becomes True) -- a one-frame flash back to 0.5 exposure
            # when Stereo is toggled. Matches the reference sample's behavior in the same case;
            # not something this fix changes.
            if topologyChanged:
                needNewPasses = True

            # CreateRenderPasses asserts self.renderTargets is not None and reads its
            # allocated textures, so it can only run after the block above (which allocates
            # self.renderTargets on first run and keeps it unchanged on later runs, per its own
            # size-driven condition).
            if needNewPasses:
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

            # Built once, before the shading branch, and handed to whichever path runs
            # (FeatureDemo.cpp:968-978). The two scales are written onto the probe objects here
            # because LightProbe::FillLightProbeConstants reads them off the struct -- the UI has
            # no other route to them.
            lightProbes = []
            if self.ui.EnableLightProbe:
                for probe in self.lightProbes:
                    if probe.enabled:
                        probe.diffuseScale = self.ui.LightProbeDiffuseScale
                        probe.specularScale = self.ui.LightProbeSpecularScale
                        lightProbes.append(probe)

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
                # The sample passes its WHOLE probe list here while giving the forward path the
                # filtered one (FeatureDemo.cpp:1021) -- an asymmetry that only works because
                # DeferredLightingPass skips probes failing IsActive(). One filtered list feeds
                # both paths here: identical rendered result, one thing to keep in sync instead
                # of two.
                deferredInputs.SetLightProbes(lightProbes)
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
                    lightProbes,
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

            # Matches FeatureDemo.cpp:1039-1067: after the shading passes so it sees the same
            # depth buffer, before the sky so the sky cannot overwrite an ID.
            if self.pick and self.pixelReadbackPass is not None:
                # 0xffff is the "nothing here" sentinel -- material IDs and instance indices are
                # both non-negative, so no real value collides with it.
                self.commandList.clearTextureUInt(self.renderTargets.MaterialIDs, 0xFFFF)

                materialIDContext = pyd.GBufferFillPassContext()
                pyd.RenderCompositeView(
                    self.commandList,
                    self.view,
                    self.viewPrevious,
                    self.renderTargets.MaterialIDFramebuffer,
                    self.scene.GetSceneGraph().GetRootNode(),
                    self.opaqueDrawStrategy,
                    self.materialIDPass,
                    materialIDContext,
                    self.ui.EnableMaterialEvents,
                )

                if self.ui.EnableTranslucency:
                    pyd.RenderCompositeView(
                        self.commandList,
                        self.view,
                        self.viewPrevious,
                        self.renderTargets.MaterialIDFramebuffer,
                        self.scene.GetSceneGraph().GetRootNode(),
                        self.transparentDrawStrategy,
                        self.materialIDPass,
                        materialIDContext,
                        self.ui.EnableMaterialEvents,
                    )

                self.pixelReadbackPass.Capture(
                    self.commandList, self.pickPosition[0], self.pickPosition[1]
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

            # Matches FeatureDemo.cpp:1159-1166: the blit runs FIRST, then this reduces
            # ResolvedColor's mip chain and draws the levels in a spiral OVER the just-blitted
            # back buffer, so the result is actually visible. (An earlier version of this file
            # had the order reversed, citing the same line range incorrectly -- the spiral was
            # being drawn and then immediately erased by the blit.)
            if self.ui.TestMipMapGen and self.mipMapGenPass is not None:
                self.mipMapGenPass.Dispatch(self.commandList)
                self.mipMapGenPass.Display(
                    self.m_CommonPasses, self.commandList, framebuffer
                )

            self.commandList.close()
            device.executeCommandList(self.commandList)

            # After executeCommandList: SaveTextureToFile requires that no immediate command
            # list be open (TextureCache.h:238) and creates temporary resources internally,
            # which is why the sample calls it here too (FeatureDemo.cpp:1191-1195).
            if self.ui.ScreenshotFileName:
                fileName = self.ui.ScreenshotFileName
                self.ui.ScreenshotFileName = ""
                saved = pyd.SaveTextureToFile(
                    device,
                    self.m_CommonPasses,
                    framebuffer.getDesc().getColorAttachment(0).texture,
                    pyd.ResourceStates.RenderTarget,
                    fileName,
                )
                if saved:
                    pyd.log.info(f"Screenshot written to {fileName}")
                else:
                    pyd.log.error(f"Failed to write screenshot to {fileName}")

            # After executeCommandList: the readback buffer is not populated until the GPU has
            # run the Capture recorded above (FeatureDemo.cpp:1197-1228).
            if self.pick and self.pixelReadbackPass is not None:
                self.pick = False
                materialID, instanceIndex, _, _ = self.pixelReadbackPass.ReadUInts()

                self.ui.SelectedMaterial = None
                self.ui.SelectedNode = None

                sceneGraph = self.scene.GetSceneGraph()
                for material in sceneGraph.GetMaterials():
                    if material.materialID == materialID:
                        self.ui.SelectedMaterial = material
                        break

                for instance in sceneGraph.GetMeshInstances():
                    if instance.GetInstanceIndex() == instanceIndex:
                        # The owning handle, not GetNode()'s raw pointer: this is stored across
                        # frames and outlives the loop.
                        self.ui.SelectedNode = instance.GetNodeSharedPtr()
                        break

                if self.ui.SelectedNode is not None:
                    pyd.log.info(f"Picked node: {self.ui.SelectedNode.GetPath()}")
                    self.PointThirdPersonCameraAt(self.ui.SelectedNode)
                else:
                    self.PointThirdPersonCameraAt(sceneGraph.GetRootNode())

            self.viewPrevious = self._snapshotView()

    class UIRenderer(pyd.ImGui_Renderer):
        def __init__(
            self: UIRenderer, deviceManager: pyd.DeviceManager, app: FeatureDemo, ui: UIData
        ) -> None:
            super().__init__(deviceManager)
            self.app = app
            self.ui = ui
            # The selected light lives here rather than on UIData because nothing outside the
            # UI reads it -- the same place the original keeps m_SelectedLight
            # (FeatureDemo.cpp:1445).
            self.selectedLight: pyd.Light | None = None
            pyd.ImGui.DisableIniFile()

        def _relativeScenePath(self: UIRenderer, name: str) -> str:
            """Trims the media-folder prefix off a scene path for display.

            FindScenes returns absolute paths; the C++ does the same trim inline with a
            starts_with (FeatureDemo.cpp:1517-1521). as_posix() because that is the separator
            FindScenes uses in the strings it returns, on Windows too.
            """
            prefix = self.app.sceneDir.as_posix() + "/"
            return name[len(prefix):] if name.startswith(prefix) else name

        def buildUI(self: UIRenderer) -> None:
            if not self.ui.ShowUI:
                return

            # Mirrors FeatureDemo.cpp:1480-1496. Ahead of the ShowUI check in spirit but after
            # it in code, so ESC/TAB still hides everything: while a scene loads there is no
            # scene, no render targets and no views, and every panel below would fault on the
            # first self.app.scene access. The early return is what makes those panels' later
            # `self.app.scene is not None` guards enough.
            #
            # These counters are written by the loading thread as this reads them --
            # ObjectsLoaded/ObjectsTotal are atomics on the engine's one global stats object,
            # and the texture counts are atomics on TextureCache. A torn read here would only
            # ever show a number one frame stale.
            if self.app.IsSceneLoading():
                stats = pyd.Scene.GetLoadingStats()
                textureCache = self.app.m_TextureCache
                self.BeginFullScreenWindow()
                self.DrawScreenCenteredText(
                    f"Loading scene {self.app.GetCurrentSceneName()}, please wait...\n"
                    f"Objects: {stats.ObjectsLoaded}/{stats.ObjectsTotal}, "
                    f"Textures: {textureCache.GetNumberOfLoadedTextures()}/"
                    f"{textureCache.GetNumberOfRequestedTextures()}"
                )
                self.EndFullScreenWindow()
                return

            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Settings", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            # Scene picker, mirroring FeatureDemo.cpp:1523-1536. Paths are shown relative to
            # the media folder -- the absolute ones FindScenes returns are far too long for a
            # combo. Selecting the active scene is a no-op; selecting any other one re-enters
            # BeginLoadingScene, so SceneUnloading() fires and the splash screen comes back on
            # the very next frame.
            currentScene = self.app.GetCurrentSceneName()
            if pyd.ImGui.BeginCombo("Scene", self._relativeScenePath(currentScene)):
                for scene in self.app.GetAvailableScenes():
                    isSelected = scene == currentScene
                    if pyd.ImGui.Selectable(self._relativeScenePath(scene), isSelected):
                        self.app.SetCurrentSceneName(scene)
                    if isSelected:
                        pyd.ImGui.SetItemDefaultFocus()
                pyd.ImGui.EndCombo()

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

            _, self.ui.EnableLightProbe = pyd.ImGui.Checkbox(
                "Enable Light Probe", self.ui.EnableLightProbe
            )
            if self.ui.EnableLightProbe and pyd.ImGui.CollapsingHeader("Light Probe"):
                # DragFloat, not SliderFloat: the sample uses one, and the useful range sits at
                # the bottom of 0-10 where a linear slider cannot resolve it. Same reasoning as
                # the TAA section's "Max Radiance".
                _, self.ui.LightProbeDiffuseScale = pyd.ImGui.DragFloat(
                    "Diffuse Scale", self.ui.LightProbeDiffuseScale, 0.01, 0.0, 10.0
                )
                _, self.ui.LightProbeSpecularScale = pyd.ImGui.DragFloat(
                    "Specular Scale", self.ui.LightProbeSpecularScale, 0.01, 0.0, 10.0
                )

            _, self.ui.EnableVsync = pyd.ImGui.Checkbox("VSync", self.ui.EnableVsync)

            _, self.ui.Stereo = pyd.ImGui.Checkbox("Stereo", self.ui.Stereo)

            _, self.ui.EnableAnimations = pyd.ImGui.Checkbox(
                "Animations", self.ui.EnableAnimations
            )

            # Mirrors FeatureDemo.cpp:1548-1570, which places this right after the Animations
            # checkbox. The preview shows the active scene camera's name, or which user camera
            # is active. The scene is None until Init has loaded it.
            if self.app.scene is not None:
                sceneCameras = self.app.scene.GetSceneGraph().GetCameras()
                activeSceneCamera = self.app.camera.GetSceneCamera()

                if activeSceneCamera is not None:
                    cameraPreview = activeSceneCamera.GetName()
                elif self.app.camera.IsFirstPersonActive():
                    cameraPreview = "First-Person"
                else:
                    cameraPreview = "Third-Person"

                if pyd.ImGui.BeginCombo("Camera (T)", cameraPreview):
                    # As in the Lights section, selection is driven by Selectable's return
                    # value rather than the original's mutate-and-test pattern: the bound
                    # Selectable(label, selected) -> bool returns the click, and the argument
                    # only drives highlighting.
                    #
                    # copyView is left at its default True for every switch here, so the new
                    # camera picks up the outgoing one's viewpoint -- the behaviour the
                    # original gets from its CopyActiveCameraToFirstPerson call.
                    if pyd.ImGui.Selectable(
                        "First-Person", self.app.camera.IsFirstPersonActive()
                    ):
                        self.app.camera.SwitchToFirstPerson()
                    if pyd.ImGui.Selectable(
                        "Third-Person", self.app.camera.IsThirdPersonActive()
                    ):
                        self.app.camera.SwitchToThirdPerson()
                    for sceneCamera in sceneCameras:
                        if pyd.ImGui.Selectable(
                            sceneCamera.GetName(), sceneCamera is activeSceneCamera
                        ):
                            self.app.camera.SwitchToSceneCamera(sceneCamera)
                    pyd.ImGui.EndCombo()

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

                # These two are pushed straight at the live shadow map rather than read back
                # out of the UI each frame, so they need the `changed` guard the other controls
                # do not. The stored value is updated unconditionally all the same: gating the
                # store on shadowMap as well would make the control snap back while no map
                # exists, and CreateShadowMap replays both settings onto every new map.
                changed, self.ui.ShadowFalloffDistance = pyd.ImGui.SliderFloat(
                    "Falloff Distance", self.ui.ShadowFalloffDistance, 0.0, 10.0
                )
                if changed and self.app.shadowMap is not None:
                    self.app.shadowMap.SetFalloffDistance(self.ui.ShadowFalloffDistance)

                changed, self.ui.ShadowLitOutOfBounds = pyd.ImGui.Checkbox(
                    "Lit Out Of Bounds", self.ui.ShadowLitOutOfBounds
                )
                if changed and self.app.shadowMap is not None:
                    self.app.shadowMap.SetLitOutOfBounds(self.ui.ShadowLitOutOfBounds)

            # Fetched before the header so an empty scene hides the section entirely, matching
            # FeatureDemo.cpp:1635. This example always has three, but a different scene need
            # not.
            assert self.app.scene is not None
            lights = self.app.scene.GetSceneGraph().GetLights()

            if lights and pyd.ImGui.CollapsingHeader("Lights"):
                # CollapsingHeader does not push an ImGui ID scope (ImGuiTreeNodeFlags_
                # CollapsingHeader includes NoTreePushOnOpen), so LightEditor's "Radius" slider
                # (for Point/Spot lights) would otherwise share an ImGui ID with the SSAO
                # section's own "Radius" slider below, whenever both sections are open --
                # dragging one could silently drive the other's value. PushID/PopID give this
                # section's widgets their own ID namespace.
                pyd.ImGui.PushID("LightEditor")
                preview = (
                    self.selectedLight.GetName()
                    if self.selectedLight is not None
                    else "(None)"
                )
                if pyd.ImGui.BeginCombo("Select Light", preview):
                    for light in lights:
                        # The original passes &selected and then tests it
                        # (FeatureDemo.cpp:1641-1648), which re-selects whatever the mouse
                        # passes over. The bound Selectable returns the click instead, which is
                        # the correct ImGui idiom, so the argument only drives highlighting.
                        #
                        # `is` is sound here: pybind hands back the same Python wrapper for a
                        # C++ object that is still alive on the Python side, and holding the
                        # selection is what keeps it alive.
                        if pyd.ImGui.Selectable(light.GetName(), light is self.selectedLight):
                            self.selectedLight = light
                            pyd.ImGui.SetItemDefaultFocus()
                    pyd.ImGui.EndCombo()

                # Donut draws the whole editor, picking the controls from the light's concrete
                # type. Its return value says whether anything changed; nothing here needs to
                # act on that, because every field it writes is read fresh each frame -- the
                # sun's cascades included, since RenderShadowMap re-fits them every frame.
                if self.selectedLight is not None:
                    pyd.LightEditor(self.selectedLight)
                pyd.ImGui.PopID()

            # PushID for the same reason the Lights and Material Editor sections have one:
            # CollapsingHeader pushes no ID scope, so buttons labelled "1".."4" here could
            # otherwise collide with any other generically-labelled widget on the panel.
            pyd.ImGui.PushID("LightProbes")
            pyd.ImGui.Text("Render Light Probe: ")
            for probe in self.app.lightProbes:
                pyd.ImGui.SameLine()
                if pyd.ImGui.Button(probe.name):
                    # Direct call, not a flag -- see RenderLightProbe's docstring. It runs
                    # synchronously here, so the frame this button is pressed on takes visibly
                    # longer; that is the capture, not a hang.
                    self.app.RenderLightProbe(probe)
            pyd.ImGui.PopID()

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

            if pyd.ImGui.Button("Screenshot"):
                # Blocking modal. BMP first, because SaveTextureToFile picks its encoder from
                # the extension and BMP is what the sample offers (FeatureDemo.cpp:1671).
                chosen = pyd.FileDialog(
                    False, [("BMP files", "*.bmp"), ("All files", "*.*")]
                )
                self.ui.ScreenshotFileName = (
                    chosen if chosen is not None else _nextScreenshotPath()
                )

            pyd.ImGui.Separator()
            _, self.ui.TestMipMapGen = pyd.ImGui.Checkbox(
                "Test MipMapGen Pass", self.ui.TestMipMapGen
            )

            pyd.ImGui.End()

            # A second, separate window, as in FeatureDemo.cpp:1684-1698. Outside the Settings
            # window's Begin/End: ImGui windows do not nest. Shown only when a pick has resolved
            # to a material -- right-click in the viewport to select one.
            if self.ui.SelectedMaterial is not None:
                self._buildMaterialEditorWindow(self.ui.SelectedMaterial)

        def _buildMaterialEditorWindow(
            self: UIRenderer, material: pyd.Material
        ) -> None:
            """Draws the Material Editor window over the picked material.

            Split out of buildUI purely for size -- buildUI is already long, and this is a
            self-contained second window rather than another section of the settings panel.

            Stage 2c drove this from a dropdown as an explicit stand-in for picking. The
            dropdown is gone; `material` is whatever the last right-click resolved to.
            """
            # Right-aligned, matching FeatureDemo.cpp:1687: the pivot puts the window's
            # top-right corner at the given point, which is the only way to right-align
            # without knowing the window's width beforehand.
            windowWidth, _ = self.app.GetDeviceManager().GetWindowDimensions()
            # Assumes DisplayFramebufferScale == 1 (no DPI scaling reported to ImGui); on a scaled
            # display this anchor would sit slightly off the true right edge, but ImGui's own
            # on-screen clamping keeps the visible effect small.
            pyd.ImGui.SetNextWindowPos(float(windowWidth) - 10.0, 10.0, 0, 1.0, 0.0)
            pyd.ImGui.Begin("Material Editor", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            # MaterialEditor emits generically-labelled controls, and CollapsingHeader does not
            # push an ID scope -- the same collision the Lights section is wrapped against.
            pyd.ImGui.PushID("MaterialEditor")

            # Sponza's glTF assigns no name to any of its materials (GltfImporter.cpp:914-915
            # only sets one when the source file supplies it), so the ID carries the identity.
            pyd.ImGui.Text(f"Material {material.materialID}: {material.name or '(unnamed)'}")

            if self.ui.SelectedNode is not None:
                pyd.ImGui.Text(f"Node: {self.ui.SelectedNode.GetPath()}")

            previousDomain = material.domain
            material.dirty = pyd.MaterialEditor(material, True)

            # Moving between the opaque and alpha-blended domains changes which draw list the
            # material's geometry belongs to, so the scene has to re-evaluate its content.
            if material.domain != previousDomain:
                self.app.scene.GetSceneGraph().GetRootNode().InvalidateContent()

            pyd.ImGui.PopID()
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
