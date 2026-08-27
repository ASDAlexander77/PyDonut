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
"""Surface tests for the FeatureDemo stage 2b light bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a field that silently did not round-trip.
"""

from __future__ import annotations

import struct

import pytest

import pydonut as pyd


def _attached(light: pyd.Light) -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Puts `light` under a fresh graph's root and returns the graph and the light's node.

    SetPosition/SetDirection assert when a light has no node (SceneTypes.cpp:82, :100), and
    SceneGraphLeaf.SetName silently no-ops when the leaf has no node (SceneGraph.cpp:40-47), so
    every positional or naming test needs this much scaffolding. No device is involved.
    """
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    root = graph.GetRootNode()
    node = graph.AttachLeafNode(root, light)
    return graph, node


def test_scene_graph_leaf_name_round_trips() -> None:
    light = pyd.DirectionalLight()
    # Keep the (graph, node) tuple alive in `_`, even though neither name is used by name below:
    # dropping the return value entirely lets Python garbage-collect the SceneGraph immediately,
    # which detaches the node and makes SetName silently no-op (SceneGraph.cpp:40-47).
    _ = _attached(light)
    light.SetName("Sun")
    assert light.GetName() == "Sun"


def test_light_set_position_writes_the_nodes_world_transform() -> None:
    # SetPosition converts world space to parent-local and calls SceneGraphNode::SetTranslation
    # itself (SceneTypes.cpp:77-93). SetTranslation only marks the node dirty, so the world
    # transform GetWorldPosition reads back is the one Refresh recomputes.
    light = pyd.DirectionalLight()
    graph, node = _attached(light)
    light.SetPosition(1.0, 2.0, 3.0)
    graph.Refresh(0)
    assert node.GetWorldPosition() == pytest.approx((1.0, 2.0, 3.0))


def test_light_set_direction_leaves_the_position_alone() -> None:
    # SetDirection writes rotation and scaling through SetTransform(nullptr, &rotation,
    # &scaling) (SceneGraph.cpp:282-291), so the two setters are order-free.
    light = pyd.DirectionalLight()
    graph, node = _attached(light)
    light.SetPosition(1.0, 2.0, 3.0)
    light.SetDirection(0.0, -1.0, 0.0)
    graph.Refresh(0)
    assert node.GetWorldPosition() == pytest.approx((1.0, 2.0, 3.0))


def test_light_set_color_accepts_three_floats() -> None:
    # Setter only, matching SkyParameters' float3 fields -- there is no GetColor, because
    # nothing in the example reads a colour back and LightEditor writes the field from C++.
    # Proven via FillLightConstants instead: it is already bound and reachable, and its
    # LightConstants layout (light_cb.h:43-63) puts color right after direction(3f) +
    # lightType(i) + position(3f) + radius(f), i.e. at byte offset 32, as 3 packed floats.
    #
    # The light is attached first (via _attached()) because DirectionalLight::FillLightConstants
    # calls normalize(GetDirection()) (SceneTypes.cpp:133), which needs a valid node -- an
    # unattached light would give a degenerate/zero direction.
    light = pyd.DirectionalLight()
    # Keep the (graph, node) tuple alive in `_`: dropping it entirely would let Python
    # garbage-collect the SceneGraph immediately and detach the node before FillLightConstants
    # runs (see test_scene_graph_leaf_name_round_trips above for the same hazard).
    _ = _attached(light)
    light.SetColor(1.0, 0.5, 0.25)
    assert not hasattr(light, "GetColor")

    constants = light.FillLightConstants()
    color = struct.unpack_from("<3f", constants, 32)
    assert color == pytest.approx((1.0, 0.5, 0.25))


def test_spot_light_is_a_light() -> None:
    assert issubclass(pyd.SpotLight, pyd.Light)


def test_point_light_is_a_light() -> None:
    assert issubclass(pyd.PointLight, pyd.Light)


def test_spot_light_fields_round_trip() -> None:
    light = pyd.SpotLight()
    light.intensity = 60.0
    light.radius = 0.05
    light.range = 0.0
    light.innerAngle = 20.0
    light.outerAngle = 35.0
    # approx throughout: these are C++ floats, so 0.05 does not survive a round trip exactly.
    assert light.intensity == pytest.approx(60.0)
    assert light.radius == pytest.approx(0.05)
    assert light.range == pytest.approx(0.0)
    assert light.innerAngle == pytest.approx(20.0)
    assert light.outerAngle == pytest.approx(35.0)


def test_point_light_fields_round_trip() -> None:
    light = pyd.PointLight()
    light.intensity = 20.0
    light.radius = 0.05
    light.range = 0.0
    assert light.intensity == pytest.approx(20.0)
    assert light.radius == pytest.approx(0.05)
    assert light.range == pytest.approx(0.0)


def test_local_lights_cast_no_shadow_by_default() -> None:
    # Neither added light may get its own shadow map: DeferredLightingPass logs an error and
    # returns without rendering the frame when two lights present different shadow textures
    # (DeferredLightingPass.cpp:172-175).
    assert pyd.SpotLight().shadowMap is None
    assert pyd.PointLight().shadowMap is None


def test_get_lights_returns_the_concrete_light_types() -> None:
    # The Lights UI and LightEditor both depend on this: GetLights() is typed as a list of
    # Light in C++, and pybind must hand back the most-derived registered type so the editor
    # dispatches correctly and so `is` comparisons against the stored selection hold.
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    root = graph.GetRootNode()

    spot = pyd.SpotLight()
    point = pyd.PointLight()
    graph.AttachLeafNode(root, spot)
    graph.AttachLeafNode(root, point)
    spot.SetName("Spot")
    point.SetName("Point")

    lights = graph.GetLights()
    assert [light.GetName() for light in lights] == ["Spot", "Point"]
    assert isinstance(lights[0], pyd.SpotLight)
    assert isinstance(lights[1], pyd.PointLight)
    assert lights[0] is spot
    assert lights[1] is point


def test_light_editor_is_exported() -> None:
    # Never called from a test: it emits ImGui widgets, so it needs a live frame between
    # Begin and End. Presence only, the same treatment the ImGui surface gets in
    # test_postprocess_bindings.py:227.
    assert callable(pyd.LightEditor)


def test_set_root_node_returns_the_previous_root_not_the_new_one() -> None:
    # SceneGraph::SetRootNode (SceneGraph.cpp:670-679) returns the *previous* root, which is
    # None on a fresh graph -- not the node just passed in. Two earlier tasks in this plan each
    # wrote `root = graph.SetRootNode(node)` and used the (None) result as AttachLeafNode's
    # parent, silently replacing the graph's root on every subsequent attach. Use
    # GetRootNode() instead. This test pins the surprising return value so nobody reintroduces
    # the mistake.
    graph = pyd.SceneGraph()
    assert graph.SetRootNode(pyd.SceneGraphNode()) is None
