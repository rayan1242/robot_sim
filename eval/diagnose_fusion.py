"""Audit exported geometry against saved SLAM observations and model depth."""
import argparse
import json
from pathlib import Path

import cv2
import msgpack
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.stats import spearmanr

from fuse_dataset import load_camera, resize_intrinsics
from perception.depth import DepthEstimator
from perception.fusion import project_landmarks, sample_bilinear


def audit_keyframe(keyframe, landmarks, matrix):
    rotation = Rotation.from_quat(keyframe["rot_cw"]).as_matrix()
    translation = np.array(keyframe["trans_cw"])
    points, observed = [], []
    for i, landmark_id in enumerate(keyframe["lm_ids"]):
        landmark = landmarks.get(str(landmark_id))
        if landmark is not None:
            points.append(landmark["pos_w"])
            observed.append(keyframe["undist_keypts"][i]["pt"])
    points, observed = np.array(points).reshape(-1, 3), np.array(observed).reshape(-1, 2)
    camera = points @ rotation.T + translation
    valid = camera[:, 2] > 1e-8
    projected = camera[valid] @ matrix.T
    uv = projected[:, :2]/projected[:, 2:3]
    residuals = np.linalg.norm(uv-observed[valid], axis=1)
    pose = np.eye(4)
    pose[:3, :3] = rotation.T
    pose[:3, 3] = -rotation.T @ translation
    return pose, points, residuals


def landmark_view_angles(data):
    """Maximum retained-view ray angle per map point, as an internal parallax check."""
    rays = {}
    for keyframe in data["keyframes"].values():
        rotation = Rotation.from_quat(keyframe["rot_cw"]).as_matrix()
        center = -rotation.T @ np.array(keyframe["trans_cw"])
        for identifier in set(keyframe["lm_ids"]):
            point = data["landmarks"].get(str(identifier))
            if point is None:
                continue
            ray = np.array(point["pos_w"])-center
            norm = np.linalg.norm(ray)
            if norm > 1e-10:
                rays.setdefault(identifier, []).append(ray/norm)
    angles = {}
    for identifier,observations in rays.items():
        if len(observations) < 2:
            continue
        vectors = np.array(observations)
        angles[identifier]=float(np.degrees(np.arccos(np.clip(np.min(vectors @ vectors.T), -1, 1))))
    return angles


