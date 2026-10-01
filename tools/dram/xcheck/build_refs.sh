#!/usr/bin/env bash
#
# Build the reference simulators tools/dram/xcheck/run.py compares against,
# at pinned commits, into PREFIX (default /opt):
#
#   PREFIX/DRAMSys      LPDDR4 / LPDDR4X reference (standalone, STL trace player)
#   PREFIX/ramulator2   LPDDR5 reference (library + Python config exporter)
#
# Used by the Dockerfile next to this script, and runnable as is in the
# hetero-sim image (Ubuntu 22.04: its CMake is too old for DRAMSys, so a newer
# one is installed into PREFIX/xvenv with uv or pip). Needs git, a C++20
# compiler, network access, and about 300 MB.
#
#   tools/dram/xcheck/build_refs.sh [PREFIX]
#
set -euo pipefail

PREFIX=${1:-/opt}
DRAMSYS_COMMIT=f5a6c60fdd09e53c02ca49591ab0e28a17a1cc0e
RAMULATOR2_COMMIT=72427a1bba3771564c4fb0e494ba02242fd1eaa7
PYTHON=${PYTHON:-$(command -v python3)}
JOBS=${JOBS:-$(nproc)}

mkdir -p "$PREFIX"
cd "$PREFIX"

# DRAMSys wants CMake >= 3.25.
cmake_ok() {
  command -v cmake >/dev/null || return 1
  local v; v=$(cmake --version | head -1 | awk '{print $3}')
  [ "$(printf '%s\n3.25\n' "$v" | sort -V | head -1)" = "3.25" ]
}
if ! cmake_ok; then
  echo "CMake too old or missing; installing a newer one into $PREFIX/xvenv"
  if command -v uv >/dev/null; then
    uv venv -q "$PREFIX/xvenv" && VIRTUAL_ENV="$PREFIX/xvenv" uv pip install -q cmake
  else
    "$PYTHON" -m venv "$PREFIX/xvenv" && "$PREFIX/xvenv/bin/pip" install -q cmake
  fi
  export PATH="$PREFIX/xvenv/bin:$PATH"
fi

clone() {  # url dir commit
  [ -d "$2" ] || git clone -q "$1" "$2"
  git -C "$2" checkout -q --detach "$3"
}

clone https://github.com/tukl-msd/DRAMSys.git DRAMSys "$DRAMSYS_COMMIT"
# CMAKE_POLICY_VERSION_MINIMUM: some of its fetched dependencies declare a
# minimum CMake 4 no longer accepts.
cmake -S DRAMSys -B DRAMSys/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build DRAMSys/build --parallel "$JOBS"

clone https://github.com/CMU-SAFARI/ramulator2.git ramulator2 "$RAMULATOR2_COMMIT"
cmake -S ramulator2 -B ramulator2/build -DCMAKE_BUILD_TYPE=Release -DPython_EXECUTABLE="$PYTHON"
cmake --build ramulator2/build --parallel "$JOBS"

# The sources are not needed to run; keep only what run.py uses.
rm -rf DRAMSys/build/_deps/*-subbuild DRAMSys/.git ramulator2/.git
echo "references built in $PREFIX"
