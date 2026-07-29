# GPU-Accelerated Vulkan in WSL for PyDonut

By default, an Ubuntu WSL2 distro has **no GPU-accelerated Vulkan driver**. `vulkaninfo` only
lists `llvmpipe` — Mesa's CPU software rasterizer — even when `nvidia-smi` works and the WSL GPU
paravirtualization libraries (`/usr/lib/wsl/lib/libd3d12.so`, `libdxcore.so`) are present.
Running PyDonut samples in that state is both far too slow for real scenes and, in practice,
crashes: llvmpipe segfaults inside `vkCreateGraphicsPipelines` for the `bindless_rendering.py`
pipeline.

GPU access for Vulkan in WSL goes through **dzn ("Dozen")** — Mesa's Vulkan-on-Direct3D12
driver, which layers Vulkan over the D3D12 device that WSL exposes from the Windows host.
Ubuntu's `mesa-vulkan-drivers` package does **not** ship dzn, so it has to be built from
source. This document records the procedure that was verified on:

- Windows 11 Home 10.0.26200, WSL2, Ubuntu 24.04 (noble)
- NVIDIA GeForce RTX 5080 (any D3D12-capable GPU works the same way)
- Mesa 25.2.8 (matching the distro's Mesa version; see notes about Mesa `main` at the end)

> **Conformance warning:** dzn self-reports as *"not a conformant Vulkan implementation,
> testing use only"*. It is good enough to develop and smoke-test PyDonut samples inside WSL;
> it is not a production Vulkan stack. Native Windows runs (`uv sync` + D3D12/Vulkan on the
> host) remain the primary path.

## 1. Prerequisites

All commands below run **as root inside the WSL distro**. From Windows, `wsl -d Ubuntu -u root`
gives a root shell without a password.

Enable source repositories and install the Mesa build dependencies:

```sh
sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources
apt-get update
apt-get build-dep -y mesa
apt-get install -y directx-headers-dev python3-pip
```

Mesa 25.2 requires Meson >= 1.4, newer than Ubuntu 24.04's 1.3.2. Install a current Meson with
pip (it lands in `/usr/local/bin`, shadowing the distro binary):

```sh
pip3 install --break-system-packages 'meson>=1.4,<2'
```

## 2. Get and patch the Mesa source

Match the distro's Mesa version so the loader and driver come from the same series
(`apt-cache policy mesa-vulkan-drivers` shows the installed version):

```sh
cd /root
wget https://archive.mesa3d.org/mesa-25.2.8.tar.xz
tar xf mesa-25.2.8.tar.xz
cd mesa-25.2.8
```

**Version patch (required for Donut):** dzn implements the Vulkan 1.3 features Donut needs
(`dynamicRendering`, `synchronization2`) but hard-caps its *advertised* API version at 1.2 —
and Donut rejects any physical device below 1.3, silently falling back to llvmpipe. Bump the
advertised version:

```sh
sed -i 's/#define DZN_API_VERSION VK_MAKE_VERSION(1, 2, VK_HEADER_VERSION)/#define DZN_API_VERSION VK_MAKE_VERSION(1, 3, VK_HEADER_VERSION)/' \
    src/microsoft/vulkan/dzn_device.c
```

(Checked against Mesa `main` as of July 2026: still capped at 1.2 upstream, so this patch is
needed regardless of which Mesa version you build.)

## 3. Build only the dzn driver

No GL, no llvmpipe, no LLVM — this keeps the build to ~550 objects / a few minutes:

```sh
meson setup build-dzn \
    -Dbuildtype=release \
    -Dprefix=/usr/local \
    -Dvulkan-drivers=microsoft-experimental \
    -Dgallium-drivers= \
    -Dllvm=disabled \
    -Dglx=disabled \
    -Degl=disabled \
    -Dgbm=disabled \
    -Dplatforms=x11,wayland
ninja -C build-dzn
ninja -C build-dzn install
```

This installs:

- `/usr/local/lib/x86_64-linux-gnu/libvulkan_dzn.so` — the driver
- `/usr/local/share/vulkan/icd.d/dzn_icd.x86_64.json` — the ICD manifest

`/usr/local/share/vulkan/icd.d` is on the Vulkan loader's default search path, so no
environment variables are needed — the driver is picked up automatically alongside the distro's
llvmpipe.

## 4. Verify

```sh
vulkaninfo --summary
```

Expected: a new `GPU0` entry like

```text
deviceType   = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
deviceName   = Microsoft Direct3D12 (NVIDIA GeForce RTX 5080)
driverName   = Dozen
```

with llvmpipe demoted to `GPU1`. Donut prefers the discrete GPU, so PyDonut samples pick dzn
automatically — the log line to look for is:

```text
INFO: Created Vulkan device: Microsoft Direct3D12 (NVIDIA GeForce RTX 5080)
```

Smoke test from the repo root (`.venv-linux` is this repo's WSL virtualenv, built with
`UV_PROJECT_ENVIRONMENT=.venv-linux uv sync`):

```sh
.venv-linux/bin/python basic_triangle.py
```

## 5. Donut-side change that this depends on

dzn does not implement three of the Vulkan features Donut used to request unconditionally at
device creation (`tessellationShader`, `dualSrcBlend`, `maintenance4`), which made
`vkCreateDevice` fail with `VK_ERROR_FEATURE_NOT_PRESENT`. The vendored Donut submodule was
patched (in `src/app/vulkan/DeviceManager_VK.cpp`) to query the physical device first and
request those three features only when supported. Native Windows drivers support all three, so
the patch is behavior-neutral outside WSL/dzn.

Note this is a local patch to the `extern/donut` submodule — it must be committed to a Donut
fork (or re-applied) if the submodule is ever re-pinned.

## Known limitations

- **Bindless descriptor arrays crash dzn's shader compiler.** `bindless_rendering.py` (runtime
  descriptor arrays over `space1`/`space2`) segfaults inside dzn's SPIR-V→DXIL pass
  `dxil_spirv_nir_lower_bindless` during `vkCreateGraphicsPipelines` — verified on both Mesa
  25.2.8 and a Mesa `main` snapshot (July 2026), so building a newer Mesa does not help. This
  is a driver bug, not a PyDonut bug; non-bindless samples work. Run bindless samples natively
  on Windows until it is fixed upstream (worth reporting to Mesa's issue tracker).
- dzn is explicitly non-conformant ("testing use only"); expect other gaps for advanced
  features (mesh shaders, ray tracing).
- The version patch in step 2 makes dzn *claim* 1.3 while only guaranteeing the 1.3 features
  Donut actually checks; other 1.3-core features may be missing.

## Reverting

```sh
rm /usr/local/share/vulkan/icd.d/dzn_icd.x86_64.json \
   /usr/local/lib/x86_64-linux-gnu/libvulkan_dzn.so
```

Removing the ICD manifest alone is enough to make the loader ignore the driver.
