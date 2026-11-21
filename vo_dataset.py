"""Run mini monocular VO on the original TUM freiburg1_xyz RGB sequence."""
import argparse
import csv
import json
from pathlib import Path
import time

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from perception.vo import VisualOdometry
from eval.trajectory import associate, align_similarity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/rgbd_dataset_freiburg1_xyz"))
    parser.add_argument("--output", type=Path, default=Path("data/vo_fr1_xyz"))
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--max-frames", type=int, default=0)
    args = parser.parse_args()
    if args.stride < 1 or args.max_frames < 0:
        parser.error("Stride must be positive; max-frames must be nonnegative")
    index = args.dataset / "rgb.txt"
    rows = [line.split() for line in index.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    rows = rows[::args.stride]
    if args.max_frames:
        rows = rows[:args.max_frames]
    if len(rows) < 3:
        parser.error("Need at least three RGB frames")
    odometry = VisualOdometry()
    trajectory, diagnostics = [], []
    for i, (timestamp, filename) in enumerate(rows):
        path = (args.dataset / filename).resolve()
        if not path.is_relative_to(args.dataset.resolve()):
            raise ValueError("RGB index path escapes dataset directory")
        image = cv2.imread(str(path))
        if image is None or image.shape[:2] != (480, 640):
            raise ValueError(f"Expected original 640x480 RGB image: {path}")
        started = time.perf_counter()
        pose, status = odometry.update(image)
        quaternion = Rotation.from_matrix(pose[:3, :3]).as_quat()
        trajectory.append([float(timestamp), *pose[:3, 3], *quaternion])
        diagnostics.append({"timestamp": timestamp, **status, "latency_ms": (time.perf_counter()-started)*1000})
        if i % 100 == 0:
            print(f"Frame {i+1}/{len(rows)}: {status['status']}", flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    estimate = np.array(trajectory)
    np.savetxt(args.output / "trajectory.txt", estimate, fmt="%.9f", header="timestamp tx ty tz qx qy qz qw")
    with (args.output / "tracking.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(diagnostics[0]))
        writer.writeheader()
        writer.writerows(diagnostics)
    truth = np.loadtxt(args.dataset / "groundtruth.txt", ndmin=2)
    truth = truth[np.argsort(truth[:, 0])]
    matched_estimate, matched_truth = associate(estimate, truth)
    aligned, scale = align_similarity(matched_estimate[:, 1:4], matched_truth[:, 1:4])
    errors = np.linalg.norm(aligned-matched_truth[:, 1:4], axis=1)
    tracked = sum(row["status"] == "tracked" for row in diagnostics)
    report = {"dataset": str(args.dataset), "frames": len(rows), "stride": args.stride,
              "associated_poses": len(errors), "tracked_steps": tracked,
              "lost_steps": sum(row["status"] == "lost" for row in diagnostics),
              "low_motion_steps": sum(row["status"] == "low_motion" for row in diagnostics),
              "tracking_rate": tracked/(len(rows)-1), "alignment": "Sim(3) on associated positions",
              "alignment_scale": scale, "ate_rmse_m": float(np.sqrt(np.mean(errors**2))),
              "ate_median_m": float(np.median(errors)), "ate_p95_m": float(np.percentile(errors, 95)),
              "mean_vo_latency_ms": float(np.mean([row["latency_ms"] for row in diagnostics])),
              "limitations": "Unit translation per accepted step; no relative step scale, map, loop closure, or pure-rotation handling. Failed steps hold pose. Ground truth used only for evaluation."}
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure = plt.figure(figsize=(9, 7))
    axes = figure.add_subplot(111, projection="3d")
    axes.plot(*matched_truth[:, 1:4].T, label="Ground truth")
    axes.plot(*aligned.T, label="Mini VO (Sim3 aligned)")
    axes.set(xlabel="X (m)", ylabel="Y (m)", zlabel="Z (m)", title=f"TUM fr1_xyz | ATE RMSE {report['ate_rmse_m']:.3f} m")
    span = np.ptp(np.vstack((matched_truth[:, 1:4], aligned)), axis=0)
    axes.set_box_aspect(np.maximum(span, 0.01))
    axes.legend()
    figure.tight_layout()
    figure.savefig(args.output / "trajectory.png", dpi=160)
    plt.close(figure)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
