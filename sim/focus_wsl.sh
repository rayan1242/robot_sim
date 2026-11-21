#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export GZ_PARTITION="${GZ_PARTITION:-robot_sim_lab}"
gz service -s /gui/move_to --reqtype gz.msgs.StringMsg --reptype gz.msgs.Boolean --timeout 5000 --req 'data: "mono_bot"'
