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
"""Surface tests for the FeatureDemo stage 2c camera bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a field that silently did not round-trip, a reference-returning getter that hands
back a copy.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def _graph_with_root() -> tuple[pyd.SceneGraph, pyd.SceneGraphNode]:
    """Returns a fresh graph and its real root node.

    SetRootNode returns the *previous* root (SceneGraph.cpp:670-679) -- None on a fresh
    graph -- so the root has to be read back with GetRootNode(). Passing SetRootNode's
    result as AttachLeafNode's parent silently re-roots the graph on every attach instead
    of adding siblings.
    """
    graph = pyd.SceneGraph()
    graph.SetRootNode(pyd.SceneGraphNode())
    return graph, graph.GetRootNode()


def test_scene_camera_is_not_constructible() -> None:
    # SceneCamera inherits SceneGraphLeaf::Clone() pure (SceneGraph.h:67) and does not
    # override it, so it is abstract and binds base-only -- the same shape as Light.
    with pytest.raises(TypeError):
        pyd.SceneCamera()


def test_perspective_camera_is_a_scene_camera() -> None:
    assert issubclass(pyd.PerspectiveCamera, pyd.SceneCamera)


def test_perspective_camera_is_a_scene_graph_leaf() -> None:
    # The dropdown labels cameras with SceneGraphLeaf.GetName, and CreateSceneCameras
    # attaches them with AttachLeafNode -- both need this inheritance edge to be registered.
    assert issubclass(pyd.PerspectiveCamera, pyd.SceneGraphLeaf)


def test_perspective_camera_fields_round_trip() -> None:
    camera = pyd.PerspectiveCamera()
    camera.zNear = 0.1
    camera.verticalFov = 1.047  # radians, NOT degrees (SceneGraph.h:158)
    # approx: these are C++ floats, so neither value survives a round trip exactly.
    assert camera.zNear == pytest.approx(0.1)
    assert camera.verticalFov == pytest.approx(1.047)


def test_get_cameras_returns_the_concrete_camera_types() -> None:
    # SwitchableCamera.GetSceneCameraProjectionParams dynamic_pointer_casts to
    # PerspectiveCamera (Camera.cpp:522-532), and the dropdown's `is` check compares against
    # the stored selection -- both need pybind to hand back the most-derived registered type.
    graph, root = _graph_with_root()

    nave = pyd.PerspectiveCamera()
    gallery = pyd.PerspectiveCamera()
    graph.AttachLeafNode(root, nave)
    graph.AttachLeafNode(root, gallery)
    nave.SetName("Nave")
    gallery.SetName("Gallery")

    cameras = graph.GetCameras()
    assert [camera.GetName() for camera in cameras] == ["Nave", "Gallery"]
    assert isinstance(cameras[0], pyd.PerspectiveCamera)
    assert cameras[0] is nave
    assert cameras[1] is gallery


def test_set_position_and_direction_writes_the_nodes_world_transform() -> None:
    # Light.SetPosition/SetDirection are declared on Light (SceneGraph.h:199-200), not on
    # SceneGraphLeaf, so a camera cannot be placed the way a light is. This node-level
    # equivalent is how CreateSceneCameras positions its cameras.
    #
    # SetTranslation only marks the node dirty, so the world transform GetWorldPosition reads
    # back is the one Refresh recomputes.
    graph, root = _graph_with_root()
    camera = pyd.PerspectiveCamera()
    node = graph.AttachLeafNode(root, camera)

    node.SetPositionAndDirection(-8.0, 2.0, 0.0, 1.0, 0.0, 0.0)
    graph.Refresh(0)

    assert node.GetWorldPosition() == pytest.approx((-8.0, 2.0, 0.0))


def test_switchable_camera_starts_in_third_person() -> None:
    # m_UseFirstPerson defaults to false and m_SceneCamera starts null (Camera.h:259-261), so
    # a fresh SwitchableCamera is in THIRD person. The example starts first-person, so Init
    # must switch explicitly. Pinned here because getting it wrong changes the example's
    # starting camera silently, with nothing else to catch it.
    camera = pyd.SwitchableCamera()
    assert camera.IsThirdPersonActive()
    assert not camera.IsFirstPersonActive()
    assert not camera.IsSceneCameraActive()


def test_switch_to_first_person_makes_it_active() -> None:
    camera = pyd.SwitchableCamera()
    camera.SwitchToFirstPerson(copyView=False)
    assert camera.IsFirstPersonActive()
    assert not camera.IsThirdPersonActive()


def test_get_first_person_camera_returns_the_owned_camera_not_a_copy() -> None:
    # Bound with return_value_policy::reference_internal. If it handed back a copy instead,
    # Init's LookAt/SetMoveSpeed would be written to a temporary and thrown away -- the
    # example would silently start at the origin. Two separate calls must see one object.
    camera = pyd.SwitchableCamera()
    camera.GetFirstPersonCamera().LookAt(0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    assert camera.GetFirstPersonCamera().GetDir() == pytest.approx((1.0, 0.0, 0.0))


def test_switch_to_scene_camera_activates_the_scene_camera() -> None:
    graph, root = _graph_with_root()
    sceneCamera = pyd.PerspectiveCamera()
    graph.AttachLeafNode(root, sceneCamera)

    camera = pyd.SwitchableCamera()
    camera.SwitchToSceneCamera(sceneCamera)

    assert camera.IsSceneCameraActive()
    assert not camera.IsFirstPersonActive()
    assert not camera.IsThirdPersonActive()
    assert camera.GetSceneCamera() is sceneCamera


def test_switch_to_scene_camera_rejects_none() -> None:
    # C++ guards this with assert(!!sceneCamera) (Camera.cpp:578-582), which compiles out in
    # this project's Release build -- a None would become a null dereference on the next
    # frame's GetWorldToViewMatrix rather than an error here.
    camera = pyd.SwitchableCamera()
    with pytest.raises(ValueError):
        camera.SwitchToSceneCamera(None)


def test_set_matrices_from_switchable_camera_accepts_every_camera_state() -> None:
    # No device needed: PlanarView and SwitchableCamera are both constructible standalone and
    # this only computes matrices. PlanarView exposes no matrix getters, so this asserts the
    # shim runs rather than checking the values -- including the scene-camera branch, where
    # GetSceneCameraProjectionParams overrides fov and zNear. The rendered result is a manual
    # check in tasks 4-5.
    graph, root = _graph_with_root()
    sceneCamera = pyd.PerspectiveCamera()
    graph.AttachLeafNode(root, sceneCamera)
    sceneCamera.verticalFov = 0.7
    sceneCamera.zNear = 0.2

    view = pyd.PlanarView()
    camera = pyd.SwitchableCamera()

    camera.SwitchToFirstPerson(copyView=False)
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0)

    camera.SwitchToThirdPerson(copyView=False)
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0)

    camera.SwitchToSceneCamera(sceneCamera)
    view.SetMatricesFromSwitchableCamera(camera, 16.0 / 9.0)