def triangulation_angles(data):
    return list(landmark_view_angles(data).values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--slam", type=Path, required=True)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-keyframes", type=int, default=8)
    parser.add_argument('--width',type=int,default=320)
    parser.add_argument('--height',type=int,default=240)
    args = parser.parse_args()
    if args.max_keyframes < 1:
        parser.error("max-keyframes must be positive")
    if min(args.width,args.height)<14:parser.error('Inference dimensions must be at least 14')
    matrix, distortion, size = load_camera(args.calibration, args.dataset)
    inference_size=(args.width,args.height)
    scaled = resize_intrinsics(matrix, size, inference_size)
    data = msgpack.unpackb((args.slam/"map.msg").read_bytes(), raw=False, strict_map_key=False)
    keyframes = sorted(data["keyframes"].values(), key=lambda k: k["ts"])
    if not keyframes:
        raise ValueError("No saved keyframes")
    selected = np.linspace(0, len(keyframes)-1, min(len(keyframes), args.max_keyframes), dtype=int)
    rgb = [line.split() for line in (args.dataset/"rgb.txt").read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#")]
    times = np.array([float(row[0]) for row in rgb])
    exported_poses = np.loadtxt(args.slam/"keyframe_trajectory.txt", ndmin=2)
    model = DepthEstimator(local_files_only=True)
    rows, all_residuals = [], []
    arrays = {}
    for i in selected:
        keyframe = keyframes[i]
        pose, points, residuals = audit_keyframe(keyframe, data["landmarks"], matrix)
        all_residuals.extend(residuals.tolist())
        exported = exported_poses[np.argmin(abs(exported_poses[:, 0]-keyframe["ts"]))]
        exported_pose = np.eye(4)
        exported_pose[:3, :3] = Rotation.from_quat(exported[4:8]).as_matrix()
        exported_pose[:3, 3] = exported[1:4]
        frame_index = int(np.argmin(abs(times-keyframe["ts"])))
        path = (args.dataset/rgb[frame_index][1]).resolve()
        if not path.is_relative_to(args.dataset.resolve()):
            raise ValueError("Image path escapes dataset")
        image = cv2.imread(str(path))
        if image is None or (image.shape[1], image.shape[0]) != size:
            raise ValueError("Invalid image dimensions")
        predicted = model.predict(cv2.resize(image, inference_size, interpolation=cv2.INTER_AREA))
        point_ids=np.array([identifier for identifier in keyframe['lm_ids'] if str(identifier) in data['landmarks']],dtype=np.int64)
        projected_ids, uv, z = project_landmarks(points, pose, scaled, distortion, inference_size)
        values = sample_bilinear(predicted, uv)
        valid = np.isfinite(values) & np.isfinite(z) & (z > 0)
        values, z = values[valid], z[valid]
        correlation = None
        slope = None
        if len(z) >= 3 and np.ptp(values) > 1e-8 and np.ptp(z) > 1e-8:
            correlation = float(spearmanr(values, 1/z).statistic)
            slope = float(np.linalg.lstsq(np.column_stack((values, np.ones(len(values)))), 1/z, rcond=None)[0][0])
        camera = data["cameras"][keyframe["cam"]]
        rows.append({"timestamp": keyframe["ts"], "observation_count": len(residuals),
                     "reprojection_median_px": float(np.median(residuals)) if len(residuals) else None,
                     "reprojection_p95_px": float(np.percentile(residuals, 95)) if len(residuals) else None,
                     "exported_pose_max_abs_difference": float(abs(pose-exported_pose).max()),
                     "camera_matrix_max_abs_difference": float(max(abs(matrix[0,0]-camera['fx']), abs(matrix[1,1]-camera['fy']), abs(matrix[0,2]-camera['cx']), abs(matrix[1,2]-camera['cy']))),
                     "distorted_projection_samples": len(z), "rgb_timestamp_difference": float(abs(times[frame_index]-keyframe["ts"])),
                     "prediction_inverse_depth_spearman": correlation, "unconstrained_inverse_depth_slope": slope})
        arrays[f"prediction_{i}"] = values
        arrays[f"inverse_depth_{i}"] = 1/z
        arrays[f'landmark_ids_{i}']=point_ids[projected_ids][valid]
        print(f"Audited {keyframe['ts']:.3f}: rank correlation {correlation}", flush=True)
    angles = triangulation_angles(data)
    report = {"dataset": str(args.dataset), "slam": str(args.slam), "keyframes": rows,
              'inference_size_wh':inference_size,
              "landmark_max_ray_angle_degrees_median": float(np.median(angles)) if angles else None,
              "landmark_max_ray_angle_degrees_p10": float(np.percentile(angles, 10)) if angles else None,
              "pooled_reprojection_median_px": float(np.median(all_residuals)),
              "pooled_reprojection_p95_px": float(np.percentile(all_residuals, 95)),
              "note": "Reprojection is internal SLAM consistency, not independent accuracy. Correlations are diagnostics, not used to tune acceptance."}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"diagnostics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    np.savez_compressed(args.output/"correspondences.npz", **arrays)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 4, figsize=(14, 7), squeeze=False)
    for ax, i, row in zip(axes.ravel(), selected, rows):
        ax.scatter(arrays[f"prediction_{i}"], arrays[f"inverse_depth_{i}"], s=4, alpha=0.5)
        ax.set(title=f"t={row['timestamp']:.2f} | rho={row['prediction_inverse_depth_spearman']}",
               xlabel="Network relative inverse depth", ylabel="1 / SLAM z")
    for ax in axes.ravel()[len(rows):]:
        ax.set_visible(False)
    fig.tight_layout()
    fig.savefig(args.output/"correspondences.png", dpi=140)
    plt.close(fig)
    print(json.dumps({key:value for key,value in report.items() if key != "keyframes"}, indent=2))


if __name__ == "__main__":
    main()
