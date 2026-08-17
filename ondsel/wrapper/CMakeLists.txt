cmake_minimum_required(VERSION 3.16)

project(ondselsolver_wrapper LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../third_party/pybind11 pybind11_build EXCLUDE_FROM_ALL)

find_package(Python 3.9 EXACT REQUIRED COMPONENTS Interpreter Development.Module)

pybind11_add_module(ondselsolver ondselsolver_wrapper.cpp)

target_include_directories(ondselsolver PRIVATE
    ${ONDSELSOLVER_INSTALL}/include/OndselSolver
)

target_link_libraries(ondselsolver PRIVATE
    ${ONDSELSOLVER_INSTALL}/lib/libOndselSolver.a
)

# Universal binary so the module loads in either arm64 or x86_64 Rhino.
set_target_properties(ondselsolver PROPERTIES
    OSX_ARCHITECTURES "arm64;x86_64"
)
