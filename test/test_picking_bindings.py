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
"""Surface tests for the FeatureDemo stage 3a picking bindings.

These need no GPU: they construct no device and render nothing. Constructing a MaterialIDPass
or a PixelReadbackPass needs a device, so those get presence-and-signature checks here and are
verified by running feature_demo.py in task 5.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def _graph_with_root() -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Returns a fresh graph and its real root node.

    SetRootNode returns the *previous* root (SceneGraph.cpp:670-679) -- None on a fresh
    graph -- so the root has to be read back with GetRootNode().
    """
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    return graph, graph.GetRootNode()


def test_material_id_pass_is_a_gbuffer_fill_pass() -> None:
    # MaterialIDPass derives from GBufferFillPass and overrides only Init and the protected
    # CreatePixelShader (GBufferFillPass.h:148-159), so it reuses that pass's create-parameters
    # and context types rather than getting its own. Constructing one needs a device.
    assert issubclass(pyd.MaterialIDPass, pyd.GBufferFillPass)
    assert issubclass(pyd.MaterialIDPass, pyd.IGeometryPass)


def test_material_id_pass_has_no_context_type_of_its_own() -> None:
    # Reusing GBufferFillPassContext is the point -- a "MaterialIDPassContext" would mean the
    # binding invented a type the C++ does not have.
    assert not hasattr(pyd, "MaterialIDPassContext")
    assert not hasattr(pyd, "MaterialIDPassCreateParameters")


def test_material_id_pass_exposes_init() -> None:
    doc = pyd.MaterialIDPass.Init.__doc__
    assert doc is not None
    assert "shaderFactory" in doc
    assert "params" in doc


def test_pixel_readback_pass_exposes_all_three_readers() -> None:
    # All three bind because the class is meaningless without whichever one matches the
    # caller's format, and each is a single line. feature_demo.py uses ReadUInts.
    for name in ("Capture", "ReadUInts", "ReadFloats", "ReadInts"):
        assert hasattr(pyd.PixelReadbackPass, name), name


def test_pixel_readback_capture_takes_flat_pixel_coordinates() -> None:
    # C++ takes a dm::uint2 (PixelReadbackPass.h:62); donut math types never cross into Python,
    # so it is flattened to two ints -- the same rule as PlanarView.SetPixelOffset.
    #
    # pybind11 3.x on this build renders every integral input parameter as
    # "typing.SupportsInt | typing.SupportsIndex", never a bare "int" -- confirmed against the
    # pre-existing, untouched CascadedShadowMap constructor binding, which shows the identical
    # pattern for its own uint32_t parameters. So this checks for the parameter names and the
    # ABSENCE of the math type, not a literal "x: int" spelling.
    doc = pyd.PixelReadbackPass.Capture.__doc__
    assert doc is not None
    assert "x: typing.SupportsInt" in doc
    assert "y: typing.SupportsInt" in doc
    assert "uint2" not in doc


def test_pixel_readback_constructor_defaults_the_subresource() -> None:
    # arraySlice and mipLevel default to 0 in C++ (PixelReadbackPass.h:59-60); the binding keeps
    # them optional rather than forcing every caller to pass them.
    #
    # Same pybind11 3.x rendering as above -- integral parameters show as
    # "typing.SupportsInt | typing.SupportsIndex", not "int".
    doc = pyd.PixelReadbackPass.__init__.__doc__
    assert doc is not None
    assert "arraySlice: typing.SupportsInt | typing.SupportsIndex = 0" in doc
    assert "mipLevel: typing.SupportsInt | typing.SupportsIndex = 0" in doc


def test_command_list_can_clear_a_uint_texture() -> None:
    # Needed to reset MaterialIDs to 0xffff before each pick. Mirrors clearTextureFloat: an
    # AllSubresources overload and a view-scoped one.
    doc = pyd.CommandList.clearTextureUInt.__doc__
    assert doc is not None
    assert "clearValue: typing.SupportsInt" in doc
    assert "view: donut::engine::IView" in doc


def test_global_bounding_box_returns_six_flat_floats() -> None:
    # dm::box3 does not cross into Python. A fresh node's box is box3::empty(), which is
    # mins = FLT_MAX and maxs = -FLT_MAX (box.h:139-143) -- so mins are GREATER than maxs here.
    # That sentinel is exactly what PointThirdPersonCameraAt has to guard against, since its
    # radius would otherwise be infinite.
    node = pyd.SceneGraphNode()
    bounds = node.GetGlobalBoundingBox()
    assert isinstance(bounds, tuple)
    assert len(bounds) == 6
    assert all(isinstance(v, float) for v in bounds)
    minX, minY, minZ, maxX, maxY, maxZ = bounds
    assert minX > maxX and minY > maxY and minZ > maxZ


def test_scene_graph_node_reports_its_path() -> None:
    # std::filesystem::path does not cross into Python either -- generic_string() C++-side.
    # Drives the "Picked node:" log line.
    #
    # SceneGraph binds no way to attach a bare node, only AttachLeafNode -- so the node under
    # test is the one that call returns, and the leaf is just the vehicle for creating it.
    graph, root = _graph_with_root()
    node = graph.AttachLeafNode(root, pyd.PointLight())
    node.SetName("nave")
    path = node.GetPath()
    assert isinstance(path, str)
    assert "nave" in path


def test_leaf_reports_its_owning_node() -> None:
    # A weak_ptr::lock(), so it legitimately returns None for a leaf that is not attached.
    # Bound on SceneGraphLeaf rather than MeshInstance so every leaf type gets it.
    #
    # `light` is freshly constructed and therefore attached rather than cloned -- AttachLeafNode
    # only clones a leaf that is already attached elsewhere (SceneGraph.cpp:844-847) -- so the
    # local object really is the one that ends up on the returned node.
    graph, root = _graph_with_root()
    light = pyd.PointLight()
    assert light.GetNodeSharedPtr() is None

    node = graph.AttachLeafNode(root, light)
    node.SetName("probe")

    owner = light.GetNodeSharedPtr()
    assert owner is not None
    # SceneGraphNode binds no GetName, so compare on the path instead.
    assert owner.GetPath() == node.GetPath()


def test_mesh_instance_inherits_the_owning_node_accessor() -> None:
    # MeshInstance.GetNode() already existed but returns a non-owning raw pointer. Picking
    # stores the node across frames, so it needs the shared_ptr form.
    assert hasattr(pyd.MeshInstance, "GetNodeSharedPtr")
    assert hasattr(pyd.MeshInstance, "GetNode")
