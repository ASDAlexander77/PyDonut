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

"""Surface tests for the FeatureDemo stage 3b light-probe bindings.

These need no GPU. LightProbe is a plain struct and is constructible standalone;
LightProbeProcessingPass and the passes that consume probes all need a device, so those get
presence-and-signature checks against __doc__ instead of live calls -- the same split
test_picking_bindings.py uses for MaterialIDPass and PixelReadbackPass.

One thing deliberately NOT tested here: that SetBoundsFromBox makes a probe active. IsActive()
requires a non-empty bounds AND an assigned diffuse or specular map (SceneTypes.cpp:379-389),
and a Texture cannot be created without a device. The behavioural proof that the bounds helpers
reach the real field is the manual run at the end of the stage: feature_demo.py sets every
probe's bounds empty at creation, so if SetBoundsFromBox silently no-oped, IsActive() would stay
false and a captured probe would light nothing.
"""

from __future__ import annotations

import pydonut as pyd


def test_light_probe_is_constructible() -> None:
    assert pyd.LightProbe() is not None


def test_light_probe_is_re_exported() -> None:
    # Reachable as pyd.LightProbe, not just pyd._pydonut.LightProbe -- feature_demo.py builds
    # them by name.
    assert "LightProbe" in pyd.__all__


def test_light_probe_defaults_match_the_struct() -> None:
    # SceneTypes.h:362-367. Nothing in feature_demo.py sets the scales or `enabled` at
    # construction, so the C++ defaults are what a fresh probe starts with.
    probe = pyd.LightProbe()
    assert probe.diffuseArrayIndex == 0
    assert probe.specularArrayIndex == 0
    assert probe.diffuseScale == 1.0
    assert probe.specularScale == 1.0
    assert probe.enabled is True
    assert probe.diffuseMap is None
    assert probe.specularMap is None
    assert probe.environmentBrdf is None


def test_light_probe_fields_round_trip() -> None:
    # The UI writes diffuseScale/specularScale onto the probe every frame and CreateLightProbes
    # writes the name and both array indices, so every one of these must be settable.
    probe = pyd.LightProbe()
    probe.name = "3"
    probe.diffuseArrayIndex = 2
    probe.specularArrayIndex = 2
    probe.diffuseScale = 0.25
    probe.specularScale = 4.0
    probe.enabled = False
    assert probe.name == "3"
    assert probe.diffuseArrayIndex == 2
    assert probe.specularArrayIndex == 2
    assert probe.diffuseScale == 0.25
    assert probe.specularScale == 4.0
    assert probe.enabled is False


def test_fresh_light_probe_is_inactive() -> None:
    # IsActive() has three conditions (SceneTypes.cpp:379-389). It is worth being precise about
    # WHICH one rejects a fresh probe, because the obvious guess is wrong: a default-constructed
    # probe's bounds are frustum::infinite(), not empty, so the bounds check PASSES. What fails
    # is the map check -- neither diffuseMap nor specularMap is assigned.
    probe = pyd.LightProbe()
    assert probe.IsActive() is False


def test_disabled_light_probe_is_inactive() -> None:
    probe = pyd.LightProbe()
    probe.enabled = False
    assert probe.IsActive() is False


def test_bounds_helpers_replace_the_frustum_type() -> None:
    # dm::frustum never crosses into Python: `bounds` is not a property, it is three
    # construction methods. This pins both halves -- the methods exist and are callable, and
    # no Frustum type was introduced alongside them.
    probe = pyd.LightProbe()
    assert probe.SetBoundsEmpty() is None
    assert probe.SetBoundsInfinite() is None
    assert probe.SetBoundsFromBox(-1.0, -2.0, -3.0, 1.0, 2.0, 3.0) is None
    assert not hasattr(pyd, "Frustum")
    assert not hasattr(pyd.LightProbe, "bounds")


def test_set_bounds_from_box_takes_six_flat_floats() -> None:
    # dm::box3 does not cross into Python, exactly as for
    # SceneGraphNode.GetGlobalBoundingBox's six-float return.
    doc = pyd.LightProbe.SetBoundsFromBox.__doc__
    assert doc is not None
    for name in ("minX", "minY", "minZ", "maxX", "maxY", "maxZ"):
        assert f"{name}: typing.SupportsFloat" in doc, name
    assert "box3" not in doc


