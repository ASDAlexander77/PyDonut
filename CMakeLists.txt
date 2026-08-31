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

cmake_minimum_required(VERSION 4.2)

if ("${SKBUILD_PROJECT_NAME}" STREQUAL "")
    # to support custom compile in VS    
    message("Using SKBUILD_PROJECT_NAME as: ${SKBUILD_PROJECT_NAME}")
    set(SKBUILD_PROJECT_NAME "pydonut")
    message("Using pybind11 from: ${pybind11_DIR}")
    set(pybind11_DIR ".venv/Lib/site-packages/pybind11/share/cmake/pybind11")
endif()

project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

# ---------------------------------------
# Dependancy
# ---------------------------------------

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)

# _pydonut is a shared object (a Python extension module) that statically links donut's
# libraries (donut_core/engine/app, nvrhi, glfw, imgui, ...) built below via
# add_subdirectory(extern/donut). On Linux/macOS, static libraries linked into a shared
# object must be position-independent; set this before that add_subdirectory() so it
# applies to all of them. No-op on Windows.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if (MSVC)
	set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/bin")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
set(DONUT_SHADERS_OUTPUT_DIR "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/shaders/framework")

# ---------------------------------------
# Local patches to the vendored extern/donut submodule, applied here before
# add_subdirectory() below picks up donut's sources. Idempotent and non-fatal: a patch
# already applied is detected and skipped, and a patch that plain doesn't apply only warns
# rather than failing the whole configure, so a hand-edited or already-patched submodule
# tree doesn't break every subsequent cmake run.
#
# Explicit allowlist, NOT every file under patches/ -- some patches there (currently
# DeviceManager_VK-wsl-dzn-fixes.patch, for Mesa's dzn Vulkan-on-D3D12 driver under WSL) are
# kept for reference/manual `git -C extern/donut apply` use but deliberately not auto-applied.
set(PYDONUT_DONUT_PATCHES
    "${CMAKE_CURRENT_SOURCE_DIR}/patches/DeviceManager-skip-joystick-init-by-default.patch"
)

find_program(GIT_EXECUTABLE git)
if (GIT_EXECUTABLE)
    # Ensure extern/donut (and its own nested submodules, e.g. NVRHI/GLFW/ImGui) is actually
    # checked out before trying to patch or add_subdirectory() it -- a fresh clone without
    # --recurse-submodules leaves it an empty directory, which would otherwise fail later with
    # a much less obvious error. Safe/cheap to run on every configure: a no-op when already
    # up to date.
    execute_process(
        COMMAND "${GIT_EXECUTABLE}" submodule update --init --recursive
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        RESULT_VARIABLE PYDONUT_SUBMODULE_UPDATE_RESULT)
    if (NOT PYDONUT_SUBMODULE_UPDATE_RESULT EQUAL 0)
        message(FATAL_ERROR "pydonut: 'git submodule update --init --recursive' failed -- "
                             "cannot configure without extern/donut checked out.")
    endif()

    foreach(PATCH_FILE ${PYDONUT_DONUT_PATCHES})
        execute_process(
            COMMAND "${GIT_EXECUTABLE}" apply --check "${PATCH_FILE}"
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/extern/donut"
            RESULT_VARIABLE PYDONUT_PATCH_CHECK
            OUTPUT_QUIET ERROR_QUIET)
        if (PYDONUT_PATCH_CHECK EQUAL 0)
            message(STATUS "pydonut: applying patch to extern/donut: ${PATCH_FILE}")
            execute_process(
                COMMAND "${GIT_EXECUTABLE}" apply "${PATCH_FILE}"
                WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/extern/donut"
                RESULT_VARIABLE PYDONUT_PATCH_APPLY)
            if (NOT PYDONUT_PATCH_APPLY EQUAL 0)
                message(WARNING "pydonut: failed to apply patch: ${PATCH_FILE}")
            endif()
        else()
            # Not applicable as a forward patch -- check whether it's already applied (reverse
            # patch would apply cleanly) before warning.
            execute_process(
                COMMAND "${GIT_EXECUTABLE}" apply --check --reverse "${PATCH_FILE}"
                WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/extern/donut"
                RESULT_VARIABLE PYDONUT_PATCH_REVERSE_CHECK
                OUTPUT_QUIET ERROR_QUIET)
            if (PYDONUT_PATCH_REVERSE_CHECK EQUAL 0)
                message(STATUS "pydonut: patch already applied to extern/donut: ${PATCH_FILE}")
            else()
                message(WARNING "pydonut: patch does not apply cleanly to extern/donut (skipped): ${PATCH_FILE}")
            endif()
        endif()
    endforeach()
