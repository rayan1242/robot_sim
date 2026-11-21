#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
"${SIM_VENV:-$HOME/robot_sim_perception_venv}/bin/python" sim/check_depth.py
