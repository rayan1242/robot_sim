# Monocular perception — capture, depth, SLAM, and fusion

Webcam capture, relative depth, checkerboard calibration, and educational visual
odometry. Python 3.11+.

Current milestone: live webcam depth, SLAM and a bounded cross-view-validated dense
window are integrated with the local dashboard. The final demonstration produced
dense output on 79/84 tracked outputs (94.0%); p95 receipt-to-packet age was 687 ms.
Mapping remains experimental and arbitrary-scale; complete room reconstruction,
independent dense accuracy and repeatability remain unvalidated.

See the [complete project engineering report](docs/project_report.md) for the
problems, actions, quantitative evidence, limitations and relevance to Efference.
Older phase reports describe their historical state, not the current feature set.

Dataset SLAM and offline depth fusion have now been run successfully. Results:
[depth benchmarks](docs/phase2_results.md), [mini VO](docs/phase3_results.md),
[established SLAM comparison](docs/phase4_results.md), and
[fusion experiment](docs/phase5_results.md). These do not complete webcam calibration,
own-room validation, or occupancy mapping.

Update: webcam calibration and an initial own-room SLAM/fusion trial are now available
in [room results](docs/room_slam/results.md). The first reconstruction is noisy and
incomplete; occupancy mapping and reliable room-scale validation remain pending.

The [session backend](backend/README.md) now provides recording, SQLite metadata,
download/delete, and process-based RGB/pose/map replay. See [Phase 6 validation](docs/phase6_results.md).

