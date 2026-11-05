cmake_minimum_required(VERSION 3.15...3.30)
project(clearhire_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(clearhire_native src/matcher.cpp)
if(NOT MSVC)
  target_compile_options(clearhire_native PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

install(TARGETS clearhire_native LIBRARY DESTINATION .)
