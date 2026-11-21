#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SLAM_BUILD_ROOT:-$HOME/robot_sim_slam}"
recording="${1:-1793497050756818200}"
profile="${2:-baseline}"
if [[ "$profile" != "baseline" && "$profile" != "strict" ]]; then
  printf 'Profile must be baseline or strict\n' >&2
  exit 1
fi
if [[ ! "$recording" =~ ^[0-9]+$ ]]; then
  printf 'Recording ID must be numeric\n' >&2
  exit 1
fi
export LD_LIBRARY_PATH="$build_root/install/lib:${LD_LIBRARY_PATH:-}"
output="$repo_root/data/slam_webcam_$recording"
config="$repo_root/slam/webcam_640_mono.yaml"
if [[ "$profile" == "strict" ]]; then
  output="${output}_strict"
  config="$repo_root/slam/webcam_640_mono_strict.yaml"
fi
mkdir -p "$output"
"$build_root/build/runner/run_mono_dataset" \
  "$config" \
  "$repo_root/.cache/slam-source/orb_vocab.fbow" \
  "$repo_root/data/recordings/$recording" \
  "$output" 2>&1 | tee "$output/run.log"