else()
    message(WARNING "pydonut: git not found -- skipping donut patch application")
endif()

# Opt-in NSight Aftermath GPU crash dumps. OFF by default: turning it on makes donut force
# NVRHI_WITH_AFTERMATH (extern/donut/CMakeLists.txt:101), which pulls in
# extern/donut/nvrhi/cmake/FetchAftermath.cmake -- a configure-time FetchContent download of
# the NSight Aftermath SDK from developer.nvidia.com. Must be set before add_subdirectory()
# below, or donut caches the OFF value.
option(PYDONUT_WITH_AFTERMATH "Enable NSight Aftermath GPU crash dumps (downloads the SDK at configure time)" OFF)
if (PYDONUT_WITH_AFTERMATH)
    set(DONUT_WITH_AFTERMATH ON CACHE BOOL "" FORCE)
endif()

add_subdirectory(extern/donut)

if (NVRHI_WITH_DX12)
    set(DONUT_D3D_AGILITY_SDK_URL "https://www.nuget.org/api/v2/package/Microsoft.Direct3D.D3D12/1.616.1")
    set(DONUT_D3D_AGILITY_SDK_FETCH_DIR "" CACHE STRING "" FORCE)
    include("${CMAKE_CURRENT_SOURCE_DIR}/extern/donut/cmake/FetchAgilitySDK.cmake")

    file(COPY
        "${DONUT_D3D_AGILITY_SDK_PATH}/build/native/bin/x64/D3D12Core.dll"
        "${DONUT_D3D_AGILITY_SDK_PATH}/build/native/bin/x64/D3D12SDKLayers.dll"
        DESTINATION "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}/D3D12/")
endif()

if (MSVC)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /W3 /MP")
endif()

# ---------------------------------------
# Pybind11
# ---------------------------------------

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(
	_pydonut MODULE 
	src/cpp/_pydonut.cpp
)

target_include_directories(_pydonut PRIVATE
    src/cpp
    include
)

target_link_libraries(_pydonut PRIVATE
    donut_core
    donut_render
    donut_app
    donut_engine
)

if (NVRHI_WITH_DX12)
    # Forwards the CMake option as a C++ preprocessor macro so _pydonut.cpp can guard its
    # D3D12 Work Graphs interop code the same way it already guards DXC via PYDONUT_HAVE_DXC.
    target_compile_definitions(_pydonut PRIVATE NVRHI_WITH_DX12=1)
    # d3dx12/d3dx12.h (CD3DX12_STATE_OBJECT_DESC, CD3DX12_WORK_GRAPH_SUBOBJECT, ...) ships in the
    # Agility SDK package fetched above by FetchAgilitySDK.cmake, not on any include path yet.
    target_include_directories(_pydonut PRIVATE "${DONUT_D3D_AGILITY_SDK_PATH}/build/native/include")
endif()

# ---------------------------------------
# DXC (in-process HLSL -> DXIL/SPIR-V compilation, for pyd.CompileShader)
# ---------------------------------------

