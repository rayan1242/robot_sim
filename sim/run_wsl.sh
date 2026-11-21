#!/usr/bin/env bash
set -eo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_PARTITION="${GZ_PARTITION:-robot_sim_lab}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
run_dir="$repo_root/data/simulation/current"
mkdir -p "$run_dir"
args=(-s -r --headless-rendering)
mode=manual
for option in "$@"; do
  case "$option" in
    --gui) args=(-r);;
    --avoid) mode=avoid;;
    *) echo "Unknown option: $option" >&2;exit 1;;
  esac
done
node_python=/usr/bin/python3
if [[ "$mode" == "avoid" ]]; then
  node_python="${SIM_VENV:-$HOME/robot_sim_perception_venv}/bin/python"
  if [[ ! -x "$node_python" ]]; then echo 'Install the simulation depth environment first.' >&2;exit 1;fi
fi
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "${controller_pid:-}" ]]; then kill -INT "$controller_pid" 2>/dev/null || true; fi
  if [[ -n "${bridge_pid:-}" ]]; then kill "$bridge_pid" 2>/dev/null || true; fi
  if [[ -n "${gazebo_pid:-}" ]]; then kill "$gazebo_pid" 2>/dev/null || true; fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
gz sim "${args[@]}" "$repo_root/sim/world.sdf" > "$run_dir/gazebo.log" 2>&1 &
gazebo_pid=$!
ros2 run ros_gz_bridge parameter_bridge --ros-args -p config_file:="$repo_root/sim/bridge.yaml" > "$run_dir/bridge.log" 2>&1 &
bridge_pid=$!
cd "$repo_root"
"$node_python" "$repo_root/sim/robot_node.py" --mode "$mode" --output "$run_dir" > "$run_dir/controller.log" 2>&1 &
controller_pid=$!
printf 'Gazebo PID=%s | bridge PID=%s | ROS_DOMAIN_ID=%s\nLogs: %s\n' "$gazebo_pid" "$bridge_pid" "$ROS_DOMAIN_ID" "$run_dir"
wait "$gazebo_pid"
