#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export GZ_PARTITION="${GZ_PARTITION:-robot_sim_lab}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
export QT_QPA_PLATFORM=xcb
gz sim -g