# ShaderMake's own CMakeLists.txt (pulled in via add_subdirectory(extern/donut) above)
# fetches DXC and records its path in this CACHE INTERNAL variable, so it is visible
# here regardless of which subdirectory originally set it.
#
# The fetched package layout differs by platform (Windows zip: bin/<arch>/dxc.exe,
# inc/dxcapi.h, lib/<arch>/dxcompiler.lib; Linux tarball: bin/dxc,
# include/dxc/dxcapi.h (nested one level deeper than Windows -- verified against the
# actual fetched tarball), lib/libdxcompiler.so, lib/libdxil.so) -- so rather than
# hardcoding one layout, search a superset of candidate directories at both possible
# depths above the dxc executable and let find_path/find_library/find_file pick
# whichever actually exists.
if (SHADERMAKE_DXC_PATH AND EXISTS "${SHADERMAKE_DXC_PATH}")
    get_filename_component(DXC_BIN_DIR "${SHADERMAKE_DXC_PATH}" DIRECTORY)  # .../bin  or .../bin/<arch>
    get_filename_component(DXC_ROOT_1 "${DXC_BIN_DIR}" DIRECTORY)          # one level up
    get_filename_component(DXC_ROOT_2 "${DXC_ROOT_1}" DIRECTORY)          # two levels up

    find_path(DXC_INCLUDE_DIR NAMES dxcapi.h
        PATHS "${DXC_ROOT_1}/inc" "${DXC_ROOT_1}/include" "${DXC_ROOT_1}/include/dxc"
              "${DXC_ROOT_2}/inc" "${DXC_ROOT_2}/include" "${DXC_ROOT_2}/include/dxc"
        NO_DEFAULT_PATH)
    find_library(DXC_LIB NAMES dxcompiler
        PATHS "${DXC_ROOT_1}/lib" "${DXC_ROOT_1}/lib/x64" "${DXC_ROOT_1}/lib/arm64"
              "${DXC_ROOT_2}/lib" "${DXC_ROOT_2}/lib/x64" "${DXC_ROOT_2}/lib/arm64"
        NO_DEFAULT_PATH)
    find_file(DXC_COMPILER_RUNTIME NAMES dxcompiler.dll libdxcompiler.so
        PATHS "${DXC_BIN_DIR}" "${DXC_ROOT_1}/lib" "${DXC_ROOT_1}/lib/x64"
        NO_DEFAULT_PATH)
    find_file(DXC_SIGNER_RUNTIME NAMES dxil.dll libdxil.so
        PATHS "${DXC_BIN_DIR}" "${DXC_ROOT_1}/lib" "${DXC_ROOT_1}/lib/x64"
        NO_DEFAULT_PATH)
endif()

if (DXC_INCLUDE_DIR AND DXC_LIB AND DXC_COMPILER_RUNTIME)
    message(STATUS "pydonut: DXC found (${DXC_LIB}) -- enabling pyd.CompileShader")
    target_include_directories(_pydonut PRIVATE "${DXC_INCLUDE_DIR}")
    target_link_libraries(_pydonut PRIVATE "${DXC_LIB}")
    target_compile_definitions(_pydonut PRIVATE PYDONUT_HAVE_DXC=1)
    if (NOT WIN32)
        # rpath so the loader finds libdxcompiler.so next to _pydonut without LD_LIBRARY_PATH
        set_target_properties(_pydonut PROPERTIES BUILD_RPATH "$ORIGIN" INSTALL_RPATH "$ORIGIN")
    endif()

    set(DXC_RUNTIME_FILES "${DXC_COMPILER_RUNTIME}")
    if (DXC_SIGNER_RUNTIME)
        list(APPEND DXC_RUNTIME_FILES "${DXC_SIGNER_RUNTIME}")
    endif()

    add_custom_command(TARGET _pydonut POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different ${DXC_RUNTIME_FILES} "$<TARGET_FILE_DIR:_pydonut>"
        COMMENT "pydonut: copying DXC runtime library next to _pydonut")

    install(FILES ${DXC_RUNTIME_FILES} DESTINATION ${SKBUILD_PROJECT_NAME})
else()
    message(WARNING "pydonut: DXC not found -- pyd.CompileShader will not be available. "
                     "Set SHADERMAKE_DXC_PATH to a DXC install to enable it.")
endif()

