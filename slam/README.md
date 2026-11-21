# Phase 4: headless stella_vslam on WSL

This build uses the existing Ubuntu 24.04 WSL2 installation. Build artifacts and
locally installed SLAM libraries live in `~/robot_sim_slam/`; system packages are
installed through apt. No viewer, Docker, ROS, or CUDA is required.

From the Windows project directory:

```powershell
.\slam\prepare_sources.ps1
wsl -d Ubuntu -u root -- bash -lc 'apt-get update && apt-get install -y --no-install-recommends build-essential cmake ninja-build pkg-config libeigen3-dev libopencv-dev libyaml-cpp-dev libsqlite3-dev libsuitesparse-dev libspdlog-dev libfmt-dev libglew-dev curl ca-certificates'
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/slam/build_wsl.sh
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/slam/run_tum_wsl.sh
python -m eval.compare_slam
python -m eval.inspect_map
```

Paths above match this workspace; adjust the `/mnt/c/...` path on another machine.
The source and vocabulary versions are recorded in `source_versions.json`.
The build script copies source trees onto the Linux filesystem for faster compilation,
uses two compiler jobs to limit memory, and changes the local stella build copy to
C++17 for Ubuntu's modern dependencies. It does not modify the cached upstream checkout.
The build script can be rerun to resume compilation.

Our small C++ runner uses stella's public API and reads only `rgb.txt` and RGB images.
The upstream TUM example also loads a depth index to associate timestamps even in
monocular mode; this runner avoids that dependency and preserves original RGB times.
The Freiburg 1 calibration matches Phase 3. OpenCV input is BGR. Ground truth is
read only by the Python evaluator, never by SLAM.

Outputs in `data/slam_fr1_xyz/`:

- `frame_trajectory.txt`, `keyframe_trajectory.txt`: optimized TUM camera-to-world poses.
- `tracking.csv`: per-input-frame pose availability and tracking time.
- `map.msg`: stella's reusable map database.
- `landmarks.csv`: sparse landmark IDs, arbitrary-scale world positions, observations.
- `observations.csv`: keyframe ID/timestamp to landmark ID relationships for fusion.

`docs/phase4/` holds common-timestamp comparison JSON, Markdown, and a 3D plot.
The comparison aligns each system independently with Sim(3), uses shared ground-truth
associations, and reports pose coverage. An unavailable live pose can mean startup or
tracking failure; do not label the whole unavailable fraction as tracking loss.
Errors are positional and scale-aligned, not evidence of metric scale.

## Your own footage

The previous depth demo AVI contains a processed, side-by-side visualization at fixed
playback speed. It is not a raw SLAM input recording. Capture raw PNGs and monotonic
timestamps with:

```powershell
python record_camera.py --backend dshow --width 640 --height 480 --duration 30
```

This needs you to move the webcam slowly with textured surroundings and an initial
sideways motion for parallax. It saves raw frames and timestamps to `data/recordings/`.
Disk IO may skip frames; actual timing is retained. A valid calibration at matching
resolution/focus is still required before a meaningful own-camera SLAM run.
Do not reuse Freiburg calibration for your webcam.

Upstream references: [installation](https://stella-cv.readthedocs.io/en/latest/installation.html),
[examples](https://stella-cv.readthedocs.io/en/latest/example.html),
[source](https://github.com/stella-cv/stella_vslam).
