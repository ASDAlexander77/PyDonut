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

### WSL

A stock WSL2 Ubuntu distro has no GPU-accelerated Vulkan driver, so it silently falls back to
Mesa's CPU software rasterizer (`llvmpipe`) — samples run far too slowly, and
`bindless_rendering.py` specifically segfaults on it. See
[`docs/WSL_GPU_SETUP.md`](docs/WSL_GPU_SETUP.md) for building and installing Mesa's `dzn`
(Vulkan-on-D3D12) driver, which routes Vulkan through the host GPU instead.

That setup depends on a small fix to the vendored Donut submodule: `dzn` doesn't implement
`tessellationShader`, `dualSrcBlend`, or `maintenance4`, which Donut's Vulkan device manager
requests unconditionally, so device creation fails with `VK_ERROR_FEATURE_NOT_PRESENT` without
it. Apply it after checking out submodules:

```sh
git -C extern/donut apply ../../patches/DeviceManager_VK-wsl-dzn-fixes.patch
```

The patch is a no-op on native drivers (Windows, or Linux with a real Vulkan ICD) — those
already support all three features — so it's safe to apply on every platform, not just WSL.

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
- Pass a backend flag to select the graphics API (parsed by `pyd.GetGraphicsAPIFromCommandLine`): `-vk` / `-vulkan` for Vulkan, or `-d3d12` / `-dx12` for D3D12 (Windows only). E.g. `uv run main.py -vk` or `uv run main.py -d3d12`. With no flag, it defaults to D3D12 on Windows and Vulkan on Linux.

| Windows (D3D12) | Linux (Vulkan) |
| --- | --- |
| ![Basic triangle example on Windows](img/win_basic_triangle.png) | ![Basic triangle example on Linux](img/linux_basic_triangle.png) |

### Example: `main.py`

```python
if __name__ == "__main__":
    import sys
    from pathlib import Path
    from typing import Optional
    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Basic Triangle"
    folder = Path(__file__).resolve().parent

    class BasicTriangle(pyd.IRenderPass):
        def __init__(self: BasicTriangle, deviceManager: pyd.DeviceManager) -> None:
            super().__init__(deviceManager)
            self.vertexShader: Optional[pyd.Shader] = None
            self.pixelShader: Optional[pyd.Shader] = None
            self.pipeline: Optional[pyd.GraphicsPipeline] = None
            self.commandList: Optional[pyd.CommandList] = None

        def Init(self: BasicTriangle) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "basic_triangle" / "shaders.hlsl"
            source = shaderPath.read_text(encoding="utf-8")

            try:
                assert pyd.CompileShader is not None
                vsBytecode = pyd.CompileShader(source, "main_vs", pyd.ShaderType.Vertex, api, sourceName=shaderPath.name)
                psBytecode = pyd.CompileShader(source, "main_ps", pyd.ShaderType.Pixel, api, sourceName=shaderPath.name)
            except RuntimeError as e:
                print(f"Shader compilation failed: {e}", file=sys.stderr)
                return False

            self.vertexShader = device.createShader(vsBytecode, "main_vs", pyd.ShaderType.Vertex)
            self.pixelShader = device.createShader(psBytecode, "main_ps", pyd.ShaderType.Pixel)

            if not self.vertexShader or not self.pixelShader:
                return False

            self.commandList = device.createCommandList()

            return True

        def BackBufferResizing(self: BasicTriangle):
            self.pipeline = None

        def Animate(self: BasicTriangle, elapsedTimeSeconds: float):
            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def Render(self: BasicTriangle, framebuffer: pyd.Framebuffer):
            device = self.GetDevice()
            assert self.commandList is not None

            if not self.pipeline:
                psoDesc = pyd.GraphicsPipelineDesc()
                psoDesc.VS = self.vertexShader
                psoDesc.PS = self.pixelShader
                psoDesc.primType = pyd.PrimitiveType.TriangleList
                psoDesc.renderState.depthStencilState.depthTestEnable = False

                self.pipeline = device.createGraphicsPipeline(psoDesc, framebuffer.getFramebufferInfo())

            self.commandList.open()

            pyd.ClearColorAttachment(self.commandList, framebuffer, 0, pyd.Color(0.0))

            state = pyd.GraphicsState()
            state.pipeline = self.pipeline
            state.framebuffer = framebuffer
            state.viewport.addViewportAndScissorRect(framebuffer.getFramebufferInfo().getViewport())

            self.commandList.setGraphicsState(state)

            args = pyd.DrawArguments()
            args.vertexCount = 3
            self.commandList.draw(args)

            self.commandList.close()
            device.executeCommandList(self.commandList)

    is_debug = "--debug" in sys.argv or "-d" in sys.argv

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        print("Failed to create DeviceManager.", file=sys.stderr)
        exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, "PyDonut Window"):
        print("Cannot initialize a graphics device with the requested parameters", file=sys.stderr)
        exit(1)

    example = BasicTriangle(deviceManager)
    if example.Init():
        deviceManager.AddRenderPassToBack(example)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    del deviceManager
```

## Project layout

```text
main.py                 Example application (basic triangle)
src/cpp/_pydonut.cpp     pybind11 bindings for the native module
src/pydonut/             Python package (__init__.py, type stubs)
include/pydonut/         C++ headers for the bindings
shaders/                 HLSL shaders used by examples
extern/donut/            Donut framework (git submodule)
patches/                 Optional patches for the vendored extern/donut submodule (see WSL setup above)
CMakeLists.txt           Native build configuration (invoked by scikit-build-core)
```

## Development

Rebuild the native module after C++ changes by re-running `uv sync` (it's cached based on
`src/**/*.{h,c,hpp,cpp}`, `CMakeLists.txt`, and `extern/donut`'s sources/headers/CMake files —
see `[tool.uv].cache-keys` in `pyproject.toml`).

Run tests with:

```sh
uv run pytest
```
