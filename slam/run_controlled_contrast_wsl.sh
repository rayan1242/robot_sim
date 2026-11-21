#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SLAM_BUILD_ROOT:-$HOME/robot_sim_slam}"
export LD_LIBRARY_PATH="$build_root/install/lib:${LD_LIBRARY_PATH:-}"
output="$repo_root/data/slam_webcam_1793510528100184300_contrast"
mkdir -p "$output"
"$build_root/build/runner/run_mono_dataset" "$repo_root/slam/webcam_640_mono.yaml" \
 "$repo_root/.cache/slam-source/orb_vocab.fbow" \
 "$repo_root/data/experiments/contrast_1793510528100184300" "$output" 2>&1 | tee "$output/run.log"
