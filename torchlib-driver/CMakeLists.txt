# Builds Torch as a static library (USE_STANDALONE=OFF) plus a small driver, so the
# library configuration Shipwright will link can be run through the same ROM matrix
# as the CLI build. See torch-migration/PHASE0.md in Shipwright, Gate A.
#
#   cmake -S torchlib-driver -B torchlib-driver/build -GNinja -DCMAKE_BUILD_TYPE=Debug
#   cmake --build torchlib-driver/build -j
#   TORCH_BIN=torchlib-driver/build/torchlib-driver tools/matrix.sh static-lib
#
# The BUILD_<game> flags and CMAKE_BUILD_TYPE are deliberately NOT set here — those
# are Gate B's and Gate C's variables and get passed on the command line, so this
# file changes exactly one thing versus the harness baseline.

cmake_minimum_required(VERSION 3.26)
project(torchlib-driver CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(USE_STANDALONE          OFF CACHE BOOL "" FORCE)  # static lib, no CLI, no libgfxd
set(PORT_VERSION_ENDIANNESS ON  CACHE BOOL "" FORCE)  # 7-byte portVersion, OTRExporter parity
set(ROM_CRC_BSWAP           OFF CACHE BOOL "" FORCE)
set(BUILD_UI                OFF CACHE BOOL "" FORCE)
set(BUILD_STORMLIB          OFF CACHE BOOL "" FORCE)

add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../torch ${CMAKE_BINARY_DIR}/torch)

add_executable(torchlib-driver main.cpp)

# torch exports src/, lib/ and the yaml-cpp includes as PUBLIC under
# USE_STANDALONE=OFF (torch/CMakeLists.txt), and spdlog becomes PUBLIC too.
target_link_libraries(torchlib-driver PRIVATE torch)