# The Aftermath SDK's runtime library has to sit next to _pydonut, both in a dev build tree and
# in an installed wheel -- same two-step (POST_BUILD copy + install) the DXC runtime uses above.
#
# NOT via the `aftermath` imported target: donut's FetchAftermath.cmake declares it as
# `add_library(aftermath SHARED IMPORTED)` without GLOBAL (unlike the nvapi target just above it
# in nvrhi/CMakeLists.txt), so it is scoped to that directory and `TARGET aftermath` is false
# here. The find_file/find_library results it caches are global, so use those instead.
if (PYDONUT_WITH_AFTERMATH)
    if (WIN32)
        set(AFTERMATH_RUNTIME "${AFTERMATH_RUNTIME_LIBRARY}")  # the .dll, not the import .lib
    else()
        set(AFTERMATH_RUNTIME "${AFTERMATH_LIBRARY}")
    endif()

    if (AFTERMATH_RUNTIME AND EXISTS "${AFTERMATH_RUNTIME}")
        add_custom_command(TARGET _pydonut POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different "${AFTERMATH_RUNTIME}" "$<TARGET_FILE_DIR:_pydonut>"
            COMMENT "pydonut: copying Aftermath runtime library next to _pydonut")
        install(FILES "${AFTERMATH_RUNTIME}" DESTINATION ${SKBUILD_PROJECT_NAME})
        message(STATUS "pydonut: Aftermath enabled (${AFTERMATH_RUNTIME})")
    else()
        # Loud, not silent: without this library the built module fails to load at import time.
        message(FATAL_ERROR
            "pydonut: PYDONUT_WITH_AFTERMATH is ON but the Aftermath runtime library was not "
            "found. Expected AFTERMATH_RUNTIME_LIBRARY (Windows) or AFTERMATH_LIBRARY to be set "
            "by donut's FetchAftermath.cmake.")
    endif()
endif()

# The NGX feature DLLs are loaded at RUNTIME by name, from a directory the application hands
# to DLSS::Create -- they are not linked, so nothing pulls them in automatically. donut's
# samples get them next to their .exe; a Python extension has no .exe of its own (the process
# is python.exe, in the venv), so they go beside _pydonut instead and DLSS.Create is passed
# that directory. Without this, NGX starts but reports FeatureNotFound (0xbad00004).
#
# Both DLLs are shipped: nvngx_dlss.dll is DLSS proper, nvngx_dlssd.dll is Ray Reconstruction
# (the "d" is denoiser) -- DLSS::Create probes for both and logs each independently.
if (DONUT_WITH_DLSS AND WIN32)
    set(DLSS_RUNTIME_DIR "${DONUT_DLSS_FETCH_DIR}/lib/Windows_x86_64/rel")
    set(DLSS_RUNTIME_FILES
        "${DLSS_RUNTIME_DIR}/nvngx_dlss.dll"
        "${DLSS_RUNTIME_DIR}/nvngx_dlssd.dll")

    foreach(dll IN LISTS DLSS_RUNTIME_FILES)
        if (NOT EXISTS "${dll}")
            # Loud, not silent: a missing DLL here degrades to "DLSS mysteriously unavailable
            # at runtime", which is exactly the failure this block exists to prevent.
            message(FATAL_ERROR "pydonut: DONUT_WITH_DLSS is ON but ${dll} was not found.")
        endif()
    endforeach()

    add_custom_command(TARGET _pydonut POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different ${DLSS_RUNTIME_FILES} "$<TARGET_FILE_DIR:_pydonut>"
        COMMENT "pydonut: copying DLSS runtime libraries next to _pydonut")
    install(FILES ${DLSS_RUNTIME_FILES} DESTINATION ${SKBUILD_PROJECT_NAME})
    message(STATUS "pydonut: DLSS enabled (${DLSS_RUNTIME_DIR})")
endif()

install(TARGETS _pydonut DESTINATION ${SKBUILD_PROJECT_NAME})

# The C interop seam's public header ships inside the wheel so a companion extension module
# (PyRTXPT and friends) can compile against an *installed* pydonut with no source checkout:
# `pydonut.get_include()` returns this directory, and the header is included as
# <pydonut/pydonut_capi.h>. Keep the nested pydonut/ path -- get_include() returns the parent,
# so flattening it here would break that include spelling.
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/include/pydonut/pydonut_capi.h"
        DESTINATION "${SKBUILD_PROJECT_NAME}/include/pydonut")
