#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
python3 sim/robot_node.py --mode manual --output data/simulation/current
