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
"""Surface tests for the FeatureDemo stage 3a stereo bindings.

These need no GPU: PlanarView and SwitchableCamera are both constructible standalone, and the
matrix work is pure math. PlanarView exposes no matrix getters, so the observable used
throughout is FillPlanarViewConstants(), which returns the raw constant-buffer bytes -- two
views whose matrices differ produce different bytes.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def _stereo_view_with_matrices() -> pyd.StereoPlanarView:
    """A stereo view with both eyes' matrices set from a default first-person camera."""
    view = pyd.StereoPlanarView()
    camera = pyd.SwitchableCamera()
    # copyView=False: SwitchableCamera starts on the third-person camera, and copying its view
    # into the first-person one would overwrite the default this test relies on.
    camera.SwitchToFirstPerson(copyView=False)
    # Per-eye aspect ratio: each eye owns half the framebuffer width.
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0 * 0.5)
    view.LeftView.UpdateCache()
    view.RightView.UpdateCache()
    return view


def test_stereo_planar_view_is_an_iview() -> None:
    # It has to reach every pass widened in task 1, all of which take IView or ICompositeView.
    assert issubclass(pyd.StereoPlanarView, pyd.IView)
    assert issubclass(pyd.StereoPlanarView, pyd.ICompositeView)


def test_stereo_planar_view_is_constructible_and_copyable() -> None:
    # The copy constructor is how the render tail snapshots this frame's view as next frame's
    # previous view, mirroring PlanarView's (FeatureDemo.cpp:753).
    view = pyd.StereoPlanarView()
    copied = pyd.StereoPlanarView(view)
    assert isinstance(copied, pyd.StereoPlanarView)


def test_eye_views_are_planar_views() -> None:
    view = pyd.StereoPlanarView()
    assert isinstance(view.LeftView, pyd.PlanarView)
    assert isinstance(view.RightView, pyd.PlanarView)


def test_eye_views_are_live_references_not_copies() -> None:
    # This is the whole point of reference_internal. If LeftView handed back a copy, the
    # SetViewport below would land on a temporary and the second, separate property access
    # would still see the original state -- so the constants would come back unchanged.
    view = pyd.StereoPlanarView()
    view.LeftView.UpdateCache()
    before = view.LeftView.FillPlanarViewConstants()

    view.LeftView.SetViewport(pyd.Viewport(640.0, 480.0))
    view.LeftView.UpdateCache()
    after = view.LeftView.FillPlanarViewConstants()

    assert after != before


def test_writing_one_eye_does_not_disturb_the_other() -> None:
    # Confirms LeftView and RightView are distinct members, not two views of one.
    view = pyd.StereoPlanarView()
    view.RightView.UpdateCache()
    rightBefore = view.RightView.FillPlanarViewConstants()

    view.LeftView.SetViewport(pyd.Viewport(640.0, 480.0))
    view.LeftView.UpdateCache()

    assert view.RightView.FillPlanarViewConstants() == rightBefore


def test_the_two_eyes_get_different_matrices() -> None:
    # The observable proxy for the eye offset: matrices do not cross into Python, but the right
    # eye's view matrix is the left's translated along X, so their constants must differ.
    # Neither viewport is touched here, so the matrices are the only thing that can differ.
    view = _stereo_view_with_matrices()
    assert view.LeftView.FillPlanarViewConstants() != view.RightView.FillPlanarViewConstants()


def test_eye_separation_is_adjustable_and_defaults_to_the_sample_value() -> None:
    # FeatureDemo.cpp:741 hardcodes 0.2 world units; it is a named argument here so the example
    # does not have to repeat the magic number, and so the effect is testable.
    doc = pyd.StereoPlanarView.SetMatricesFromSwitchableCamera.__doc__
    assert doc is not None
    assert "eyeSeparation: typing.SupportsFloat | typing.SupportsIndex = 0.2" in doc

    camera = pyd.SwitchableCamera()
    camera.SwitchToFirstPerson(copyView=False)

    wide = pyd.StereoPlanarView()
    wide.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0 * 0.5, eyeSeparation=2.0)
    wide.RightView.UpdateCache()

    narrow = pyd.StereoPlanarView()
    narrow.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0 * 0.5, eyeSeparation=0.2)
    narrow.RightView.UpdateCache()

    assert wide.RightView.FillPlanarViewConstants() != narrow.RightView.FillPlanarViewConstants()


def test_stereo_view_has_no_update_cache_of_its_own() -> None:
    # StereoView declares none -- the caches live on the two child PlanarViews, and each has to
    # be updated individually (FeatureDemo.cpp:748-749). A bound UpdateCache here would be an
    # invention that silently did nothing.
    assert not hasattr(pyd.StereoPlanarView, "UpdateCache")
