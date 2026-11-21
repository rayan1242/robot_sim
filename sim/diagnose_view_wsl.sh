#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export GZ_PARTITION="${GZ_PARTITION:-robot_sim_lab}"
gz service -i -s /gui/screenshot
gz topic -l | grep -E 'pose|scene'
gz service -s /gui/screenshot --reqtype gz.msgs.StringMsg --reptype gz.msgs.Boolean --timeout 5000 --req 'data: "/mnt/c/Users/Rayyan/developer/robot_sim/data/simulation/viewer.png"'
timeout 5 gz topic -e -n 1 -t /world/mono_lab/dynamic_pose/info > /mnt/c/Users/Rayyan/developer/robot_sim/data/simulation/poses.txt || true
