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
"""Surface tests for the FeatureDemo stage 2a shadow bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a parameter default drifting away from the C++ header it mirrors.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def test_ishadowmap_is_exported() -> None:
    assert hasattr(pyd, "IShadowMap")


def test_ishadowmap_is_not_constructible() -> None:
    # Registered purely as a polymorphic base, the same shape ICompositeView/IView take --
    # everything the interface declares is called by the lighting passes in C++.
    with pytest.raises(TypeError):
        pyd.IShadowMap()


def test_light_shadow_map_defaults_to_none() -> None:
    light = pyd.DirectionalLight()
    assert light.shadowMap is None


def test_light_shadow_map_accepts_none() -> None:
    # Assigning None is the shadow toggle: both lighting passes null-check light->shadowMap
    # (DeferredLightingPass.cpp:163), so clearing it needs no pass rebuild.
    light = pyd.DirectionalLight()
    light.shadowMap = None
    assert light.shadowMap is None


def test_cascaded_shadow_map_is_a_shadow_map() -> None:
    assert issubclass(pyd.CascadedShadowMap, pyd.IShadowMap)


def test_cascaded_shadow_map_surface() -> None:
    for name in (
        "SetupForPlanarView",
        "SetupForPlanarViewStable",
        "Clear",
        "GetView",
        "GetCascadeView",
        "GetTexture",
        "GetNumberOfCascades",
        "SetLitOutOfBounds",
        "SetFalloffDistance",
    ):
        assert hasattr(pyd.CascadedShadowMap, name), name


def test_cascaded_shadow_map_rejects_an_out_of_range_cascade_count() -> None:
    # Donut only asserts 1 <= numCascades <= 4 (CascadedShadowMap.cpp:40-41) and asserts are
    # compiled out of the build this repo ships, so the binding raises instead. Without the
    # guard, m_Cascades is a std::vector and the count sails through: both lighting passes then
    # write lightConstants.shadowCascades[cascade] for every cascade (DeferredLightingPass.cpp:
    # 197, ForwardShadingPass.cpp:427) into an int4 (light_cb.h:59), corrupting the neighbouring
    # constant-buffer fields with no crash and no message.
    #
    # Passing device=None is only safe because the guard runs before the device is touched --
    # do NOT add an in-range count to this list, it would dereference the null device.
    for count in (-1, 0, 5, 8):
        with pytest.raises(ValueError):
            pyd.CascadedShadowMap(None, 2048, count, 0, pyd.Format.D32)


# The matching exponent > 1 guard on SetupForPlanarView/SetupForPlanarViewStable has no test
# here: reaching either call needs a constructed shadow map, which needs a real device, and this
# module is the GPU-free surface layer. It is verified by running feature_demo.py.


def test_cascaded_shadow_map_skips_the_unsafe_cascade_setter() -> None:
    # SetNumberOfCascadesUnsafe only moves the count the *shaders* read; the composite view is
    # built once in the constructor (CascadedShadowMap.cpp:67) and never rebuilt, so lowering
    # the count through it would leave GetView() still rendering every allocated slice. The
    # cascade count is a construction parameter here instead -- see the spec.
    assert not hasattr(pyd.CascadedShadowMap, "SetNumberOfCascadesUnsafe")


def test_cascaded_shadow_map_setup_takes_a_view_not_a_frustum() -> None:
    # The frustum is pulled off the view C++-side: donut math types never cross into Python.
    # Nothing here constructs a shadow map (that needs a device), so this checks the bound
    # signature names a view type for `view` and that no frustum type appears anywhere in it.
    #
    # IView, not PlanarView: a stereo view has to reach both setup calls, and both of the
    # accessors they use (GetViewFrustum, GetProjectionFrustum) are declared on IView
    # (View.h:71-72) and meaningfully overridden by StereoView (View.h:235-255).
    #
    # Assert the *qualified parameter* spelling, not a bare "PlanarView" substring: the method
    # name itself contains "PlanarView", so a bare check can never fail here. pybind11 renders
    # the C++ type name because CascadedShadowMap is registered ahead of IView in the module.
    for setup in (
        pyd.CascadedShadowMap.SetupForPlanarView,
        pyd.CascadedShadowMap.SetupForPlanarViewStable,
    ):
        doc = setup.__doc__
        assert doc is not None
        assert "view: donut::engine::IView" in doc
        assert "view: donut::engine::PlanarView" not in doc
        assert "Frustum" not in doc


def test_depth_pass_trio_is_exported() -> None:
    for name in ("DepthPass", "DepthPassContext", "DepthPassCreateParameters"):
        assert hasattr(pyd, name), name


def test_depth_pass_context_is_a_geometry_pass_context() -> None:
    # RenderCompositeView threads this through, so it has to convert to the base.
    assert issubclass(pyd.DepthPassContext, pyd.GeometryPassContext)


def test_depth_pass_is_a_geometry_pass() -> None:
    assert issubclass(pyd.DepthPass, pyd.IGeometryPass)


def test_depth_pass_create_parameter_defaults_match_the_header() -> None:
    # Mirrors DepthPass.h:75-88. A default drifting from the header is exactly what this
    # GPU-free test layer exists to catch.
    params = pyd.DepthPassCreateParameters()
    assert params.depthBias == 0
    assert params.depthBiasClamp == 0.0
    assert params.slopeScaledDepthBias == 0.0
    assert params.trackLiveness is True
    assert params.useInputAssembler is False
    assert params.numConstantBufferVersions == 16


def test_depth_pass_create_parameters_skip_material_bindings() -> None:
    # The pass builds its own MaterialBindingCache when this is null, and nothing in this repo
    # constructs one -- so it is deliberately unbound rather than overlooked.
    assert not hasattr(pyd.DepthPassCreateParameters(), "materialBindings")


def test_render_composite_view_takes_a_composite_view() -> None:
    # CascadedShadowMap.GetView() returns a CompositeView, which derives from ICompositeView and
    # is NOT an IView (View.h:55,150) -- an IView parameter would reject the very argument this
    # widening exists to accept. pybind11 renders the C++ type name here because ICompositeView
    # is registered further down the module than this function.
    doc = pyd.RenderCompositeView.__doc__
    assert "ICompositeView" in doc
    assert "PlanarView" not in doc


def test_render_composite_view_keeps_material_events_ninth() -> None:
    # feature_demo.py passes materialEvents positionally, at three call sites; no other example
    # passes it at all. passEvent is appended after it precisely so those three keep binding to
    # the argument they meant instead of silently taking a str for a bool.
    doc = pyd.RenderCompositeView.__doc__
    assert doc.index("materialEvents") < doc.index("passEvent")


def test_planar_view_still_converts_to_both_widened_parameters() -> None:
    # The widening's backward compatibility, checked where it actually lives: every existing
    # caller passes a PlanarView, and it keeps binding because PlanarView derives from IView
    # derives from ICompositeView. Calling the functions for real needs a device, so the five
    # examples that do are run in this task's verification step instead.
    assert issubclass(pyd.PlanarView, pyd.IView)
    assert issubclass(pyd.IView, pyd.ICompositeView)


def test_render_view_takes_an_iview() -> None:
    # RenderView's C++ signature takes const IView*, not ICompositeView* (GeometryPasses.h:70-78),
    # so it widens one step less far than RenderCompositeView.
    doc = pyd.RenderView.__doc__
    assert "IView" in doc
    assert "PlanarView" not in doc


def test_deferred_lighting_render_takes_a_composite_view() -> None:
    # DeferredLightingPass::Render takes const ICompositeView& (DeferredLightingPass.h:97-101);
    # the binding narrowed it to PlanarView, which a stereo view cannot satisfy.
    doc = pyd.DeferredLightingPass.Render.__doc__
    assert doc is not None
    assert "ICompositeView" in doc
    assert "PlanarView" not in doc


def test_temporal_aa_signatures_take_composite_views() -> None:
    # All three take const ICompositeView& in C++ (TemporalAntiAliasingPass.h:106-124). The
    # constructor matters as much as the two render calls: the pass caches state derived from
    # the view it was built with.
    for member in (
        pyd.TemporalAntiAliasingPass.__init__,
        pyd.TemporalAntiAliasingPass.RenderMotionVectors,
        pyd.TemporalAntiAliasingPass.TemporalResolve,
    ):
        doc = member.__doc__
        assert doc is not None
        assert "ICompositeView" in doc
        assert "PlanarView" not in doc


def test_get_framebuffer_signatures_take_an_iview() -> None:
    # FramebufferFactory::GetFramebuffer takes const IView& (FramebufferFactory.h:48) -- one
    # step narrower than ICompositeView, because it needs GetSubresources.
    for member in (
        pyd.FramebufferFactory.GetFramebuffer,
        pyd.GBufferRenderTargets.GetFramebuffer,
    ):
        doc = member.__doc__
        assert doc is not None
        assert "view: donut::engine::IView" in doc
        assert "view: donut::engine::PlanarView" not in doc


def test_view_scoped_clear_overloads_take_an_iview() -> None:
    # Both overloads call view.GetSubresources(), declared on IView. __doc__ here carries every
    # overload of the name, so the AllSubresources variants appear alongside the view-taking ones.
    for member in (
        pyd.CommandList.clearTextureFloat,
        pyd.CommandList.clearDepthStencilTexture,
    ):
        doc = member.__doc__
        assert doc is not None
        assert "view: donut::engine::IView" in doc
        assert "PlanarView" not in doc
