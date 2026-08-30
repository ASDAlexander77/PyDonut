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

"""Surface tests for the async_compute multi-queue bindings.

These need no GPU: they construct no device and render nothing. They exist to catch
binding-layer mistakes -- a class missing from __init__.py's re-exports, a typo'd method
name, a chained setter that returns a copy instead of self.
"""

from __future__ import annotations

import pathlib
import struct

import pytest

import pydonut as pyd


def test_lifetime_tracker_is_exported() -> None:
    assert hasattr(pyd, "CommandListLifetimeTracker")
    assert "CommandListLifetimeTracker" in pyd.__all__


def test_lifetime_tracker_has_no_python_constructor() -> None:
    # Device-only construction: nvrhi hands out exactly one owning reference per
    # createCommandListLifetimeTracker call (nvrhi.h:3764), and there is no standalone
    # constructor to bind.
    with pytest.raises(TypeError):
        pyd.CommandListLifetimeTracker()


def test_lifetime_tracker_exposes_run_garbage_collection() -> None:
    assert callable(pyd.CommandListLifetimeTracker.runGarbageCollection)


def test_device_exposes_create_lifetime_tracker() -> None:
    assert hasattr(pyd.Device, "createCommandListLifetimeTracker")


def test_set_queue_type_returns_self_so_calls_chain() -> None:
    # py::return_value_policy::reference keeps Python object identity, so `is` holds --
    # verified against the existing setEnableImmediateExecution binding.
    params = pyd.CommandListParameters()
    assert params.setQueueType(pyd.CommandQueue.Compute) is params


def test_set_queue_type_accepts_every_queue() -> None:
    params = pyd.CommandListParameters()
    for queue in (pyd.CommandQueue.Graphics, pyd.CommandQueue.Compute, pyd.CommandQueue.Copy):
        assert params.setQueueType(queue) is params


def test_set_lifetime_tracker_is_bound_and_chains() -> None:
    # None is a valid tracker (nvrhi.h:3135 defaults it to nullptr, meaning "use the device's
    # own trackers"), so this exercises the binding without needing a device.
    params = pyd.CommandListParameters()
    assert params.setLifetimeTracker(None) is params


def test_parameters_setters_chain_together() -> None:
    params = pyd.CommandListParameters()
    chained = (
        params.setEnableImmediateExecution(False)
        .setQueueType(pyd.CommandQueue.Compute)
        .setLifetimeTracker(None)
    )
    assert chained is params


def test_device_exposes_queue_wait_for_command_list() -> None:
    assert hasattr(pyd.Device, "queueWaitForCommandList")


def test_binding_cache_exposes_get_or_create_binding_set() -> None:
    # BindingCache previously bound only Clear(). GetOrCreateBindingSet is what lets the
    # compute thread build its per-texture UAV binding set without a device round-trip
    # every tick (BindingCache.h:53).
    assert callable(pyd.BindingCache.GetOrCreateBindingSet)


def test_binding_cache_still_exposes_clear() -> None:
    # Guards against the new .def() replacing the chain rather than extending it.
    assert callable(pyd.BindingCache.Clear)


def test_submit_path_bindings_are_still_callable_after_gil_change() -> None:
    """The GIL-release widening is a call_guard change only -- no signature may shift.

    This cannot observe GIL behaviour without a GPU. It is a guard against the edit
    accidentally dropping an argument name or a default while adding the call_guard.
    """
    # pybind11 records argument names in the docstring signature. `or ""` satisfies the type
    # checker, which can't prove these docstrings are non-None -- pybind11 always generates one.
    execute_doc = pyd.Device.executeCommandList.__doc__ or ""
    compute_state_doc = pyd.CommandList.setComputeState.__doc__ or ""
    dispatch_doc = pyd.CommandList.dispatch.__doc__ or ""
    assert "commandList" in execute_doc
    assert "executionQueue" in execute_doc
    assert "state" in compute_state_doc
    for name in ("groupsX", "groupsY", "groupsZ"):
        assert name in dispatch_doc


_DONUT_INCLUDE = str(pathlib.Path(__file__).resolve().parent.parent / "extern" / "donut" / "include")
_SHADER = pathlib.Path(__file__).resolve().parent.parent / "shaders" / "async_compute" / "shaders.hlsl"


@pytest.mark.skipif(pyd.CompileShader is None, reason="native module built without DXC")
@pytest.mark.parametrize(
    "entry,shader_type",
    [
        ("main_vs", pyd.ShaderType.Vertex),
        ("main_ps", pyd.ShaderType.Pixel),
        ("main_cs", pyd.ShaderType.Compute),
    ],
)
def test_shader_entry_points_compile_to_spirv(entry, shader_type) -> None:
    """Compiles for Vulkan, which needs no device and works on every platform.

    This is the one behavioural check available without a GPU: it proves the shader's
    binding_helpers.hlsli include resolves and that all three entry points exist with the
    names async_compute.py passes.
    """
    assert pyd.CompileShader is not None
    bytecode = pyd.CompileShader(
        _SHADER.read_text(encoding="utf-8"),
        entry,
        shader_type,
        pyd.GraphicsAPI.Vulkan,
        sourceName="shaders.hlsl",
        includePaths=[_DONUT_INCLUDE],
    )
    assert len(bytecode) > 0


def _opvariable_storage_classes(spirv: bytes) -> set[int]:
    """Storage class of every OpVariable in a SPIR-V module.

    Hand-decoded rather than pulled from a SPIR-V toolchain: the module header is five
    words, then a flat instruction stream whose every word packs word-count in the high
    16 bits and opcode in the low 16. That is enough to walk it without a dependency.
    """
    words = struct.unpack("<%dI" % (len(spirv) // 4), spirv)
    assert words[0] == 0x07230203, "not a SPIR-V module"
    classes, i = set(), 5
    while i < len(words):
        wordCount, opcode = words[i] >> 16, words[i] & 0xFFFF
        assert wordCount > 0, "malformed SPIR-V instruction"
        if opcode == 59:  # OpVariable: result-type, result-id, storage-class
            classes.add(words[i + 3])
        i += wordCount
    return classes


_STORAGE_CLASS_UNIFORM = 2
_STORAGE_CLASS_PUSH_CONSTANT = 9


@pytest.mark.skipif(pyd.CompileShader is None, reason="native module built without DXC")
def test_vulkan_compile_defines_spirv_so_push_constants_stay_push_constants() -> None:
    """CompileShader must define SPIRV/TARGET_VULKAN the way ShaderMake does.

    binding_helpers.hlsli gates [[vk::push_constant]] on those macros, so without them
    DECLARE_PUSH_CONSTANTS quietly degrades to `cbuffer : register(b0)` -- which the
    b-shift maps to binding 256, a descriptor nvrhi never writes because its layout
    declares a real VkPushConstantRange. DXC reports nothing; only the Vulkan validation
    layer does, at dispatch time, on a machine with a GPU. Asserting on the storage class
    catches it here instead.
    """
    assert pyd.CompileShader is not None
    bytecode = pyd.CompileShader(
        _SHADER.read_text(encoding="utf-8"),
        "main_cs",
        pyd.ShaderType.Compute,
        pyd.GraphicsAPI.Vulkan,
        sourceName="shaders.hlsl",
        includePaths=[_DONUT_INCLUDE],
    )
    classes = _opvariable_storage_classes(bytecode)
    assert _STORAGE_CLASS_PUSH_CONSTANT in classes
    assert _STORAGE_CLASS_UNIFORM not in classes
