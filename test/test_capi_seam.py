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

"""Tests for the C interop seam that companion modules (PyRTXPT) build against.

No GPU needed: these check the *contract* a consumer relies on at import time -- the capsule
exists under exactly the name PyDonut_ImportCAPI() looks for, and the table behind it is
populated with a matching version and a plausible size. Getting the capsule name wrong, or
shipping a table whose struct_size disagrees with the header, fails only inside the consumer's
C extension init, where the error is far harder to read than it is here.

The table is read through ctypes rather than by building a second extension module, so this
runs in ordinary CI.
"""

from __future__ import annotations

import ctypes
import os

import pytest

import pydonut as pyd
from pydonut import _pydonut

_CAPSULE_NAME = b"pydonut._pydonut._C_API"

# The two uint32 fields the header guarantees come first, at a fixed offset, precisely so that
# a mismatched consumer can read them before trusting the rest. Mirrored here for the same
# reason -- this test must keep working across appends to the table.
class _CapiHead(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
    ]


# Unwrap takes a PyObject* and returns a borrowed C pointer; Wrap takes a C pointer and returns
# a NEW reference (ctypes' py_object restype consumes exactly that).
#
# PYFUNCTYPE, *not* CFUNCTYPE: CFUNCTYPE releases the GIL around the call, and every function in
# this table requires it held (they call into pybind11 and set Python errors). Calling them
# through CFUNCTYPE access-violates as soon as one touches Python state -- which is a faithful
# demonstration of the header's GIL rule, just not something to reproduce on every test run.
_UNWRAP = ctypes.PYFUNCTYPE(ctypes.c_void_p, ctypes.py_object)
_WRAP = ctypes.PYFUNCTYPE(ctypes.py_object, ctypes.c_void_p)


class _Capi(ctypes.Structure):
    """Full mirror of PyDonut_CAPI, in declaration order, so the accessors can be called.

    Every field up to the one under test has to be declared for its offset to land right, so
    this deliberately duplicates the header's ordering: if a slot is ever reordered rather than
    appended, the calls below start hitting the wrong function. Appending stays safe -- fields
    past the end of this mirror are simply not read.
    """

    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
        ("build_config", ctypes.c_char_p),
        ("UnwrapDevice", _UNWRAP),
        ("UnwrapCommandList", _UNWRAP),
        ("UnwrapTexture", _UNWRAP),
        ("UnwrapBuffer", _UNWRAP),
        ("UnwrapFramebuffer", _UNWRAP),
        ("UnwrapSampler", _UNWRAP),
        ("UnwrapBindingLayout", _UNWRAP),
        ("UnwrapBindingSet", _UNWRAP),
        ("UnwrapShader", _UNWRAP),
        ("UnwrapAccelStruct", _UNWRAP),
        ("UnwrapDeviceManager", _UNWRAP),
        ("UnwrapShaderFactory", _UNWRAP),
        ("UnwrapCommonRenderPasses", _UNWRAP),
        ("UnwrapDescriptorTableManager", _UNWRAP),
        ("UnwrapTextureCache", _UNWRAP),
        ("UnwrapFramebufferFactory", _UNWRAP),
        ("UnwrapScene", _UNWRAP),
        ("UnwrapSceneGraph", _UNWRAP),
        ("UnwrapView", _UNWRAP),
        ("WrapCommandList", _WRAP),
        ("WrapTexture", _WRAP),
        ("WrapBuffer", _WRAP),
        ("WrapFramebuffer", _WRAP),
        ("WrapSampler", _WRAP),
        ("WrapBindingLayout", _WRAP),
        ("WrapBindingSet", _WRAP),
        ("WrapShader", _WRAP),
        ("WrapAccelStruct", _WRAP),
    ]


def _capsule_address() -> int:
    get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
    get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    get_pointer.restype = ctypes.c_void_p

    address = get_pointer(_pydonut._C_API, _CAPSULE_NAME)
    assert address, "PyCapsule_GetPointer returned NULL for the _C_API capsule"
    return address


def _capsule_head() -> _CapiHead:
    """Dereference the _C_API capsule and read the identity fields off the front of the table."""
    return _CapiHead.from_address(_capsule_address())


def _capi() -> _Capi:
    return _Capi.from_address(_capsule_address())


def _error_is_set() -> bool:
    occurred = ctypes.pythonapi.PyErr_Occurred
    occurred.restype = ctypes.c_void_p
    occurred.argtypes = []
    return bool(occurred())


def _clear_error() -> None:
    clear = ctypes.pythonapi.PyErr_Clear
    clear.restype = None
    clear.argtypes = []
    clear()


