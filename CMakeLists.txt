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
    donut_app
    donut_engine
    donut_render)

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

install(TARGETS _pydonut DESTINATION ${SKBUILD_PROJECT_NAME})
