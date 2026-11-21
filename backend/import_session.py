"""Copy saved RGB/pose/map artifacts into a self-contained replay session."""
import argparse
import json
from pathlib import Path
import shutil

import cv2
import numpy as np

from .protocol import encode_cloud
from .store import SessionStore


def import_session(store, dataset, trajectory=None, cloud=None, name="Imported session", stride=1, max_frames=0,
                   tracking=None, fusion_report=None, with_depth=False):
    dataset = Path(dataset).resolve()
    if stride < 1 or max_frames < 0:
        raise ValueError("Invalid stride or frame count")
    rows = [line.split() for line in (dataset/"rgb.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")][::stride]
    if max_frames:
        rows = rows[:max_frames]
    if not rows:
        raise ValueError("No RGB frames")
    times = np.array([float(row[0]) for row in rows])
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("RGB timestamps must be finite and strictly increasing")
    poses = None
    if trajectory:
        poses = np.loadtxt(trajectory, ndmin=2)
        if poses.shape[1] != 8 or not np.isfinite(poses).all():
            raise ValueError("Invalid TUM trajectory")
        poses = poses[np.argsort(poses[:, 0])]
    if cloud:
        encode_cloud(Path(cloud))
    from .replay_analysis import analysis_report
    analysis = analysis_report(tracking, fusion_report)
    metadata = {"source": "offline_import", "original_dataset": str(dataset),
                "trajectory": str(trajectory) if trajectory else None, "map": str(cloud) if cloud else None,
                "frames": len(rows), "stride": stride, "duration_seconds": float(times[-1]-times[0]),
                "coordinate_units": "arbitrary SLAM units", "cloud_semantics": "final_static_snapshot",
                "limitations": ["Offline optimized poses; not live tracking", "Map is the final static snapshot, not incremental reconstruction",
                                "No metric scale or accuracy claim", "Per-stage latency unavailable for imported artifacts"]}
    saved = store.create(name, metadata, "importing")
    directory = store.path(saved["id"])
    (directory/"rgb").mkdir()
    matched = 0
    try:
        model = None
        if with_depth:
            from perception.depth import DepthEstimator
            model = DepthEstimator(device="cpu", local_files_only=True)
            # Warm up separately; timings below measure offline inference, not capture latency.
            warmup_path = (dataset/rows[0][1]).resolve()
            if not warmup_path.is_relative_to(dataset):raise ValueError("RGB path escapes dataset")
            first = cv2.imread(str(warmup_path))
            if first is None:raise ValueError("Unreadable warm-up image")
            model.predict(cv2.resize(first, (320,240), interpolation=cv2.INTER_AREA))
            metadata['depth_model'] = model.model_id
            metadata['depth_device'] = model.device
            metadata['limitations'][-1] = "Only measured offline depth and recorded SLAM call timings; capture/fusion/network latency unavailable"
        (directory/'analysis.json').write_text(json.dumps(analysis,indent=2),encoding='utf-8')
        with (directory/"states.jsonl").open("w", encoding="utf-8") as handle:
            for index, row in enumerate(rows):
                timestamp, filename = float(row[0]), row[1]
                source = (dataset/filename).resolve()
                if not source.is_relative_to(dataset) or not source.is_file():
                    raise ValueError("RGB path is missing or escapes dataset")
                image = cv2.imread(str(source))
                if image is None:
                    raise ValueError("Unreadable RGB image")
                filename = f"rgb/{index:06d}.png"
                if not cv2.imwrite(str(directory/filename), image):
                    raise RuntimeError("Could not store imported image")
                pose = None
                if poses is not None:
                    nearest = int(np.argmin(abs(poses[:, 0]-timestamp)))
                    if abs(poses[nearest, 0]-timestamp) <= 0.02:
                        pose = poses[nearest, 1:8].tolist()
                        matched += 1
                state = {"timestamp": timestamp-times[0], "source_timestamp": timestamp,
                         "sequence": index, "rgb_path": filename, "pose": pose,
                         "pose_status": "available" if pose else "unavailable", "pose_format": "tx ty tz qx qy qz qw; camera-to-world",
                         "latency_ms": None, "fps": None, "device": "offline", "limitations": metadata["limitations"]}
                if model is not None:
                    prediction = model.predict(cv2.resize(image,(320,240),interpolation=cv2.INTER_AREA))
                    np.save(directory/f'depth_{index:06d}.npy',prediction)
                    state.update(depth_kind='relative_inverse',offline_depth_ms=model.last_timings.copy(),device=model.device,model=model.model_id)
                if analysis['tracking']:
                    sample = min(analysis['tracking']['samples'],key=lambda s:abs(s['timestamp']-timestamp))
                    if abs(sample['timestamp']-timestamp)<0.001:
                        state.update(tracking_available=sample['available'],offline_slam_ms=sample['tracking_ms'])
                handle.write(json.dumps(state)+"\n")
                if model is not None and index%25==0:print(f'Prepared {index+1}/{len(rows)} replay frames',flush=True)
        if cloud:
            shutil.copyfile(cloud, directory/"map.npz")
        if trajectory:
            shutil.copyfile(trajectory, directory/"poses.txt")
        metadata["pose_matched_frames"] = matched
        metadata["image_size_wh"] = [image.shape[1], image.shape[0]]
        return store.update(saved["id"], "ready", metadata)
    except Exception as exc:
        store.update(saved["id"], "error", {**metadata, "error": str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/rgbd_dataset_freiburg1_xyz"))
    parser.add_argument("--trajectory", type=Path, default=Path("data/slam_fr1_xyz/frame_trajectory.txt"))
    parser.add_argument("--cloud", type=Path, default=Path("data/fusion_fr1_xyz/dense_map.npz"))
    parser.add_argument("--root", type=Path, default=Path("data/sessions"))
    parser.add_argument("--name", default="TUM validated offline pipeline")
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--tracking",type=Path)
    parser.add_argument("--fusion-report",type=Path)
    parser.add_argument("--with-depth",action="store_true",help="Precompute synchronized relative depth on CPU")
    args = parser.parse_args()
    result = import_session(SessionStore(args.root), args.dataset, args.trajectory, args.cloud,
                            args.name, args.stride, args.max_frames,args.tracking,args.fusion_report,args.with_depth)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
