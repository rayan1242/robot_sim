"""Compare two TUM trajectories on identical ground-truth timestamp associations."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from .trajectory import associate, align_similarity


def load_trajectory(path):
    data = np.loadtxt(path, ndmin=2)
    if data.shape[1] != 8 or len(data) < 3 or not np.isfinite(data).all():
        raise ValueError(f"Expected at least 3 finite TUM poses: {path}")
    data = data[np.argsort(data[:, 0])]
    if np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError(f"Duplicate trajectory timestamps: {path}")
    return data


def compare(mini, slam, truth):
    mini_match, mini_truth = associate(mini, truth)
    slam_match, slam_truth = associate(slam, truth)
    shared = np.intersect1d(mini_truth[:, 0], slam_truth[:, 0])
    if len(shared) < 3:
        raise ValueError("Fewer than three common ground-truth timestamps")
    output = {"common_pose_count": len(shared), "alignment": "Independent Sim(3) position alignment on common timestamps", "systems": {}}
    trajectories = {}
    target = truth[np.isin(truth[:, 0], shared), 1:4]
    for name, estimate, matched_truth, original in [
            ("mini_vo", mini_match, mini_truth, mini),
            ("stella_vslam", slam_match, slam_truth, slam)]:
        selected = np.flatnonzero(np.isin(matched_truth[:, 0], shared))
        selected = selected[np.argsort(matched_truth[selected, 0])]
        positions = estimate[selected, 1:4]
        aligned, scale = align_similarity(positions, target)
        errors = np.linalg.norm(aligned-target, axis=1)
        output["systems"][name] = {"output_poses": len(original), "associated_poses": len(estimate),
                                    "ate_rmse_m": float(np.sqrt(np.mean(errors**2))),
                                    "ate_median_m": float(np.median(errors)),
                                    "ate_p95_m": float(np.percentile(errors, 95)), "alignment_scale": scale}
        trajectories[name] = aligned
    return output, target, trajectories


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mini", type=Path, default=Path("data/vo_fr1_xyz/trajectory.txt"))
    parser.add_argument("--slam", type=Path, default=Path("data/slam_fr1_xyz/frame_trajectory.txt"))
    parser.add_argument("--truth", type=Path, default=Path("data/rgbd_dataset_freiburg1_xyz/groundtruth.txt"))
    parser.add_argument("--output", type=Path, default=Path("docs/phase4"))
    args = parser.parse_args()
    report, target, trajectories = compare(load_trajectory(args.mini), load_trajectory(args.slam), load_trajectory(args.truth))
    tracking = args.slam.parent / "tracking.csv"
    rows = []
    if tracking.exists():
        with tracking.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    if rows and {"pose_available", "tracking_ms"}.issubset(rows[0]):
        report["stella_tracking"] = {"input_frames": len(rows),
                                    "pose_available_frames": sum(int(row["pose_available"]) for row in rows),
                                    "note": "Unavailable poses include initialization; this is not purely tracking loss",
                                    "tracking_ms_p50": float(np.median([float(row["tracking_ms"]) for row in rows])),
                                    "tracking_ms_p95": float(np.percentile([float(row["tracking_ms"]) for row in rows], 95))}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Phase 4: common-timestamp comparison", "", f"Common poses: {len(target)}. Both systems aligned independently with Sim(3).", "",
             "| System | ATE RMSE (m) | Median (m) | p95 (m) | Output poses |", "|---|---:|---:|---:|---:|"]
    for name, result in report["systems"].items():
        lines.append(f"| {name} | {result['ate_rmse_m']:.4f} | {result['ate_median_m']:.4f} | {result['ate_p95_m']:.4f} | {result['output_poses']} |")
    lines.extend(["", "Mini VO holds poses on failed steps; SLAM can omit initialization/lost poses.",
                  "Comparison uses only shared ground-truth associations; report coverage alongside error.",
                  "These are scale-aligned positional errors, not recovered metric scale or orientation errors.",
                  "Processing times span different implementations/environments and are not a controlled speed comparison."])
    (args.output / "comparison.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(9, 7))
    axes = fig.add_subplot(111, projection="3d")
    axes.plot(*target.T, label="Ground truth")
    for name, positions in trajectories.items():
        axes.plot(*positions.T, label=name)
    axes.set(xlabel="X (m)", ylabel="Y (m)", zlabel="Z (m)", title="Common-timestamp Sim(3) trajectory comparison")
    extent = np.ptp(np.vstack([target, *trajectories.values()]), axis=0)
    axes.set_box_aspect(np.maximum(extent, 0.01))
    axes.legend()
    fig.tight_layout()
    fig.savefig(args.output / "trajectories.png", dpi=160)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
