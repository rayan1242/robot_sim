#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SLAM_BUILD_ROOT:-$HOME/robot_sim_slam}"
python3 "$repo_root/slam/instrument_initializer.py" "$build_root/src/stella_vslam"
cmake --build "$build_root/build/stella" --parallel 2
cmake --install "$build_root/build/stella"
