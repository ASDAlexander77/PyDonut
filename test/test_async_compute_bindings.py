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
