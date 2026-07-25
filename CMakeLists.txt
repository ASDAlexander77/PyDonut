cmake_minimum_required(VERSION 4.2)
project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_core MODULE src/main.cpp)
install(TARGETS _core DESTINATION ${SKBUILD_PROJECT_NAME})
