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

"""Surface tests for the FeatureDemo stage 1 post-processing bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a parameter default drifting away from the C++ header it mirrors.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def test_view_bases_are_exported() -> None:
    assert hasattr(pyd, "ICompositeView")
    assert hasattr(pyd, "IView")


def test_planar_view_derives_from_iview() -> None:
    assert issubclass(pyd.PlanarView, pyd.IView)
    assert issubclass(pyd.IView, pyd.ICompositeView)


def test_cubemap_view_derives_from_iview() -> None:
    assert issubclass(pyd.CubemapView, pyd.IView)


def test_sky_parameters_defaults_match_header() -> None:
    p = pyd.SkyParameters()
    # brightness/glowIntensity are 0.1f in the header: float32 can't represent 0.1 exactly,
    # so the widened-to-double value read back through pybind11 needs an approx comparison.
    assert p.brightness == pytest.approx(0.1)
    assert p.horizonSize == 30.0
    assert p.glowSize == 5.0
    assert p.glowIntensity == pytest.approx(0.1)
    assert p.glowSharpness == 4.0
    assert p.maxLightRadiance == 100.0


def test_sky_parameters_are_writable() -> None:
    p = pyd.SkyParameters()
    p.brightness = 0.25
    assert p.brightness == 0.25


def test_sky_parameters_expose_flattened_float3_setters() -> None:
    p = pyd.SkyParameters()
    # dm::float3 fields are never exposed directly -- they are set as flat scalars.
    p.SetSkyColor(0.1, 0.2, 0.3)
    p.SetHorizonColor(0.4, 0.5, 0.6)
    p.SetGroundColor(0.7, 0.8, 0.9)
    p.SetDirectionUp(0.0, 1.0, 0.0)


def test_sky_pass_is_exported_with_render() -> None:
    assert hasattr(pyd, "SkyPass")
    assert hasattr(pyd.SkyPass, "Render")


def test_ssao_parameters_defaults_match_header() -> None:
    p = pyd.SsaoParameters()
    assert p.amount == 2.0
    assert p.backgroundViewDepth == 100.0
    assert p.radiusWorld == 0.5
    # 0.1f is not exactly representable, so widening the C++ float to a Python double
    # gives 0.10000000149011612. Exact == would be unsatisfiable. Values that ARE
    # binary-exact (2.0, 100.0, 0.5, 16.0) stay on exact equality deliberately.
    assert p.surfaceBias == pytest.approx(0.1)
    assert p.powerExponent == 2.0
    assert p.enableBlur is True
    assert p.blurSharpness == 16.0


def test_ssao_parameters_are_writable() -> None:
    p = pyd.SsaoParameters()
    p.amount = 3.5
    p.enableBlur = False
    assert p.amount == 3.5
    assert p.enableBlur is False


def test_ssao_pass_is_exported_with_render() -> None:
    assert hasattr(pyd, "SsaoPass")
    assert hasattr(pyd.SsaoPass, "Render")


def test_tone_mapping_parameters_defaults_match_header() -> None:
    p = pyd.ToneMappingParameters()
    # 0.8f / 0.95f / 0.02f are not exactly representable, so widening the C++ float to a
    # Python double leaves a residue and exact == would be unsatisfiable. The remaining
    # defaults (1.0, 0.5, -0.5, 3.0) are binary-exact and stay on exact equality.
    assert p.histogramLowPercentile == pytest.approx(0.8)
    assert p.histogramHighPercentile == pytest.approx(0.95)
    assert p.eyeAdaptationSpeedUp == 1.0
    assert p.eyeAdaptationSpeedDown == 0.5
    assert p.minAdaptedLuminance == pytest.approx(0.02)
    assert p.maxAdaptedLuminance == 0.5
    assert p.exposureBias == -0.5
    assert p.whitePoint == 3.0
    assert p.enableColorLUT is True


def test_tone_mapping_create_parameters_defaults_match_header() -> None:
    p = pyd.ToneMappingPassCreateParameters()
    assert p.isTextureArray is False
    assert p.histogramBins == 256
    assert p.numConstantBufferVersions == 16
    # exposureBufferOverride is how eye adaptation survives a resize; it starts unset.
    assert p.exposureBufferOverride is None
    # colorLUT is deliberately unbound -- nothing in this repo builds a colour LUT texture.
    assert not hasattr(p, "colorLUT")


def test_tone_mapping_pass_exposes_the_simple_render_path() -> None:
    assert hasattr(pyd.ToneMappingPass, "SimpleRender")
    assert hasattr(pyd.ToneMappingPass, "AdvanceFrame")
    assert hasattr(pyd.ToneMappingPass, "ResetExposure")
    assert hasattr(pyd.ToneMappingPass, "GetExposureBuffer")


def test_tone_mapping_pass_omits_the_manual_histogram_path() -> None:
    # Render/ResetHistogram/AddFrameToHistogram/ComputeExposure are deliberately unbound:
    # SimpleRender performs those steps internally and is the only path the sample takes.
    assert not hasattr(pyd.ToneMappingPass, "Render")
    assert not hasattr(pyd.ToneMappingPass, "ResetHistogram")
    assert not hasattr(pyd.ToneMappingPass, "AddFrameToHistogram")
    assert not hasattr(pyd.ToneMappingPass, "ComputeExposure")


def test_bloom_pass_is_exported_with_render() -> None:
    assert hasattr(pyd, "BloomPass")
    assert hasattr(pyd.BloomPass, "Render")


def test_bloom_render_takes_a_framebuffer_factory_per_call() -> None:
    # BloomPass takes a FramebufferFactory at construction AND at every Render call, because
    # the sample bloom's into different targets depending on AA mode (FeatureDemo.cpp:1128
    # vs :1146). Assert the per-call parameter survives in the signature.
    import inspect

    doc = inspect.getdoc(pyd.BloomPass.Render) or ""
    assert "framebufferFactory" in doc
    assert "sigmaInPixels" in doc
    assert "blendFactor" in doc
