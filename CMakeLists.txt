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
	_core MODULE 
	src/cpp/_core.cpp
)

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
    donut_engine)

# ---------------------------------------
# DXC (in-process HLSL -> DXIL/SPIR-V compilation, for pyd.CompileShader)
# ---------------------------------------

# ShaderMake's own CMakeLists.txt (pulled in via add_subdirectory(extern/donut) above)
# fetches DXC and records its path in this CACHE INTERNAL variable, so it is visible
# here regardless of which subdirectory originally set it.
if (SHADERMAKE_DXC_PATH AND EXISTS "${SHADERMAKE_DXC_PATH}")
    get_filename_component(DXC_BIN_DIR "${SHADERMAKE_DXC_PATH}" DIRECTORY)   # .../bin/<arch>
    get_filename_component(DXC_ARCH "${DXC_BIN_DIR}" NAME)                  # <arch>
    get_filename_component(DXC_BIN "${DXC_BIN_DIR}" DIRECTORY)              # .../bin
    get_filename_component(DXC_ROOT "${DXC_BIN}" DIRECTORY)                 # DXC package root

    set(DXC_INCLUDE_DIR "${DXC_ROOT}/inc")
    set(DXC_LIB "${DXC_ROOT}/lib/${DXC_ARCH}/dxcompiler.lib")
    set(DXC_COMPILER_DLL "${DXC_BIN_DIR}/dxcompiler.dll")
    set(DXC_SIGNER_DLL "${DXC_BIN_DIR}/dxil.dll")
endif()

if (DXC_INCLUDE_DIR AND EXISTS "${DXC_INCLUDE_DIR}/dxcapi.h" AND EXISTS "${DXC_LIB}" AND EXISTS "${DXC_COMPILER_DLL}")
    message(STATUS "pydonut: DXC found at '${DXC_ROOT}' -- enabling pyd.CompileShader")
    target_include_directories(_pydonut PRIVATE "${DXC_INCLUDE_DIR}")
    target_link_libraries(_pydonut PRIVATE "${DXC_LIB}")
    target_compile_definitions(_pydonut PRIVATE PYDONUT_HAVE_DXC=1)

    set(DXC_RUNTIME_DLLS "${DXC_COMPILER_DLL}")
    if (EXISTS "${DXC_SIGNER_DLL}")
        list(APPEND DXC_RUNTIME_DLLS "${DXC_SIGNER_DLL}")
    endif()

    add_custom_command(TARGET _pydonut POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different ${DXC_RUNTIME_DLLS} "$<TARGET_FILE_DIR:_pydonut>"
        COMMENT "pydonut: copying DXC runtime DLLs next to _pydonut")

    install(FILES ${DXC_RUNTIME_DLLS} DESTINATION ${SKBUILD_PROJECT_NAME})
else()
    message(WARNING "pydonut: DXC not found -- pyd.CompileShader will not be available. "
                     "Set SHADERMAKE_DXC_PATH to a DXC install to enable it.")
endif()

install(TARGETS _core DESTINATION ${SKBUILD_PROJECT_NAME})
install(TARGETS _pydonut DESTINATION ${SKBUILD_PROJECT_NAME})
