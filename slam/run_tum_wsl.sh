#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SLAM_BUILD_ROOT:-$HOME/robot_sim_slam}"
export LD_LIBRARY_PATH="$build_root/install/lib:${LD_LIBRARY_PATH:-}"
mkdir -p "$repo_root/data/slam_fr1_xyz"
"$build_root/build/runner/run_mono_dataset" \
  "$repo_root/slam/tum_fr1_mono.yaml" \
  "$repo_root/.cache/slam-source/orb_vocab.fbow" \
  "$repo_root/data/rgbd_dataset_freiburg1_xyz" \
  "$repo_root/data/slam_fr1_xyz"
