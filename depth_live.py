"""Live relative depth, saved failure examples, and warm benchmark reports."""
import argparse
import json
from pathlib import Path
import platform
import time

import cv2
import numpy as np

from perception.capture import add_camera_arguments, camera_from_args
from perception.depth import DepthEstimator, colorize_depth, prepare_depth_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_camera_arguments(parser)
    parser.add_argument("--input-width", type=int, help="Depth input width; defaults to --width")
    parser.add_argument("--input-height", type=int, help="Depth input height; defaults to --height")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--precision", choices=["fp32", "fp16"], default="fp32")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--frames", type=int, default=100, help="Measured frames; 0 runs until Q")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("data/depth_report.json"))
    parser.add_argument("--examples", type=Path, default=Path("data/depth_examples"))
    args = parser.parse_args()
    input_width = args.width if args.input_width is None else args.input_width
    input_height = args.height if args.input_height is None else args.input_height
    if min(args.width, args.height, input_width, input_height) <= 0:
        parser.error("Camera and input dimensions must be positive")
    if args.warmup < 0 or args.frames < 0 or (args.headless and args.frames == 0):
        parser.error("Use nonnegative counts and a finite frame count in headless mode")
    print("Loading Depth Anything V2 Small (first run downloads model weights)...", flush=True)
    model = DepthEstimator(args.device, args.precision, args.local_files_only)
    samples, ages = [], []
    sequence, skipped = -1, 0
    recording = None
    actual_sizes = set()
    try:
        with camera_from_args(args) as camera:
            print("Warming up...", flush=True)
            for _ in range(args.warmup):
                packet = camera.get_latest(sequence)
                sequence = packet.sequence
                model.predict(prepare_depth_frame(packet.image, input_width, input_height))
            if model.device == "cuda":
                model.torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            while not args.frames or len(samples) < args.frames:
                packet = camera.get_latest(sequence)
                skipped += max(0, packet.sequence-sequence-1) if sequence >= 0 else 0
                sequence = packet.sequence
                actual_sizes.add((packet.image.shape[1], packet.image.shape[0]))
                resize_started = time.perf_counter()
                frame = prepare_depth_frame(packet.image, input_width, input_height)
                resize_ms = (time.perf_counter()-resize_started)*1000
                depth = model.predict(frame)
                model.last_timings["input_resize_ms"] = resize_ms
                samples.append(model.last_timings.copy())
                age = (time.perf_counter()-packet.captured_at)*1000
                ages.append(age)
                if not args.headless:
                    display = np.hstack((frame, colorize_depth(depth)))
                    cv2.putText(display, f"Relative depth | {model.device} {model.precision} | {model.last_timings['total_ms']:.0f} ms | Age {age:.0f} ms",
                                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    if recording is not None:
                        recording.write(display)
                    cv2.imshow("RGB | Relative inverse depth (bright = nearer) | S save | R record | Q exit", display)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        break
                    if key == ord("s"):
                        args.examples.mkdir(parents=True, exist_ok=True)
                        stem = args.examples / f"example_{time.time_ns()}"
                        cv2.imwrite(str(stem.with_suffix(".png")), display)
                        np.save(stem.with_suffix(".npy"), depth)
                        print(f"Saved {stem}")
                    if key == ord("r"):
                        if recording is not None:
                            recording.release()
                            recording = None
                            print("Recording stopped")
                        else:
                            args.examples.mkdir(parents=True, exist_ok=True)
                            path = args.examples / f"depth_{time.time_ns()}.avi"
                            recording = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"),
                                                        10, (display.shape[1], display.shape[0]))
                            if not recording.isOpened():
                                raise RuntimeError("Could not open video writer")
                            print(f"Recording {path} at fixed 10 FPS; playback timing is illustrative")
            elapsed = time.perf_counter()-started
            report = {"model": model.model_id, "device": model.device, "precision": model.precision,
                      "hardware": platform.platform(), "processor": platform.processor(),
                      "torch": model.torch.__version__, "power_mode": "not recorded; annotate manually",
                      "camera_settings": camera.settings, "network_input_shape": model.input_shape,
                      "actual_camera_sizes_wh": sorted(actual_sizes),
                      "requested_camera_size_wh": [args.width, args.height],
                      "depth_input_size_wh": [input_width, input_height],
                      "resize_policy": "aspect-preserving resize with black padding; network rounds to multiples of 14",
                      "warmup_frames": args.warmup, "measured_frames": len(samples),
                      "elapsed_seconds": elapsed, "throughput_fps": len(samples)/elapsed,
                      "skipped_frames": skipped, "read_failures": camera.read_failures,
                      "relative_depth_only": True, "timings": {}}
            for metric in samples[0]:
                values = [s[metric] for s in samples]
                report["timings"][metric] = {"mean": float(np.mean(values)),
                                               "p50": float(np.percentile(values, 50)),
                                               "p95": float(np.percentile(values, 95))}
            report["capture_to_depth_ms_p95"] = float(np.percentile(ages, 95))
            if model.device == "cuda":
                report["gpu_name"] = model.torch.cuda.get_device_name()
                report["peak_cuda_allocated_mb"] = model.torch.cuda.max_memory_allocated()/1024**2
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Saved {args.report}; throughput {report['throughput_fps']:.2f} FPS")
    finally:
        if recording is not None:
            recording.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
