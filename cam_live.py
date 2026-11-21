"""Live preview and latency diagnostics. Press Q or Escape to exit."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np

from perception.capture import add_camera_arguments, camera_from_args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_camera_arguments(parser)
    parser.add_argument("--consumer-delay", type=float, default=0, help="Artificial processing delay in seconds")
    parser.add_argument("--duration", type=float, default=0, help="Stop after seconds; 0 means unlimited")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("data/capture_report.json"))
    args = parser.parse_args()
    ages, input_ages, sequence, skipped, count = [], [], -1, 0, 0
    started = time.perf_counter()
    try:
        with camera_from_args(args) as camera:
            print(json.dumps(camera.settings, indent=2))
            while not args.duration or time.perf_counter() - started < args.duration:
                packet = camera.get_latest(after_sequence=sequence)
                input_age = (time.perf_counter() - packet.captured_at) * 1000
                input_ages.append(input_age)
                if args.consumer_delay:
                    time.sleep(max(0, args.consumer_delay))
                age = (time.perf_counter() - packet.captured_at) * 1000
                ages.append(age)
                skipped += max(0, packet.sequence - sequence - 1) if sequence >= 0 else 0
                sequence = packet.sequence
                count += 1
                elapsed = time.perf_counter() - started
                if not args.headless:
                    display = packet.image.copy()
                    lines = [f"Capture {camera.capture_fps:.1f} FPS | Consumer {count / elapsed:.1f} FPS",
                             f"Input age {input_age:.1f} ms | After processing {age:.1f} ms",
                             f"Skipped {skipped} | Read failures {camera.read_failures}"]
                    for i, line in enumerate(lines):
                        cv2.putText(display, line, (10, 25 + i * 25), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5, (0, 255, 0), 1)
                    cv2.imshow("Camera preview", display)
                    if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                        break
            report = {"settings": camera.settings, "frames_consumed": count,
                      "skipped_frames": skipped, "read_failures": camera.read_failures,
                      "elapsed_seconds": time.perf_counter() - started,
                      "capture_fps": camera.capture_fps,
                      "input_age_ms_p50": float(np.percentile(input_ages, 50)) if input_ages else None,
                      "input_age_ms_p95": float(np.percentile(input_ages, 95)) if input_ages else None,
                      "input_age_ms_start_median": float(np.median(input_ages[:max(1, len(input_ages)//5)])) if input_ages else None,
                      "input_age_ms_end_median": float(np.median(input_ages[-max(1, len(input_ages)//5):])) if input_ages else None,
                      "frame_age_ms_p50": float(np.percentile(ages, 50)) if ages else None,
                      "frame_age_ms_p95": float(np.percentile(ages, 95)) if ages else None,
                      "timestamp_note": "Software receipt time; excludes hidden sensor/driver buffering"}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Report saved to {args.report}")
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