The [local dashboard](frontend/README.md) is served at the backend root URL. Restart
your backend and open `http://127.0.0.1:8001/` when using port 8001. It provides RGB,
3D snapshots/trajectory, recording/replay controls, and a session library.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python cam_live.py --backend dshow
```

Press **Q** or Escape to exit. Default camera settings are index 0, 640×480, 30 FPS.
Use `--camera 1` or `--backend dshow` if needed. All live commands accept
`--width`, `--height`, `--fps`, `--focus`, and `--exposure`. Exposure values are
driver-specific. The program attempts manual focus/exposure and prints driver
acceptance and readback; verify visually because driver reports are not proof of a lock.
Pick a sharp focus and usable exposure before calibration and reuse those settings.

## Capture checks

```powershell
python cam_live.py --backend dshow --duration 60
python cam_live.py --backend dshow --duration 30 --consumer-delay 0.2 --report data/slow_consumer.json
python cam_live.py --backend dshow --headless --duration 30
```

The slow consumer should skip frames without an increasing latency trend. Input age
is measured before processing; after-processing age includes the artificial delay.
Reports include input-age start/end medians to help distinguish variation from growth.
Reports also include p50/p95 age, capture FPS,
skips, failures, and negotiated settings. These timestamps mark completion of camera
reads, not sensor exposure: film a visible clock to investigate hidden buffering.
The single-slot buffer bounds retained frames; each consumer must release old packets.
`CameraCapture.get_latest(after_sequence=...)` waits for a newer immutable BGR frame.
Copy the image before drawing on it. Camera access and release belong to its worker.

## Calibration

Print an OpenCV-compatible checkerboard with **9×6 inner corners** (10×7 squares),
mount it flat on rigid backing, and measure a square edge. The examples use 25 mm;
replace `0.025` with your measurement in meters.

```powershell
python -m perception.calibrate collect --backend dshow --square-size 0.025
python -m perception.calibrate solve --square-size 0.025
python -m perception.calibrate compare --backend dshow
```

During collection, **S** saves a frame only when corners are detected; **Q** finishes.
Collect 25–40 sharp, varied views covering edges, corners, angles, and distances.
Use `--columns` and `--rows` for another board. Use a fresh `--images` folder for
each collection. Collection metadata records camera settings and board geometry.
The solver reads PNG images, rejects mixed resolutions, and requires at least 10 valid
views. Inspect per-image RMS errors in `data/calibration.json`; recollect poor views
rather than removing images just to lower the score.

Aim for overall reprojection RMS below approximately **0.5 pixels**. Inspect straight
edges in additional views using `compare`; **S** saves a raw/undistorted comparison.
The original intrinsics and distortion remain in `data/calibration.npz`; adjusted
intrinsics for the saved undistorted view are in `docs/calibration_comparison.npz`.
Any later algorithm using undistorted images must use those adjusted intrinsics.
Comparison rejects resolution mismatches. Focus, crop, zoom, and camera changes
require recalibration. Calibration quality and camera stability need physical checks.

## Verification

```powershell
python -m unittest discover -s tests -v
```

Tests use a fake camera to check latest-frame behavior and failure cleanup and synthetic
projected corner observations to exercise the calibration solver without a camera.

## Phase 2: live relative depth

```powershell
python -m pip install -r requirements-depth.txt
python depth_live.py --backend dshow --frames 0
```

The first run downloads Depth Anything V2 Small from Hugging Face. Use
`--local-files-only` afterward to require cached weights. Device selection is automatic;
`--device cpu` forces CPU and `--device cuda --precision fp16` uses an available CUDA
GPU. A CPU-only PyTorch installation cannot use CUDA. Press **Q** to exit, **S** to
save an RGB/depth comparison and raw float depth array, or **R** to toggle an AVI clip.
Saved examples are in `data/depth_examples/`. Clips use a fixed 10 FPS playback rate,
so use report throughput for performance measurements, not the playback speed.

Bright depth colors indicate nearer surfaces. Values are relative inverse depth,
not meters. Visualization uses per-frame percentiles; colors may fluctuate over time.
Capture continues independently while inference works on one frame.

### Benchmarks

Run each configuration on the same scene and lighting, plugged in with the same
power mode. Start with CPU fp32; repeat using CUDA fp32/fp16 if available.

```powershell
python depth_live.py --backend dshow --device cpu --width 640 --height 480 --headless --frames 100 --report data/depth_640_cpu.json
python depth_live.py --backend dshow --device cpu --width 480 --height 360 --headless --frames 100 --report data/depth_480_cpu.json
python depth_live.py --backend dshow --device cpu --width 320 --height 240 --headless --frames 100 --report data/depth_320_cpu.json
```

For controlled comparisons, hold camera capture at 640x480 and vary depth input:

```powershell
python depth_live.py --backend dshow --width 640 --height 480 --input-width 320 --input-height 240 --headless --frames 100 --report data/depth_fixed_320_cpu.json
python depth_live.py --backend dshow --width 640 --height 480 --input-width 480 --input-height 360 --headless --frames 100 --report data/depth_fixed_480_cpu.json
python depth_live.py --backend dshow --width 640 --height 480 --input-width 640 --input-height 480 --headless --frames 100 --report data/depth_fixed_640_cpu.json
```

Depth input dimensions default to `--width`/`--height` and are enforced independently
of camera negotiation using aspect-preserving resizing and black padding if needed.
The report records requested camera size, actual frame sizes, depth input size, resize
time, and network tensor shape. Saved depth arrays correspond to the resized/padded
image, not original camera pixels; later geometric processing must account for this.
Previous reports lack this enforcement and should not be mixed with the new results.
`total_ms` covers the depth wrapper; input resizing is reported separately and included
in throughput and capture-to-depth age.
Network dimensions are rounded to
multiples of 14 rather than silently using the processor's default size for every run.
Reports exclude three warmup inferences and include mean/p50/p95 preprocessing,
inference, postprocessing, and total latency, measured throughput, skipped frames,
and capture-to-depth p95. CUDA timings synchronize the GPU. CUDA reports also include
peak allocated tensor memory; this is not total device usage. Annotate power mode manually.

Save examples for mirrors, glass, dark rooms, blank walls, fast motion, and very close
objects. Describe what went wrong alongside each example. Phase 2 is fully validated
after a real live-depth clip, benchmark results, and this failure gallery are collected.

Model integration follows the [official Transformers documentation](https://huggingface.co/docs/transformers/model_doc/depth_anything_v2).

## Phase 3: educational monocular visual odometry

This uses the original TUM `freiburg1_xyz` RGB frames, not a webcam, and requires no
webcam calibration or camera backend argument.

```powershell
python -m pip install -r requirements-vo.txt
python download_tum.py
python vo_dataset.py
```

The downloader fetches approximately 0.5 GB from TUM, retaining the archive and
extracting only RGB images, timestamps, and ground truth. Depth and IMU data are not
used. Dataset source: [TUM RGB-D benchmark](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/download).
Calibration and trajectory convention follow [TUM's file-format documentation](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats).
The RGB-only pipeline uses the published Freiburg 1 RGB intrinsics and distortion
coefficients, undistorting feature coordinates before essential-matrix estimation.

ORB features -> Hamming matches with a 0.75 ratio test -> normalized coordinates ->
RANSAC essential matrix -> cheirality-checked relative pose -> camera-to-world trajectory.
Failed steps hold pose and use the current image as the next pairwise reference;
tracking losses are recorded rather than hidden.

Outputs in `data/vo_fr1_xyz/`:

- `trajectory.txt`: TUM camera-to-world poses (`timestamp tx ty tz qx qy qz qw`).
- `tracking.csv`: matches, inliers, state, and VO processing latency per frame.
- `trajectory.png`: estimate versus ground truth after similarity alignment.
- `report.json`: scale-aligned positional ATE RMSE and tracking statistics.

Ground truth is used only after estimation, with one-to-one timestamp matching within
20 ms and least-squares Sim(3) position alignment. All output poses, including held
poses on failed steps, participate when timestamps match. This built-in evaluator
reports position error only; it is not an orientation-error evaluator.

Important limitation: two-view translation has unknown magnitude on **every step**.
This baseline assigns a unit translation to each accepted step. A global scale alignment
cannot fix changing step sizes, drift, pure rotation, or planar-scene degeneracy.
The plotted trajectory is an educational baseline, not metric SLAM. Phase 4 will use
an established SLAM system for comparison. No depth-network predictions or ground
truth are used to manufacture translation scale.

Optional independent check (install `evo` separately):

```powershell
evo_ape tum data/rgbd_dataset_freiburg1_xyz/groundtruth.txt data/vo_fr1_xyz/trajectory.txt --align --correct_scale
```

For a quick smoke run use `python vo_dataset.py --max-frames 100 --output data/vo_smoke`.
Use the full sequence and identical stride when comparing with Phase 4.

## Phase 4: established SLAM

See [slam/README.md](slam/README.md) for the pinned headless stella_vslam build,
RGB-only TUM runner, sparse-map exports, and common-timestamp comparison. It uses
the existing Ubuntu 24.04 WSL2 distribution. Own-webcam SLAM remains pending a valid
webcam calibration and a raw recording; Freiburg intrinsics must not be reused.

## Phase 5 foundation: offline depth/SLAM fusion

After Phase 4 produces its sparse map and observations:

```powershell
python fuse_dataset.py --max-keyframes 20
```

This uses the cached depth model and Phase 4's optimized keyframe poses and observed
landmarks. It fits `1 / SLAM_z = scale * network_output + shift` with robust outlier
rejection. Twenty percent of correspondences are held out before fitting, and their
absolute relative depth errors are reported without filtering them as fit outliers.
Invalid held-out predictions are counted explicitly. Sparse SLAM agreement is not
independent depth ground truth.

Original distorted RGB pixels and Freiburg distortion coefficients are used consistently;
inference runs at 320x240 with intrinsics adjusted for OpenCV's resize convention.
Back-projection undistorts rays, transforms them by camera-to-world poses, and voxelizes
the accumulated colored points. Outputs are `data/fusion_fr1_xyz/dense_map.ply`,
`dense_map.npz`, and `report.json`. PLY opens in common point-cloud viewers.

This is a dataset fusion foundation, not completed Phase 5: output units remain arbitrary
SLAM units, and a floor-based occupancy grid requires a known or estimated ground
plane. The TUM tabletop sequence is not a webcam room reconstruction. Metric scale,
occupancy mapping, and own-room validation remain pending.

## Robot simulator

See [sim/README.md](sim/README.md) for the installed WSL2 ROS 2 / Gazebo simulator, WASD controls, and experimental camera-only local mapping.


## Live perception timing

Latest physical-camera milestone: [successful live-session report](docs/successful_live_session/report.md)
and [measured improvements / next mapping steps](docs/successful_live_session/next_steps.md).

See [live freshness results](docs/latency/results.md) for the measured webcam/depth path, queue experiment, resolution tradeoffs, and timing limitations.

