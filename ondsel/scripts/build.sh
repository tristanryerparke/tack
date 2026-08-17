#!/usr/bin/env bash
# Build OndselSolver (static) and the pybind11 `ondselsolver` module against
# Rhino 8's CPython 3.9 runtime, producing a universal .so in rhino_modules/.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
RHINO_PY="$HOME/.rhinocode/py39-rh8/python3.9"

if [ ! -d "$HERE/OndselSolver" ]; then
    git clone --depth 1 https://github.com/Ondsel-Development/OndselSolver.git "$HERE/OndselSolver"
    # Upstream force-sets ONDSELSOLVER_BUILD_SHARED=ON on UNIX; we want static.
    sed -i '' 's/set( ONDSELSOLVER_BUILD_SHARED ON )/set( ONDSELSOLVER_BUILD_SHARED OFF )/g' \
        "$HERE/OndselSolver/CMakeLists.txt"
fi

if [ ! -d "$HERE/third_party/pybind11" ]; then
    git clone --depth 1 --branch v2.13.6 \
        https://github.com/pybind/pybind11.git "$HERE/third_party/pybind11"
fi

echo "==> Building OndselSolver (static, universal)"
cmake -S "$HERE/OndselSolver" -B "$HERE/build/ondselsolver" \
    -DCMAKE_BUILD_TYPE=Release \
    -DONDSELSOLVER_BUILD_SHARED=OFF \
    -DONDSELSOLVER_BUILD_TESTS=OFF \
    -DONDSELSOLVER_BUILD_EXE=OFF \
    -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" \
    -DCMAKE_INSTALL_PREFIX="$HERE/build/install"
cmake --build "$HERE/build/ondselsolver" --target install --parallel "$(sysctl -n hw.ncpu)"

echo "==> Building ondselsolver python module (universal, Rhino CPython 3.9)"
cmake -S "$HERE/wrapper" -B "$HERE/build/wrapper" \
    -DCMAKE_BUILD_TYPE=Release \
    -DPython_EXECUTABLE="$RHINO_PY" \
    -DONDSELSOLVER_INSTALL="$HERE/build/install"
cmake --build "$HERE/build/wrapper" --parallel "$(sysctl -n hw.ncpu)"

mkdir -p "$HERE/rhino_modules"
cp "$HERE/build/wrapper/ondselsolver.cpython-39-darwin.so" "$HERE/rhino_modules/"

echo "==> Done:"
ls -la "$HERE/rhino_modules/"
