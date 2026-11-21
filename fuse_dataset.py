"""Fuse relative depth with exported monocular SLAM keyframes and sparse landmarks."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from perception.depth import DepthEstimator
from perception.vo import FR1_MATRIX, FR1_DISTORTION
from perception.fusion import (fit_inverse_depth, project_landmarks, sample_bilinear,
                               backproject, voxel_downsample, alignment_support, multiview_support)


def load_camera(calibration, dataset):
    if calibration is None:
        if dataset.name != "rgbd_dataset_freiburg1_xyz":
            raise ValueError("Non-TUM input requires --calibration; Freiburg intrinsics cannot be used for webcam footage")
        return FR1_MATRIX.copy(), FR1_DISTORTION.copy(), (640, 480)
    with np.load(calibration, allow_pickle=False) as data:
        matrix = data["camera_matrix"].astype(float)
        distortion = data["distortion_coefficients"].astype(float)
        size = tuple(int(value) for value in data["image_size"])
    if (matrix.shape != (3, 3) or len(size) != 2 or min(size) <= 0 or
            not np.isfinite(matrix).all() or not np.isfinite(distortion).all() or
            matrix[0, 0] <= 0 or matrix[1, 1] <= 0):
        raise ValueError("Invalid camera calibration")
    return matrix, distortion, size


def resize_intrinsics(matrix, source_size, target_size):
    """OpenCV resize's half-pixel convention, preserving the original calibration."""
    resized = matrix.copy()
    for axis in range(2):
        scale = target_size[axis]/source_size[axis]
        resized[axis] *= scale
        resized[axis, 2] += (scale-1)/2
    return resized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/rgbd_dataset_freiburg1_xyz"))
    parser.add_argument("--slam", type=Path, default=Path("data/slam_fr1_xyz"))
    parser.add_argument("--output", type=Path, default=Path("data/fusion_fr1_xyz"))
    parser.add_argument("--calibration", type=Path, help="Camera .npz; required for webcam recordings")
    parser.add_argument("--max-keyframes", type=int, default=20)
    parser.add_argument("--voxel-size", type=float, default=0.02, help="Arbitrary SLAM units, not meters")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--quality-checks", action="store_true", help="Training-only rejection and conservative pixel support")
    parser.add_argument("--multiview-checks", action="store_true", help="Also require another view's supported depth agreement; implies quality checks")
    parser.add_argument("--start-time",type=float,help="First source timestamp to fuse (inclusive)")
    parser.add_argument("--end-time",type=float,help="Last source timestamp to fuse (inclusive)")
    args = parser.parse_args()
    args.quality_checks = args.quality_checks or args.multiview_checks
    if args.max_keyframes < 1 or args.voxel_size <= 0:
        parser.error("Positive keyframe count and voxel size required")
    if any(value is not None and not np.isfinite(value) for value in [args.start_time,args.end_time]):
        parser.error("Time limits must be finite")
    if args.start_time is not None and args.end_time is not None and args.end_time<=args.start_time:
        parser.error("end-time must exceed start-time")
    landmarks = np.genfromtxt(args.slam / "landmarks.csv", delimiter=",", names=True, ndmin=1)
    observations = np.genfromtxt(args.slam / "observations.csv", delimiter=",", names=True, ndmin=1)
    poses = np.loadtxt(args.slam / "keyframe_trajectory.txt", ndmin=2)
    poses = poses[np.argsort(poses[:, 0])]
    if len(poses) > args.max_keyframes:
        poses = poses[np.linspace(0, len(poses)-1, args.max_keyframes, dtype=int)]
    point_lookup = {int(p["id"]): np.array([p["x"], p["y"], p["z"]]) for p in landmarks}
    rgb = [line.split() for line in (args.dataset / "rgb.txt").read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
    times = np.array([float(row[0]) for row in rgb])
    original_matrix, distortion, source_size = load_camera(args.calibration, args.dataset)
    # Keep the calibrated field of view at the smaller inference resolution.
    matrix = resize_intrinsics(original_matrix, source_size, (320, 240))
    model = DepthEstimator(device=args.device, local_files_only=True)
    rng = np.random.default_rng(0)
    chunks, color_chunks, reports, errors, all_fit_errors = [], [], [], [], []
    views, fused_reports = [], []
    for index, row in enumerate(poses):
        timestamp = row[0]
        status = {"timestamp": float(timestamp)}
        links = observations[np.abs(observations["timestamp"]-timestamp) < 1e-4]
        points = np.array([point_lookup[int(link["landmark_id"])] for link in links
                           if int(link["landmark_id"]) in point_lookup]).reshape(-1, 3)
        pose = np.eye(4)
        pose[:3, :3] = Rotation.from_quat(row[4:8]).as_matrix()
        pose[:3, 3] = row[1:4]
        _, uv, z = project_landmarks(points, pose, matrix, distortion, (320, 240))
        # For overlapping sparse projections, keep the nearest point per pixel.
        order = np.argsort(z)
        if len(order):
            _, unique = np.unique(np.round(uv[order]).astype(int), axis=0, return_index=True)
            keep = order[unique]
            uv, z = uv[keep], z[keep]
        if len(z) < 40:
            status.update(status="skipped", reason="Fewer than 40 visible observed landmarks")
            reports.append(status)
            continue
        # Preserve the original per-view split even when exporting a time segment.
        split = rng.permutation(len(z))
        heldout, training = split[:max(8, len(z)//5)], split[max(8, len(z)//5):]
        if ((args.start_time is not None and timestamp<args.start_time) or
                (args.end_time is not None and timestamp>args.end_time)):
            status.update(status="outside_interval")
            reports.append(status)
            continue
        frame_index = int(np.argmin(np.abs(times-timestamp)))
        if abs(times[frame_index]-timestamp) > 0.001:
            raise ValueError("Keyframe timestamp does not match an original RGB image")
        source_path = (args.dataset / rgb[frame_index][1]).resolve()
        if not source_path.is_relative_to(args.dataset.resolve()):
            raise ValueError("RGB image path escapes the dataset")
        original = cv2.imread(str(source_path))
        if original is None or (original.shape[1], original.shape[0]) != source_size:
            raise ValueError(f"RGB image dimensions must match calibration: {source_size}")
        image = cv2.resize(original, (320, 240), interpolation=cv2.INTER_AREA)
        predicted = model.predict(image)
        sampled = sample_bilinear(predicted, uv)
        try:
            fit = fit_inverse_depth(sampled[training], z[training], seed=index)
        except ValueError as exc:
            status.update(status="skipped", reason=str(exc))
            reports.append(status)
            continue
        heldout_depth = fit.depth(sampled[heldout])
        valid = np.isfinite(heldout_depth)
        relative = np.abs(heldout_depth[valid]-z[heldout][valid])/z[heldout][valid]
        all_fit_errors.extend(relative.tolist())
        status.update(heldout_samples=len(heldout), invalid_heldout=int((~valid).sum()),
                      heldout_abs_rel_mean=float(relative.mean()) if len(relative) else None)
        depth = fit.depth(predicted)
        if args.quality_checks:
            support, quality = alignment_support(fit, predicted, uv[training], sampled[training], z[training])
            status["quality"] = quality
            if support is None:
                status.update(status="rejected_quality", reason=quality["rejection"])
                reports.append(status)
                continue
            depth[~support] = np.nan
        errors.extend(relative.tolist())
        # Bound extrapolation far beyond sparse support; not a metric distance limit.
        max_depth = float(np.percentile(z[training], 95)*1.5)
        dense, colors = backproject(depth, image, matrix, distortion, pose, stride=3, max_depth=max_depth)
        chunks.append(dense)
        color_chunks.append(colors)
        views.append((pose, depth))
        fused_reports.append(status)
        status.update(status="fused", visible_landmarks=len(z), training_samples=len(training),
                      training_inliers=fit.inliers, heldout_samples=len(heldout),
                      invalid_heldout=int((~valid).sum()), inverse_depth_scale=fit.scale,
                      inverse_depth_shift=fit.shift,
                      heldout_abs_rel_mean=float(relative.mean()) if len(relative) else None,
                      dense_points=len(dense), max_depth_slam_units=max_depth)
        reports.append(status)
        print(f"Keyframe {index+1}/{len(poses)}: {len(dense)} dense points", flush=True)
    if args.multiview_checks:
        for index in range(len(chunks)):
            keep, consistency = multiview_support(chunks[index], index, views, matrix, distortion)
            chunks[index], color_chunks[index] = chunks[index][keep], color_chunks[index][keep]
            fused_reports[index]["multiview"] = consistency
        reportable = [(p, c) for p, c in zip(chunks, color_chunks) if len(p)]
        chunks = [p for p, c in reportable]
        color_chunks = [c for p, c in reportable]
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"coordinate_units": "arbitrary monocular SLAM units; not meters", "keyframes": reports,
              "source_timestamp_interval": [args.start_time,args.end_time],
              "dataset": str(args.dataset), "slam_export": str(args.slam),
              "calibration": str(args.calibration) if args.calibration else "TUM Freiburg 1 RGB",
              "calibrated_size_wh": source_size, "inference_size_wh": [320, 240],
              "resized_camera_matrix": matrix.tolist(), "distortion_coefficients": distortion.tolist(),
              "fused_keyframes": len(chunks), "heldout_valid_samples": len(errors),
              "quality_checks": args.quality_checks,
              "multiview_checks": args.multiview_checks,
              "multiview_policy": "At least one other supported view, >=1 degree ray angle, <=10% z-depth disagreement, no observed free-space conflict; occlusions give no support" if args.multiview_checks else None,
              "quality_policy": "training rank correlation >=0.3; depth support >=70% and >=50 points; hull >=5% image; dense pixels inside training hull and 1st-99th prediction percentiles" if args.quality_checks else None,
              "all_fit_heldout_samples": len(all_fit_errors),
              "all_fit_heldout_abs_rel_mean": float(np.mean(all_fit_errors)) if all_fit_errors else None,
              "heldout_abs_rel_mean": float(np.mean(errors)) if errors else None,
              "heldout_abs_rel_median": float(np.median(errors)) if errors else None,
              "evaluation_note": "Held-out SLAM points are not independent sensor ground truth; errors evaluate per-view alignments BEFORE multiview dense filtering, not final map accuracy; invalid held-out predictions counted per keyframe",
              "voxel_size_slam_units": args.voxel_size, "depth_model": model.model_id,
              "occupancy_grid": "deferred: no known ground plane or metric scale"}
    if chunks:
        positions, colors = voxel_downsample(np.vstack(chunks), np.vstack(color_chunks), args.voxel_size)
        report["map_points"] = len(positions)
        np.savez_compressed(args.output / "dense_map.npz", points=positions, rgb=colors)
        with (args.output / "dense_map.ply").open("w", encoding="utf-8") as handle:
            handle.write(f"ply\nformat ascii 1.0\nelement vertex {len(positions)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
            np.savetxt(handle, np.column_stack((positions, colors)), fmt=["%.6f"]*3+["%d"]*3)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure = plt.figure(figsize=(10, 7))
        axes = figure.add_subplot(111, projection="3d")
        selected = np.linspace(0, len(positions)-1, min(len(positions), 30000), dtype=int)
        axes.scatter(*positions[selected].T, c=colors[selected]/255, s=1, alpha=0.7)
        display_poses=poses
        if args.start_time is not None:display_poses=display_poses[display_poses[:,0]>=args.start_time]
        if args.end_time is not None:display_poses=display_poses[display_poses[:,0]<=args.end_time]
        axes.plot(*display_poses[:, 1:4].T, color="red", label="Selected keyframe positions")
        axes.set(xlabel="X (SLAM units)", ylabel="Y (SLAM units)", zlabel="Z (SLAM units)",
                 title="Depth aligned to sparse SLAM: offline fusion experiment")
        extent = np.ptp(positions, axis=0)
        axes.set_box_aspect(np.maximum(extent, 0.01))
        axes.legend()
        figure.tight_layout()
        figure.savefig(args.output / "dense_map.png", dpi=160)
        plt.close(figure)
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not chunks:
        raise RuntimeError("No keyframes could be fused; see report.json")
    print(f"Saved {report['map_points']} voxelized points to {args.output}")


if __name__ == "__main__":
    main()