def test_prepare_lights_still_accepts_the_nine_argument_form() -> None:
    # THE regression guard for this task. deferred_shading.py, threaded_rendering.py and every
    # other existing caller passes nine arguments; lightProbes is trailing and defaulted so they
    # keep working untouched. If a future edit reorders the parameters, this fails first.
    doc = pyd.ForwardShadingPass.PrepareLights.__doc__
    assert doc is not None
    assert "lightProbes: collections.abc.Sequence[pydonut._pydonut.LightProbe] = []" in doc
    # bottomB is the last of the nine originals, so lightProbes following it proves it is
    # trailing rather than inserted mid-list.
    assert doc.index("bottomB") < doc.index("lightProbes")


def test_deferred_inputs_take_light_probes() -> None:
    # Inputs::lightProbes is a non-owning pointer to a vector (DeferredLightingPass.h:82), so
    # the binding wrapper has to own the vector -- the same trick SetLights already uses. A live
    # call plus a surviving reference is what proves the vector outlived the call.
    inputs = pyd.DeferredLightingPassInputs()
    probes = [pyd.LightProbe(), pyd.LightProbe()]
    assert inputs.SetLightProbes(probes) is None
    del probes
    # No crash and no error means the wrapper kept its own shared_ptr copies.
    assert inputs.SetLightProbes([]) is None


def test_set_light_probes_empty_list_is_the_off_switch() -> None:
    # DeferredLightingPass::Render guards with `if (inputs.lightProbes)` and then iterates
    # (DeferredLightingPass.cpp:221-224), so a non-null pointer to an empty vector iterates zero
    # times -- indistinguishable from the sample's nullptr. feature_demo.py relies on that:
    # it passes [] rather than needing a way to null the pointer.
    inputs = pyd.DeferredLightingPassInputs()
    assert inputs.SetLightProbes([]) is None


def test_light_probe_processing_pass_is_re_exported() -> None:
    assert "LightProbeProcessingPass" in pyd.__all__


def test_light_probe_processing_pass_exposes_every_method() -> None:
    # All seven bind. BlitCubemap is the one the sample never calls, but it is a single line and
    # omitting it would leave a visibly incomplete class.
    for name in ("BlitCubemap", "GenerateCubemapMips", "RenderDiffuseMap", "RenderSpecularMap",
                 "RenderEnvironmentBrdfTexture", "GetEnvironmentBrdfTexture", "ResetCaches"):
        assert hasattr(pyd.LightProbeProcessingPass, name), name


def test_light_probe_processing_pass_constructor_defaults() -> None:
    # LightProbeProcessingPass.h:93-99. feature_demo.py passes neither, so the defaults are what
    # it actually runs with.
    doc = pyd.LightProbeProcessingPass.__init__.__doc__
    assert doc is not None
    assert "intermediateTextureSize: typing.SupportsInt | typing.SupportsIndex = 1024" in doc
    assert "intermediateTextureFormat: pydonut._pydonut.Format = " in doc
    assert "RGBA16_FLOAT" in doc


def test_render_diffuse_map_folds_away_the_subresource_set() -> None:
    # C++ takes nvrhi::TextureSubresourceSet inSubresources (LightProbeProcessingPass.h:118).
    # That type is not exposed to Python anywhere, AllSubresources is what the sample passes
    # (FeatureDemo.cpp:1413), and the existing clear/resolve bindings already set the precedent
    # of folding the subresource argument away. So the parameter is absent, not optional.
    doc = pyd.LightProbeProcessingPass.RenderDiffuseMap.__doc__
    assert doc is not None
    assert "inSubresources" not in doc
    assert "TextureSubresourceSet" not in doc
    assert "inEnvironmentMap" in doc
    assert "outDiffuseMap" in doc


def test_render_specular_map_takes_roughness_before_the_source() -> None:
    # Argument order matches C++ (LightProbeProcessingPass.h:126-132): roughness precedes the
    # environment map. feature_demo.py loops mip levels computing roughness per level, so
    # getting this backwards would silently pass a mip index as a roughness.
    doc = pyd.LightProbeProcessingPass.RenderSpecularMap.__doc__
    assert doc is not None
    assert doc.index("roughness") < doc.index("inEnvironmentMap")
    assert "inSubresources" not in doc


