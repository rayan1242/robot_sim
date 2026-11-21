#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export GZ_PARTITION="${GZ_PARTITION:-robot_sim_lab}"
gz service -l | grep -E 'gui|camera|world/.*/(scene|state|control)'
gz service -i -s /gui/move_to
gz service -i -s /gui/follow
