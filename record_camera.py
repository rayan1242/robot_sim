"""Save original webcam frames and receipt timestamps for later offline SLAM."""
import argparse
import csv
import json
from pathlib import Path
import time

import cv2

from perception.capture import add_camera_arguments, camera_from_args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_camera_arguments(parser)
    parser.set_defaults(backend="dshow")
    parser.add_argument("--output", type=Path, default=Path("data/recordings") / str(time.time_ns()))
    parser.add_argument("--duration", type=float, default=30)
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("Duration must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "rgb").mkdir()
    sequence, saved = -1, 0
    sizes = set()
    try:
        with camera_from_args(args) as camera, (args.output / "rgb.txt").open("w", encoding="utf-8") as index:
            index.write("# RGB-only webcam recording\n# monotonic seconds since recording start\n# timestamp filename\n")
            with (args.output / "timestamps.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["timestamp", "sequence", "receipt_perf_counter"])
                origin = None
                started = time.perf_counter()
                while time.perf_counter()-started < args.duration:
                    packet = camera.get_latest(sequence)
                    sequence = packet.sequence
                    if origin is None:
                        origin = packet.captured_at
                    timestamp = packet.captured_at-origin
                    sizes.add((packet.image.shape[1], packet.image.shape[0]))
                    filename = f"rgb/{saved:06d}.png"
                    if not cv2.imwrite(str(args.output / filename), packet.image):
                        raise RuntimeError("Could not write raw image")
                    index.write(f"{timestamp:.9f} {filename}\n")
                    writer.writerow([timestamp, sequence, packet.captured_at])
                    saved += 1
                    cv2.imshow("Record raw webcam | Q to stop", packet.image)
                    if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                        break
            metadata = {"camera_settings": camera.settings, "actual_sizes_wh": sorted(sizes),
                        "frames": saved, "timestamps": "monotonic software receipt time, relative to first frame",
                        "calibration": "not attached; calibrate at this resolution and focus before SLAM",
                        "warning": "Consumer disk IO may skip frames; timestamps preserve actual spacing"}
            (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"Saved {saved} raw frames to {args.output}")
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
