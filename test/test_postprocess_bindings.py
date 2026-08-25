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
