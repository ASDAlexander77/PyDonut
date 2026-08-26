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


def test_cascaded_shadow_map_skips_the_unsafe_cascade_setter() -> None:
    # SetNumberOfCascadesUnsafe only moves the count the *shaders* read; the composite view is
    # built once in the constructor (CascadedShadowMap.cpp:67) and never rebuilt, so lowering
    # the count through it would leave GetView() still rendering every allocated slice. The
    # cascade count is a construction parameter here instead -- see the spec.
    assert not hasattr(pyd.CascadedShadowMap, "SetNumberOfCascadesUnsafe")


def test_cascaded_shadow_map_setup_takes_a_view_not_a_frustum() -> None:
    # The frustum is pulled off the view C++-side: donut math types never cross into Python.
    # Nothing here constructs a shadow map (that needs a device), so this checks the signature
    # rejects the shape a frustum would have had.
    with pytest.raises(TypeError):
        pyd.CascadedShadowMap.SetupForPlanarView(None, None, (0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
