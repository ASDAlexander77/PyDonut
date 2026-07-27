*Sync repo*

git submodule update --init --recursive

*Linux build dependencies*

On Debian/Ubuntu, `uv sync` builds GLFW (via the vendored `extern/donut` submodule) from source, which needs a few system packages not installed by default:

```
sudo apt-get install -y pkg-config libxkbcommon-dev libx11-dev libxrandr-dev \
    libxinerama-dev libxcursor-dev libxi-dev libgl1-mesa-dev libwayland-dev wayland-protocols
```

Then run:

```
uv sync
```

Optional: to enable `pyd.CompileShader` (in-process HLSL compilation), install DXC and point `SHADERMAKE_DXC_PATH` at it. Without this, `uv sync` still succeeds but prints a warning and `CompileShader` is unavailable.
