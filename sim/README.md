# Local robot simulator (WSL2)

Installed in the existing Ubuntu 24.04 WSL distribution: ROS 2 Jazzy and
Gazebo Harmonic (8.15.0). This matches Ubuntu 24.04; the guide's Humble setup
targets Ubuntu 22.04. See the [official compatibility guide](https://gazebosim.org/docs/harmonic/ros_installation/).

The world contains a differential-drive robot, an RGB camera, walls and three
obstacles. Manual driving is the default. It does not require the webcam or
change the dashboard server on port 8001.

## Start

From PowerShell in the project directory, start one simulator:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/sim/run_wsl.sh --gui
```

In a second PowerShell terminal:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/sim/teleop_wsl.sh
```

Keep the second terminal focused. Hold W/S to move, A/D to turn, Space to stop,
Q to leave keyboard control. Commands expire after release. Ctrl+C in the
simulator terminal shuts down its controller, bridge and Gazebo. Do not launch
multiple instances or controllers together.

For a headless server, omit `--gui`; open its viewer separately with:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/sim/view_wsl.sh
```

Logs and the latest RGB image are in `data/simulation/current/`. The simulation
uses ROS domain 42 and Gazebo partition `robot_sim_lab` by default.

## Verify

With the simulator running in manual mode, this test moves the robot forward
briefly and then stops it:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/sim/check_wsl.sh
```

It checks RGB delivery and motion using odometry; odometry is not an input to
the camera-only controller. The initial run received 47 camera frames at
320x240 and measured 0.317 m displacement. Artifacts: `data/simulation/smoke/`.

## Experimental depth and local occupancy

The optional Linux depth environment is installed at
`~/robot_sim_perception_venv`, isolated from Windows and system Python. It uses
the existing workspace model cache. To check one saved camera frame:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/sim/check_depth_wsl.sh
```

The local map uses known simulation camera height, pitch and a flat gray floor
to establish metric scale. It is not general room reconstruction or SLAM.
It publishes `/local_occupancy`, `/mono/status` and `/cmd_vel`. Unknown space,
failed alignment or results older than one second produce a stop command.

To experiment with avoidance, stop the manual simulator first and launch
`run_wsl.sh --gui --avoid`. Do not run a second controller alongside it.
Avoidance and the saved-frame check default to CUDA. If CUDA initialization
fails, avoidance stays stopped and logs the failure. Set `SIM_DEPTH_DEVICE=cpu`
in WSL to run the CPU baseline. In the original CPU trial, depth processing
exceeded the one-second freshness limit, so the robot stayed stopped.
Automatic obstacle avoidance has **not**
passed an end-to-end navigation test. Keep manual mode as the working default.

## Installation scripts

For reproducing the setup on Ubuntu 24.04:

```powershell
wsl -d Ubuntu -u root -- bash /mnt/c/Users/Rayyan/developer/robot_sim/sim/install_wsl.sh
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/sim/install_depth_wsl.sh
```

The depth installer defaults to PyTorch CUDA 11.8 wheels and verifies that
PyTorch can allocate a CUDA tensor. CUDA in WSL requires a compatible NVIDIA
driver installed on Windows. To install the CPU-only wheels, pass
`env SIM_DEPTH_DEVICE=cpu` before `bash` in the depth installer command.
