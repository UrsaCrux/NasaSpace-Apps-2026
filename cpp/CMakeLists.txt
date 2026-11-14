cmake_minimum_required(VERSION 3.14)
project(fieldshift_core VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

# Every .cpp in src/ is compiled into one shared library that Python loads.
file(GLOB FS_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp)

add_library(fieldshift_core SHARED ${FS_SOURCES})
target_include_directories(fieldshift_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
if(MSVC)
  target_compile_definitions(fieldshift_core PRIVATE _USE_MATH_DEFINES)
endif()
# Put the library directly in build/ (also for multi-config generators).
set_target_properties(fieldshift_core PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
  RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
