"""Validate and plot a stella sparse-map export in its original arbitrary scale."""
import argparse
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/slam_fr1_xyz"))
    parser.add_argument("--output", type=Path, default=Path("docs/phase4"))
    args = parser.parse_args()
    landmarks = np.genfromtxt(args.input / "landmarks.csv", delimiter=",", names=True, ndmin=1)
    if not len(landmarks):
        raise ValueError("Map contains no landmarks")
    positions = np.column_stack([landmarks[axis] for axis in ("x", "y", "z")])
    if not np.isfinite(positions).all():
        raise ValueError("Map contains nonfinite landmark positions")
    poses = np.loadtxt(args.input / "keyframe_trajectory.txt", ndmin=2)
    observations = np.genfromtxt(args.input / "observations.csv", delimiter=",", names=True, ndmin=1)
    if not set(observations["landmark_id"]).issubset(set(landmarks["id"])):
        raise ValueError("Observation refers to a missing landmark")
    report = {"landmarks": len(positions), "keyframe_poses": len(poses),
              "observation_links": len(observations), "coordinate_units": "arbitrary monocular SLAM units",
              "finite_landmarks": True, "valid_observation_landmark_ids": True}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "map_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Portable point-cloud artifact for inspection in external 3D tools.
    with (args.output / "sparse_map.ply").open("w", encoding="utf-8") as handle:
        handle.write(f"ply\nformat ascii 1.0\nelement vertex {len(positions)}\nproperty float x\nproperty float y\nproperty float z\nend_header\n")
        np.savetxt(handle, positions, fmt="%.8f")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(9, 7))
    axes = fig.add_subplot(111, projection="3d")
    # Extreme sparse outliers may dominate the view; keep them in the PLY but crop
    # only this visualization to the central 98 percent in each dimension.
    low, high = np.percentile(positions, [1, 99], axis=0)
    selected = positions[np.all((positions >= low) & (positions <= high), axis=1)]
    axes.scatter(*selected.T, s=1, alpha=0.4, label="Landmarks (central 98% bounds)")
    axes.plot(*poses[:, 1:4].T, color="red", label="Keyframe trajectory")
    axes.set(xlabel="X (SLAM units)", ylabel="Y (SLAM units)", zlabel="Z (SLAM units)", title="Sparse monocular map")
    axes.legend()
    fig.tight_layout()
    fig.savefig(args.output / "sparse_map.png", dpi=160)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