def test_capsule_exists_under_the_documented_name() -> None:
    is_valid = ctypes.pythonapi.PyCapsule_IsValid
    is_valid.argtypes = [ctypes.py_object, ctypes.c_char_p]
    is_valid.restype = ctypes.c_int

    assert is_valid(_pydonut._C_API, _CAPSULE_NAME) == 1, (
        "the _C_API capsule is missing or carries a different name than "
        "PYDONUT_CAPI_CAPSULE_NAME in include/pydonut/pydonut_capi.h"
    )


def test_capsule_name_is_matched_exactly() -> None:
    """A near-miss name must NOT validate -- PyCapsule_GetPointer compares the whole string."""
    is_valid = ctypes.pythonapi.PyCapsule_IsValid
    is_valid.argtypes = [ctypes.py_object, ctypes.c_char_p]
    is_valid.restype = ctypes.c_int

    assert is_valid(_pydonut._C_API, b"pydonut._C_API") == 0


def test_abi_version_matches_the_python_visible_constant() -> None:
    head = _capsule_head()
    assert head.abi_version == pyd.CAPI_ABI_VERSION
    # A companion package gates on this before loading its own extension, so a zero or absurd
    # value would silently disable that check rather than trip it.
    assert head.abi_version >= 1


def test_struct_size_covers_the_whole_table() -> None:
    """struct_size drives the consumer's append-only compatibility check, so it must be real.

    A too-small value makes a valid consumer refuse to load; a bogus large one lets it call
    through a pointer that was never filled in. The table currently holds three leading fields
    (two uint32 plus a char*) and 28 function pointers, so bound it well below and above that
    without pinning the exact count, which is expected to grow.
    """
    head = _capsule_head()
    pointer_size = ctypes.sizeof(ctypes.c_void_p)

    assert head.struct_size > ctypes.sizeof(_CapiHead)
    # At least the char* plus a good number of function pointers.
    assert head.struct_size >= ctypes.sizeof(_CapiHead) + 20 * pointer_size
    # Sanity ceiling: catches an uninitialised or garbage value without constraining growth.
    assert head.struct_size <= ctypes.sizeof(_CapiHead) + 512 * pointer_size


def test_build_config_reports_at_least_one_backend() -> None:
    config = pyd.CAPI_BUILD_CONFIG
    assert isinstance(config, str)
    # Every supported configuration has D3D12, Vulkan or both; a build with neither could not
    # have produced a working module, so an empty string here means the macros went unread.
    assert "d3d12," in config or "vulkan," in config


def test_get_include_points_at_the_seam_header() -> None:
    """The path get_include() hands a compiler must really contain the header.

    This is the check that catches the editable-install trap: `uv sync` serves __init__.py from
    src/pydonut while _pydonut and the installed header live in site-packages, so a get_include
    anchored on __init__.py's directory returns a path that has never held the header. Asserting
    only the path's shape would pass in exactly that broken case.
    """
    include_dir = pyd.get_include()
    assert os.path.isabs(include_dir)
    assert os.path.basename(include_dir) == "include"
    assert os.path.isfile(os.path.join(include_dir, "pydonut", "pydonut_capi.h")), (
        f"get_include() returned {include_dir!r}, which does not contain "
        "pydonut/pydonut_capi.h"
    )


def test_every_accessor_slot_is_populated() -> None:
    """A NULL slot is the failure mode a consumer cannot defend against -- it just crashes."""
    api = _capi()
    for name, _type in _Capi._fields_[3:]:
        assert ctypes.cast(getattr(api, name), ctypes.c_void_p).value, f"{name} is NULL"


def test_unwrap_none_yields_null_without_an_error() -> None:
    """None must read as "no object", not as a failure.

    Consumers separate the two by checking PyErr_Occurred() after a NULL return, so if None set
    a TypeError here, passing an optional argument would look like a bug in the caller.
    """
    api = _capi()
    assert not api.UnwrapTexture(None)
    assert not _error_is_set()

    assert not api.UnwrapDevice(None)
    assert not _error_is_set()


def test_unwrap_wrong_type_sets_a_typeerror() -> None:
    """A wrong-typed argument must report a TypeError rather than return a garbage pointer.

    The accessor sets the error and returns NULL; ctypes checks PyErr_Occurred() after a
    PYFUNCTYPE call and re-raises, so it surfaces here as a plain TypeError. A consumer sees the
    same thing one level lower, as a NULL return with the error already set.
    """
    api = _capi()
    with pytest.raises(TypeError):
        api.UnwrapTexture("clearly not a texture")

    # And nothing is left set behind for the next caller to trip over.
    assert not _error_is_set()


def test_wrap_null_returns_none() -> None:
    """Wrapping a null pointer is the documented way to hand Python back an absent resource."""
    api = _capi()
    assert api.WrapTexture(None) is None
    assert api.WrapBuffer(None) is None
    assert not _error_is_set()
