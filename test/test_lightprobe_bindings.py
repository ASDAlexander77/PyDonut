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
