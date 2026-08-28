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
"""Surface tests for the FeatureDemo stage 3a capture bindings.

These need no GPU: they construct no device and render nothing. Constructing a MipMapGenPass or
calling SaveTextureToFile needs a device, so those get presence-and-signature checks here and
are verified by running feature_demo.py in task 6.

FileDialog is never invoked here. It is a blocking modal -- GetSaveFileNameA on Windows,
`zenity` on Linux -- and calling it would hang a headless run until someone dismissed a window.
"""

from __future__ import annotations

import pytest

import pydonut as pyd


def test_mipmapgen_mode_binds_all_four_values() -> None:
    # MipMapGenPass::Mode has exactly these four (MipMapGenPass.h:47-52). pybind11's
    # native_enum casts C++ -> Python by constructing Mode(int), which raises ValueError for an
    # unbound value -- so a partial binding is a latent crash, not a missing convenience.
    # This is the stage 2c MaterialDomain lesson applied to a new enum.
    names = {mode.name for mode in pyd.MipMapGenPassMode}
    assert names == {"MODE_COLOR", "MODE_MIN", "MODE_MAX", "MODE_MINMAX"}
    assert pyd.MipMapGenPassMode.MODE_COLOR.value == 0
    assert pyd.MipMapGenPassMode.MODE_MIN.value == 1
    assert pyd.MipMapGenPassMode.MODE_MAX.value == 2
    assert pyd.MipMapGenPassMode.MODE_MINMAX.value == 3


def test_mipmapgen_pass_exposes_dispatch_and_display() -> None:
    # Dispatch reduces LOD 0 into LOD 1 and up; Display blits the levels in a spiral for
    # debugging. Constructing one needs a device and a texture allocated with mip levels.
    for name in ("Dispatch", "Display"):
        assert hasattr(pyd.MipMapGenPass, name), name


def test_mipmapgen_dispatch_defaults_to_every_level() -> None:
    # maxLOD = -1 means "all levels" (MipMapGenPass.h:63).
    #
    # pybind11 3.x on this build renders every integral input parameter as
    # "typing.SupportsInt | typing.SupportsIndex", never a bare "int" -- confirmed during
    # Task 2's review against pre-existing bindings unrelated to this plan.
    doc = pyd.MipMapGenPass.Dispatch.__doc__
    assert doc is not None
    assert "maxLOD: typing.SupportsInt | typing.SupportsIndex = -1" in doc


def test_mipmapgen_constructor_defaults_to_max_mode() -> None:
    # Matches the C++ default (MipMapGenPass.h:59). feature_demo.py passes MODE_COLOR
    # explicitly, since it reduces an RGB colour target rather than a single-channel one.
    doc = pyd.MipMapGenPass.__init__.__doc__
    assert doc is not None
    assert "MODE_MAX" in doc


def test_save_texture_to_file_is_exposed_with_an_alpha_default() -> None:
    # A free function in donut::engine (TextureCache.h:243-249), not a method. Calling it needs
    # a device, and the header requires no immediate command list be open at the time -- which
    # is why feature_demo.py calls it after executeCommandList.
    assert callable(pyd.SaveTextureToFile)
    doc = pyd.SaveTextureToFile.__doc__
    assert doc is not None
    assert "saveAlphaChannel: bool = True" in doc


def test_file_dialog_takes_filter_pairs_not_a_packed_buffer() -> None:
    # The C++ takes a double-NUL-terminated buffer and returns through a std::string& out-param
    # (UserInterfaceUtils.h:39). Both are hostile from Python -- embedded NULs do not survive a
    # str conversion -- so the binding takes (description, pattern) pairs and returns
    # Optional[str]. This is a deliberate signature change, not a literal port.
    assert callable(pyd.FileDialog)
    doc = pyd.FileDialog.__doc__
    assert doc is not None
    assert "bOpen: bool" in doc
    assert "filters" in doc


def test_file_dialog_rejects_a_malformed_filter_list() -> None:
    # Rejected by pybind11's argument caster, before the lambda body runs -- so no dialog opens
    # and this stays safe to run headless. A bare string is the mistake this guards against:
    # it is iterable, so a looser signature would silently accept it.
    with pytest.raises(TypeError):
        pyd.FileDialog(False, "BMP files")
    with pytest.raises(TypeError):
        pyd.FileDialog(False, [("BMP files",)])


def test_folder_dialog_stays_unbound() -> None:
    # Nothing in this repo needs it; deliberately skipped rather than overlooked.
    assert not hasattr(pyd, "FolderDialog")
