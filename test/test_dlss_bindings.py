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

"""Surface tests for the optional DLSS bindings.

These need no GPU and must pass in BOTH build configurations: a default build, where the
NGX SDK is absent and the three names are None, and a DONUT_WITH_DLSS=ON build, where they
are real types. The point is the *contract* feature_demo.py relies on -- that the names
always exist so `pyd.DLSS is not None` is a valid test, rather than an AttributeError.
"""

from __future__ import annotations

import pytest

import pydonut as pyd

_DLSS_BUILT = pyd.DLSS is not None
_requires_dlss = pytest.mark.skipif(not _DLSS_BUILT, reason="built without DONUT_WITH_DLSS")


def test_names_always_exist_even_without_the_sdk() -> None:
    # The whole optional-feature contract: callers test for None, never catch AttributeError.
    for name in ("DLSS", "DLSSInitParameters", "DLSSEvaluateParameters"):
        assert hasattr(pyd, name)
        assert name in pyd.__all__


def test_the_three_names_agree_about_whether_dlss_is_built() -> None:
    # A build that exported the class but not its parameter structs would pass the None
    # check in feature_demo.py and then fail on the first DLSSInitParameters() call.
    present = [
        pyd.DLSS is not None,
        pyd.DLSSInitParameters is not None,
        pyd.DLSSEvaluateParameters is not None,
    ]
    assert len(set(present)) == 1, "DLSS names must all be present or all be None"


@_requires_dlss
def test_dlss_has_no_python_constructor() -> None:
    # DLSS is abstract; the concrete per-API subclass is chosen inside Create.
    assert pyd.DLSS is not None
    with pytest.raises(TypeError):
        pyd.DLSS()


@_requires_dlss
def test_dlss_exposes_the_methods_feature_demo_calls() -> None:
    assert pyd.DLSS is not None
    for name in (
        "Create",
        "GetRequiredVulkanExtensions",
        "Init",
        "Evaluate",
        "IsDlssSupported",
        "IsDlssInitialized",
        "IsRayReconstructionSupported",
        "IsRayReconstructionInitialized",
    ):
        assert callable(getattr(pyd.DLSS, name)), name


@_requires_dlss
def test_required_vulkan_extensions_returns_two_lists_of_strings() -> None:
    """The binding returns the lists rather than filling out-parameters.

    This is the one DLSS call that needs no device, so it is the only part of the API that
    can be exercised for real here. It must be callable BEFORE device creation -- that is
    the entire reason it exists -- so it deliberately does not touch a device.
    """
    assert pyd.DLSS is not None
    result = pyd.DLSS.GetRequiredVulkanExtensions()
    assert isinstance(result, tuple) and len(result) == 2
    instanceExtensions, deviceExtensions = result
    for extensions in (instanceExtensions, deviceExtensions):
        assert isinstance(extensions, list)
        assert all(isinstance(e, str) for e in extensions)
    # NGX needs at least one device extension; an empty pair would silently mean "no
    # extensions requested" and DLSS would then fail to initialise on Vulkan for no
    # visible reason.
    assert deviceExtensions


@_requires_dlss
def test_init_parameters_round_trip() -> None:
    assert pyd.DLSSInitParameters is not None
    params = pyd.DLSSInitParameters()
    # Defaults come from DLSS.h:49-55.
    assert params.inputWidth == 0 and params.outputWidth == 0
    assert params.useRayReconstruction is False
    params.inputWidth = 1920
    params.inputHeight = 1080
    params.outputWidth = 1920
    params.outputHeight = 1080
    params.useAutoExposure = True
    assert (params.inputWidth, params.inputHeight) == (1920, 1080)
    assert (params.outputWidth, params.outputHeight) == (1920, 1080)
    assert params.useAutoExposure is True


@_requires_dlss
def test_evaluate_parameters_texture_fields_default_to_none_and_accept_none() -> None:
    # The texture/buffer fields are bound as def_property over nvrhi handles, so this is
    # the check that the getter/setter pair is wired up rather than the field being
    # silently read-only. Real textures need a device, so only the None round-trip is
    # exercised here.
    assert pyd.DLSSEvaluateParameters is not None
    params = pyd.DLSSEvaluateParameters()
    for name in (
        "depthTexture",
        "motionVectorsTexture",
        "inputColorTexture",
        "outputColorTexture",
        "diffuseAlbedo",
        "specularAlbedo",
        "normalRoughness",
        "exposureBuffer",
    ):
        assert getattr(params, name) is None, name
        setattr(params, name, None)
        assert getattr(params, name) is None, name


@_requires_dlss
def test_evaluate_parameters_scalar_defaults_match_the_header() -> None:
    assert pyd.DLSSEvaluateParameters is not None
    params = pyd.DLSSEvaluateParameters()
    assert params.exposureScale == pytest.approx(1.0)  # DLSS.h:73
    assert params.sharpness == pytest.approx(0.0)
    assert params.resetHistory is False
    params.resetHistory = True
    assert params.resetHistory is True
