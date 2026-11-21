#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SLAM_BUILD_ROOT:-$HOME/robot_sim_slam}"
cmake -S "$repo_root/slam" -B "$build_root/build/runner" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$build_root/install"
cmake --build "$build_root/build/runner" --target run_live --parallel 2
