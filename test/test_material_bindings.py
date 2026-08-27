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
"""Surface tests for the FeatureDemo stage 2c material bindings.

These need no GPU: they construct no device and render nothing. Anything that needs a loaded
scene (GetMaterials returning real entries) or a live ImGui frame (MaterialEditor) is verified
by running the example instead, and gets a presence check here.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def test_material_id_is_readable() -> None:
    # Displayed in the editor window's "Material %d: %s" header. Assigned by the scene graph
    # when the material is registered, so a freshly constructed Material reads back the C++
    # default rather than anything meaningful -- this pins that it is exposed and is an int.
    material = pyd.Material()
    assert isinstance(material.materialID, int)


def test_material_id_is_read_only() -> None:
    # Bound read-only because the scene graph owns it -- writing it from Python would
    # desynchronise the material from the ID the MaterialID pass will resolve in stage 3.
    material = pyd.Material()
    with pytest.raises(AttributeError):
        material.materialID = 5


def test_scene_graph_exposes_get_materials() -> None:
    # A real call needs a loaded scene, since materials register through mesh geometry rather
    # than as scene-graph leaves (SceneGraph.cpp:542) -- an empty graph has none. Presence
    # here; the populated dropdown is a manual check in task 6.
    graph = pyd.SceneGraph()
    assert graph.GetMaterials() == []


def test_invalidate_content_is_callable_on_a_root_node() -> None:
    # Called when the editor changes a material's domain, so the scene re-sorts its draw
    # lists. Returns nothing and exposes no Python-readable state, so this asserts only that
    # the binding exists and does not raise -- the visible effect is a manual check.
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    graph.GetRootNode().InvalidateContent()


def test_material_editor_is_exported() -> None:
    # Never called from a test: it emits ImGui widgets, so it needs a live frame between
    # Begin and End. Presence only, the same treatment LightEditor gets in
    # test_light_bindings.py.
    assert callable(pyd.MaterialEditor)
