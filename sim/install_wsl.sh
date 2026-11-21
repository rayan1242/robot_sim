#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive
if [ "$(id -u)" -ne 0 ]; then echo 'Run the installer as root in WSL.' >&2; exit 1; fi
. /etc/os-release
if [ "$VERSION_ID" != '24.04' ]; then echo 'This installer targets Ubuntu 24.04 / ROS Jazzy.' >&2; exit 1; fi
apt-get update -qq
apt-get install -y --no-install-recommends curl ca-certificates python3
if ! dpkg-query -W ros2-apt-source >/dev/null 2>&1; then
  release=$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | python3 -c 'import sys,json; print(json.load(sys.stdin)["tag_name"])')
  package="/tmp/robot_sim_ros2_apt_source.deb"
  curl -fL "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${release}/ros2-apt-source_${release}.noble_all.deb" -o "$package"
  dpkg -i "$package"
fi
apt-get update -qq
apt-get install -y --no-install-recommends ros-jazzy-ros-base ros-jazzy-ros-gz \
  ros-jazzy-cv-bridge ros-jazzy-image-transport ros-jazzy-teleop-twist-keyboard \
  python3-opencv python3-numpy python3-colcon-common-extensions python3-venv
printf '\nInstalled ROS 2 Jazzy + matching Gazebo vendor packages.\n'
