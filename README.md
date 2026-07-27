# PyDonut

Python bindings for [NVIDIA Donut](https://github.com/NVIDIA-RTX/Donut), a rendering framework built on top of [NVRHI](https://github.com/NVIDIA-RTX/NVRHI) (NVIDIA Rendering Hardware Interface). PyDonut lets you write graphics applications in Python that target **Direct3D 12** or **Vulkan** through the same abstraction Donut/NVRHI expose in C++.

The native side is a Python extension module (`_pydonut`) built with [pybind11](https://github.com/pybind/pybind11), statically linking Donut's core/engine/app libraries, NVRHI, GLFW, and ImGui. It's packaged with [scikit-build-core](https://github.com/scikit-build/scikit-build-core) and managed with [uv](https://github.com/astral-sh/uv).

## Features

- Window and device management (`DeviceManager`) with a message-loop render pass model (`IRenderPass`), similar to Donut's C++ samples.
- Graphics pipeline, command list, framebuffer, and shader APIs exposed to Python (`GraphicsPipeline`, `CommandList`, `Framebuffer`, `Shader`, ...).
- Support for both D3D12 and Vulkan backends, selectable at runtime.
- Optional in-process HLSL shader compilation via DXC (`pyd.CompileShader`), producing DXIL or SPIR-V depending on the selected backend.
- Type stubs (`_pydonut.pyi`, `py.typed`) for editor autocompletion.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package/project manager)
- Python 3.14 (uv will install/select this automatically based on `.python-version`)
- Git (with submodule support)
- A C++20 compiler and CMake (scikit-build-core will drive the CMake/Ninja build during `uv sync`)
- **Windows:** Visual Studio 2022 (Desktop development with C++) or the equivalent Build Tools
- **Linux:** GCC/Clang toolchain, plus the system packages listed below for building GLFW

Optional, for `pyd.CompileShader` (in-process HLSL compilation):

- [DXC](https://github.com/microsoft/DirectXShaderCompiler) — point `SHADERMAKE_DXC_PATH` at your DXC install. Without it, `uv sync` still succeeds but prints a warning and `CompileShader` is unavailable.

## Installation

### 1. Clone and sync submodules (Windows & Linux)

```sh
git clone <this-repo-url>
cd PyDonut
git submodule update --init --recursive
```

### 2. Windows

```powershell
uv sync
```

This builds the `_pydonut` native module (with D3D12 and Vulkan enabled) and installs the project into a local virtual environment (`.venv`).

### 3. Linux

Install the system packages needed to build GLFW (pulled in from the vendored `extern/donut` submodule) — not installed by default on Debian/Ubuntu:

```sh
sudo apt-get install -y pkg-config libxkbcommon-dev libx11-dev libxrandr-dev \
    libxinerama-dev libxcursor-dev libxi-dev libgl1-mesa-dev libwayland-dev wayland-protocols
```

Then sync as usual:

```sh
uv sync
```

> Note: D3D12 is a Windows-only backend; on Linux the module builds with Vulkan support.

### 4. Enabling `pyd.CompileShader` (optional, both platforms)

Install DXC and set `SHADERMAKE_DXC_PATH` to point at it before running `uv sync`, e.g.:

```sh
export SHADERMAKE_DXC_PATH=/path/to/dxc/bin/dxc   # Linux
set SHADERMAKE_DXC_PATH=C:\path\to\dxc\bin\dxc.exe  # Windows (cmd)
```

## Running the example

`main.py` renders a basic textured triangle using `pydonut`:

```sh
uv run main.py
```

Useful flags:

- `--debug` / `-d` — enables the graphics debug runtime and NVRHI validation layer.
- Pass a specific backend on the command line to select the graphics API (see `pyd.GetGraphicsAPIFromCommandLine`), e.g. `uv run main.py -api vk` (Vulkan) or `uv run main.py -api d3d12` (Windows only).

## Project layout

```text
main.py                 Example application (basic triangle)
src/cpp/_pydonut.cpp     pybind11 bindings for the native module
src/pydonut/             Python package (__init__.py, type stubs)
include/pydonut/         C++ headers for the bindings
shaders/                 HLSL shaders used by examples
extern/donut/            Donut framework (git submodule)
CMakeLists.txt           Native build configuration (invoked by scikit-build-core)
```

## Development

Rebuild the native module after C++ changes by re-running `uv sync` (it's cached based on `src/**/*.{h,c,hpp,cpp}` and `CMakeLists.txt`, see `pyproject.toml`).

Run tests with:

```sh
uv run pytest
```
