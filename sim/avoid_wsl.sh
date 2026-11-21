#!/usr/bin/env bash
set -eo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
cd "$repo_root"
"${SIM_VENV:-$HOME/robot_sim_perception_venv}/bin/python" sim/robot_node.py --mode avoid --duration 20 --output data/simulation/avoid_trial