def test_render_specular_map_names_its_own_target() -> None:
    # donut's header calls this parameter outDiffuseMap (LightProbeProcessingPass.h:131), a
    # copy-paste slip from RenderDiffuseMap. The binding names it outSpecularMap.
    doc = pyd.LightProbeProcessingPass.RenderSpecularMap.__doc__
    assert doc is not None
    assert "outSpecularMap" in doc
    assert "outDiffuseMap" not in doc


def test_generate_cubemap_mips_signature() -> None:
    # feature_demo.py calls this with (colorTexture, 0, 0, mipLevels - 1).
    doc = pyd.LightProbeProcessingPass.GenerateCubemapMips.__doc__
    assert doc is not None
    for name in ("cubeMap", "baseArraySlice", "sourceMipLevel", "levelsToGenerate"):
        assert name in doc, name


def test_cubemap_view_set_transform_from_position_defaults_the_projection_flag() -> None:
    # C++ SetTransform takes a dm::affine3 (View.h:361), which cannot cross into Python, and the
    # only affine3 the sample ever builds for it is dm::translation(-probePosition)
    # (FeatureDemo.cpp:1353). So the binding takes the position and builds the matrix itself,
    # named to sit beside the existing SetTransformFromCamera.
    doc = pyd.CubemapView.SetTransformFromPosition.__doc__
    assert doc is not None
    assert "useReverseInfiniteProjections: bool = True" in doc
    assert "affine3" not in doc


def test_cubemap_view_set_transform_from_position_moves_the_faces() -> None:
    # Behavioural, not a doc check: CubemapView is constructible without a device, and its faces
    # are PlanarViews, which expose FillPlanarViewConstants(). Two different probe positions must
    # therefore produce different face constants -- that is what proves the position reaches the
    # matrix rather than being dropped.
    near = pyd.CubemapView()
    near.SetArrayViewports(256, 0)
    near.SetTransformFromPosition(0.0, 0.0, 0.0, 0.1, 100.0)
    near.UpdateCache()

    far = pyd.CubemapView()
    far.SetArrayViewports(256, 0)
    far.SetTransformFromPosition(10.0, 5.0, -3.0, 0.1, 100.0)
    far.UpdateCache()

    assert near.GetFaceView(0).FillPlanarViewConstants() != far.GetFaceView(0).FillPlanarViewConstants()


def test_cubemap_view_still_takes_a_camera() -> None:
    # Regression: SetTransformFromPosition is an addition, not a replacement.
    # threaded_rendering.py drives the camera form.
    assert hasattr(pyd.CubemapView, "SetTransformFromCamera")


def test_setup_for_cubemap_view_takes_a_view_not_a_centre() -> None:
    # C++ takes a dm::float3 centre (CascadedShadowMap.h:79-85) and the sample passes
    # view.GetViewOrigin(). Rather than bind GetViewOrigin and round-trip three floats, the
    # binding takes the view and reads the origin off it -- deliberately the same shape as the
    # already-bound SetupForPlanarView(light, view, ...), which likewise extracts what it needs
    # internally. GetViewOrigin is pure virtual on IView (View.h:69), so any view type works.
    doc = pyd.CascadedShadowMap.SetupForCubemapView.__doc__
    assert doc is not None
    assert "view: donut::engine::IView" in doc
    assert "exponent: typing.SupportsFloat | typing.SupportsIndex = 4.0" in doc
    assert "center" not in doc
    assert "float3" not in doc


def test_single_pass_cubemap_defaults_off_and_round_trips() -> None:
    # The sample sets this from queryFeatureSupport(FastGeometryShader)
    # (FeatureDemo.cpp:1379). Default False matters: the app's own forward pass must stay
    # six-pass, and only the throwaway pass built per probe capture opts in.
    params = pyd.ForwardShadingPassCreateParameters()
    assert params.singlePassCubemap is False
    params.singlePassCubemap = True
    assert params.singlePassCubemap is True


