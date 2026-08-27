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

import pytest

import pydonut as pyd


def _attached(light: pyd.Light) -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Puts `light` under a fresh graph's root and returns the graph and the light's node.

    SetPosition/SetDirection assert when a light has no node (SceneTypes.cpp:82, :100), so
    every positional test needs this much scaffolding. No device is involved.
    """
    graph = pyd.SceneGraph()
    root = graph.SetRootNode(pyd.SceneGraphNode())
    node = graph.AttachLeafNode(root, light)
    return graph, node


def test_scene_graph_leaf_name_round_trips() -> None:
    light = pyd.DirectionalLight()
    graph, node = _attached(light)
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
    light = pyd.DirectionalLight()
    light.SetColor(1.0, 0.5, 0.25)
    assert not hasattr(light, "GetColor")
