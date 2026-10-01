# Reference DRAM simulators for cross-checking hetero-sim's DRAM timing model
# (targets/hetero/dram_core.hpp). Separate from the main image on purpose: the
# simulation never needs them, they want a newer toolchain than Ubuntu 22.04
# has (DRAMSys: CMake >= 3.25; Ramulator2: C++20), and building them costs
# minutes nobody running the pipeline should pay.
#
#   docker build -t hetero-dram-xcheck tools/dram/xcheck
#   make dram-xcheck            (runs tools/dram/xcheck/run.py in it)
#
#   DRAMSys    LPDDR4 / LPDDR4X reference (open-source standalone, STL trace
#              player, per-transaction timing in its SQLite trace database)
#   Ramulator2 LPDDR5 reference (DRAMSys's LPDDR5 support is not open source)

FROM ubuntu:24.04

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates python3 python3-dev python3-venv \
        python3-yaml \
    && rm -rf /var/lib/apt/lists/*

# Commits are pinned in build_refs.sh, which is also what to run to build the
# references inside the hetero-sim image instead (see that script).
COPY build_refs.sh /tmp/build_refs.sh
RUN /tmp/build_refs.sh /opt
