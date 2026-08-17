cmake_minimum_required(VERSION 3.16)

project(ondselsolver_wrapper LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../third_party/pybind11 pybind11_build EXCLUDE_FROM_ALL)

find_package(Python 3.9 EXACT REQUIRED COMPONENTS Interpreter Development.Module)

set(MODULE_NAME "ondsel_v1" CACHE STRING "Python module name (bump per build to dodge import caches)")

pybind11_add_module(${MODULE_NAME} ondselsolver_wrapper.cpp)
target_compile_definitions(${MODULE_NAME} PRIVATE MOD_NAME=${MODULE_NAME})

target_include_directories(${MODULE_NAME} PRIVATE
    ${ONDSELSOLVER_INSTALL}/include/OndselSolver
)

target_link_libraries(${MODULE_NAME} PRIVATE
    ${ONDSELSOLVER_INSTALL}/lib/libOndselSolver.a
)

# Universal binary so the module loads in either arm64 or x86_64 Rhino.
set_target_properties(${MODULE_NAME} PROPERTIES
    OSX_ARCHITECTURES "arm64;x86_64"
)