def test_base_camera_reports_its_position() -> None:
    # Flat 3-tuple, matching the GetDir/GetUp already on this class -- math types never cross
    # into Python. Needed because a probe captures at the active camera's position.
    camera = pyd.FirstPersonCamera()
    camera.LookAt(1.0, 2.0, 3.0, 1.0, 2.0, 4.0)
    assert camera.GetPosition() == (1.0, 2.0, 3.0)


def test_get_active_user_camera_returns_the_owned_camera() -> None:
    # A reference to the camera the SwitchableCamera owns, not a copy: writes through it must
    # stick, the same guarantee GetFirstPersonCamera already documents.
    switchable = pyd.SwitchableCamera()
    switchable.SwitchToFirstPerson(copyView=False)
    active = switchable.GetActiveUserCamera()
    active.SetMoveSpeed(7.5)
    assert switchable.GetActiveUserCamera().GetPosition() == active.GetPosition()


def test_get_active_user_camera_follows_the_switch() -> None:
    # Two cameras at distinguishable positions, so the switch is observable through GetPosition.
    switchable = pyd.SwitchableCamera()
    switchable.SwitchToFirstPerson(copyView=False)
    switchable.GetFirstPersonCamera().LookAt(1.0, 0.0, 0.0, 2.0, 0.0, 0.0)
    switchable.GetThirdPersonCamera().SetTargetPosition(50.0, 50.0, 50.0)
    switchable.GetThirdPersonCamera().SetDistance(1.0)
    switchable.GetThirdPersonCamera().Animate(0.0)

    assert switchable.GetActiveUserCamera().GetPosition() == (1.0, 0.0, 0.0)
    switchable.SwitchToThirdPerson(copyView=False)
    assert switchable.GetActiveUserCamera().GetPosition() != (1.0, 0.0, 0.0)


def _graph_with_root() -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Returns a fresh graph and its real root node.

    Copied from test_camera_bindings.py's helper of the same name. SetRootNode returns the
    *previous* root (SceneGraph.cpp:670-679) -- None on a fresh graph -- so the root has to be
    read back with GetRootNode(); passing SetRootNode's result as AttachLeafNode's parent
    silently re-roots the graph on every attach instead of adding siblings.
    """
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    return graph, graph.GetRootNode()


def test_scene_camera_reports_its_world_position() -> None:
    # A scene camera's position comes from its node's transform, so it needs an attached node.
    # AttachLeafNode takes the leaf and creates the wrapping node itself.
    #
    # SetPositionAndDirection only marks the node dirty (as test_camera_bindings.py's
    # test_set_position_and_direction_writes_the_nodes_world_transform documents), so
    # graph.Refresh(0) is required before the node's world transform -- and therefore
    # GetViewToWorldMatrix() -- reflects it.
    graph, root = _graph_with_root()
    camera = pyd.PerspectiveCamera()
    node = graph.AttachLeafNode(root, camera)
    node.SetPositionAndDirection(-8.0, 2.0, 5.0, 1.0, 0.0, 0.0)
    graph.Refresh(0)

    x, y, z = camera.GetPosition()
    assert (round(x, 4), round(y, 4), round(z, 4)) == (-8.0, 2.0, 5.0)


def test_scene_camera_position_is_not_the_world_to_view_translation() -> None:
    # THE test for this task's one deliberate correction. The sample reads
    # GetWorldToViewMatrix().m_translation (FeatureDemo.cpp:1351), which is -R*p, not p. For an
    # axis-aligned camera the two happen to differ only in sign; for a ROTATED one they are
    # unrelated. These are Sponza's own Gallery camera placement, which is rotated, so a binding
    # built on the world-to-view translation cannot produce the node's own position.
    #
    # graph.Refresh(0) is required for the same reason as the test above -- SetPositionAndDirection
    # only dirties the node.
    graph, root = _graph_with_root()
    camera = pyd.PerspectiveCamera()
    node = graph.AttachLeafNode(root, camera)
    node.SetPositionAndDirection(0.0, 8.0, -4.0, 0.0, -0.4, 1.0)
    graph.Refresh(0)

    x, y, z = camera.GetPosition()
    assert (round(x, 4), round(y, 4), round(z, 4)) == (0.0, 8.0, -4.0)
