#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SLAM_BUILD_ROOT:-$HOME/robot_sim_slam}"
export LD_LIBRARY_PATH="$build_root/install/lib:${LD_LIBRARY_PATH:-}"
export ROBOT_INITIALIZER_DIAGNOSTICS="${ROBOT_INITIALIZER_DIAGNOSTICS:-1}"
exec "$build_root/build/runner/run_live" "${3:-$repo_root/slam/webcam_640_mono.yaml}" "$repo_root/.cache/slam-source/orb_vocab.fbow" "$1" "${2:-$1}"
