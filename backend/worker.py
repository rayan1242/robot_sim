"""Workers own acquisition/replay and recording; a slow browser cannot queue perception."""
import csv
import json
from pathlib import Path
from queue import Empty, Full
import time

import cv2
import numpy as np

from .protocol import encode_cloud, encode_cloud_arrays, packet
from .map_io import save_snapshot


def publish(queue, value):
    try:
        queue.put_nowait(value)
    except Full:
        try:
            queue.get(timeout=0.01)
        except Empty:
            pass
        try:
            queue.put_nowait(value)
        except Full:
            pass


def replay_worker(directory, queue, stop, speed=1.0):
    directory = Path(directory)
    try:
        cloud, count = encode_cloud(directory/"map.npz")
        with (directory/"states.jsonl").open(encoding="utf-8") as source:
            started = time.perf_counter()
            first = None
            sequence = 0
            for line in source:
                state = json.loads(line)
                if first is None:
                    first = state["timestamp"]
                target = started+(state["timestamp"]-first)/speed
                if stop.wait(max(0, target-time.perf_counter())):
                    break
                image_path = (directory/state["rgb_path"]).resolve()
                if not image_path.is_relative_to(directory.resolve()):
                    raise ValueError("Image path escapes session")
                image = cv2.imread(str(image_path))
                if image is None:
                    raise ValueError(f"Missing frame: {state['rgb_path']}")
                ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if not ok:
                    raise RuntimeError("JPEG encoding failed")
                publish(queue, packet({**state, "mode": "replay", "sequence": sequence,
                                       'cloud_semantics':'final_static_snapshot' if cloud else None,
                                       "state": "running", "replay_speed": speed}, jpeg.tobytes(), cloud, count))
                sequence += 1
    except Exception as exc:
        publish(queue, packet({"mode": "replay", "state": "error", "error": str(exc)}))
    finally:
        # Completion is detected from process exit; don't replace the final data packet.
        queue.close()
        queue.join_thread()


def camera_worker(directory, options, queue, stop):
    from perception.capture import CameraCapture
    directory = Path(directory)
    writer = None
    from perception.timing import TimingSummary
    summary=TimingSummary(options.get('deadline_ms',500))
    bridge=feeder=None
    keyframe_window=None
    try:
        (directory/"rgb").mkdir(exist_ok=True)
        if options.get('slam'):
            from perception.live_slam import SlamProcess,SlamCapture,live_cloud
            from fuse_dataset import load_camera,resize_intrinsics
            from scipy.spatial.transform import Rotation
            calibration_path=Path(options.get('slam_calibration','data/calibration.npz'))
            matrix,distortion,size=load_camera(calibration_path,directory)
            if size!=(640,480):raise ValueError('Live SLAM requires a 640x480 calibration')
            matrix=resize_intrinsics(matrix,size,(options.get('depth_width',320),options.get('depth_height',240)))
            bridge=SlamProcess(directory/'slam_input',transport=options.get('slam_transport','raw'),keyframes=options.get('keyframe_map',False),
                               calibration_path=calibration_path,config_path=options.get('slam_config'))
            if options.get('keyframe_map'):
                from perception.keyframe_window import ActiveKeyframeWindow
                keyframe_window=ActiveKeyframeWindow()
        depth = None
        if options["depth"]:
            from perception.depth import DepthEstimator
            depth = DepthEstimator(device=options["device"], local_files_only=True)
        with CameraCapture(camera=options["camera"], width=options["width"], height=options["height"],
                           fps=options["fps"], backend=options["backend"],auto_exposure=options.get('auto_exposure',False)) as camera:
            sequence, origin, saved = -1, None, 0
            if bridge:
                feeder=SlamCapture(camera,bridge);origin=feeder.origin
            with (directory/"states.jsonl").open("w", encoding="utf-8") as states, (directory/"timestamps.csv").open("w", newline="", encoding="utf-8") as handle:
                timestamps = csv.writer(handle)
                timestamps.writerow(["timestamp", "capture_sequence", "perf_counter"])
                while not stop.is_set():
                    slam_result=None
                    if feeder:frame,slam_result=feeder.get_latest(sequence)
                    else:frame=camera.get_latest(sequence)
                    skipped = max(0, frame.sequence-sequence-1) if sequence >= 0 else 0
                    sequence = frame.sequence
                    if origin is None:
                        origin = frame.captured_at
                    elapsed = frame.captured_at-origin
                    if elapsed >= options["duration"]:
                        break
                    image = frame.image
                    input_age_ms=(time.perf_counter()-frame.captured_at)*1000
                    stage_started=time.perf_counter()
                    image_path = f"rgb/{saved:06d}.png"
                    if not cv2.imwrite(str(directory/image_path), image):
                        raise RuntimeError("Frame write failed")
                    if writer is None:
                        writer = cv2.VideoWriter(str(directory/"raw.avi"), cv2.VideoWriter_fourcc(*"MJPG"),
                                                 options["fps"], (image.shape[1], image.shape[0]))
                        if not writer.isOpened():
                            raise RuntimeError("Video writer could not open")
                    writer.write(image)
                    timings = {'rgb_save_ms':(time.perf_counter()-stage_started)*1000}
                    if slam_result is not None:
                        timings.update(slam_roundtrip_ms=slam_result.get('host_roundtrip_ms'),
                            slam_input_ms=slam_result.get('input_ms'),slam_frame_write_ms=slam_result.get('slam_frame_write_ms'),
                            capture_to_slam_selection_ms=slam_result.get('capture_to_slam_selection_ms'),
                            slam_result_wait_ms=max(0,(stage_started-slam_result['host_available_at'])*1000))
                    cloud=b'';cloud_count=0;pose_values=None;fusion_status=None
                    snapshot_warning=None
                    if depth is not None:
                        resize_started=time.perf_counter()
                        depth_image=cv2.resize(image, (options.get('depth_width',320), options.get('depth_height',240)), interpolation=cv2.INTER_AREA)
                        timings['depth_resize_ms']=(time.perf_counter()-resize_started)*1000
                        predicted = depth.predict(depth_image)
                        save_started=time.perf_counter()
                        np.save(directory/f"depth_{saved:06d}.npy", predicted)
                        timings.update(depth.last_timings)
                        timings['depth_save_ms']=(time.perf_counter()-save_started)*1000
                    if slam_result is not None:
                        fusion_started=time.perf_counter()
                        if keyframe_window:
                            positions,colors,pose,fusion_status=keyframe_window.update(slam_result,feeder.keyframe_image,
                                depth.predict,matrix,distortion,(predicted.shape[1],predicted.shape[0]))
                            timings['keyframe_inference_ms']=fusion_status['keyframe_inference_ms']
                            timings['keyframe_window_ms']=fusion_status['window_update_ms']
                        else:
                            positions,colors,pose,fusion_status=live_cloud(slam_result,predicted,
                                cv2.resize(image,(predicted.shape[1],predicted.shape[0]),interpolation=cv2.INTER_AREA),matrix,distortion)
                        if pose is not None:pose_values=[*pose[:3,3].tolist(),*Rotation.from_matrix(pose[:3,:3]).as_quat().tolist()]
                        timings['map_build_ms']=(time.perf_counter()-fusion_started)*1000
                        save_started=time.perf_counter()
                        try:save_snapshot(directory/'map.npz',positions,colors)
                        except PermissionError:
                            snapshot_warning='Map file is locked; live stream continues, saved snapshot may lag until the next successful write'
                        timings['map_save_ms']=(time.perf_counter()-save_started)*1000
                        pack_started=time.perf_counter()
                        cloud,cloud_count=encode_cloud_arrays(positions,colors)
                        timings['cloud_pack_ms']=(time.perf_counter()-pack_started)*1000
                        timings.update(slam_ms=slam_result['tracking_ms'],fusion_ms=(time.perf_counter()-fusion_started)*1000)
                    encode_started=time.perf_counter()
                    ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    timings['jpeg_encode_ms']=(time.perf_counter()-encode_started)*1000
                    if not ok:raise RuntimeError('JPEG encoding failed')
                    completed_at=time.perf_counter()
                    age_ms=(completed_at-frame.captured_at)*1000
                    summary.add(age_ms,completed_at,skipped)
                    state = {"timestamp": elapsed, "sequence": saved, "rgb_path": image_path,
                             'capture_sequence':frame.sequence,
                             "pose": pose_values, "pose_status": "available" if pose_values else "unavailable", "mode": "live", "state": "running",
                             "fps": camera.capture_fps, "skipped_since_previous": skipped,
                             "latency_ms": {**timings, "capture_to_state": age_ms,'input_age_ms':input_age_ms},
                             'capture_receipt_monotonic':frame.captured_at,'timing_summary':summary.report(),
                             'timing_scope':'Capture receipt to packet readiness, including RGB/depth writes and JPEG encoding; excludes sensor buffering and browser',
                             "device": depth.device if depth else "cpu", "depth_kind": "relative_inverse" if depth else None,
                             "image_size_wh": [image.shape[1], image.shape[0]],
                             "model": depth.model_id if depth else None,
                             "limitations": ["No live SLAM or fusion; pose unavailable", "No metric scale"]}
                    if slam_result is not None:
                        state.update(slam_sequence=slam_result['sequence'],slam_timestamp=slam_result['timestamp'],
                            map_snapshot_saved=snapshot_warning is None,map_snapshot_warning=snapshot_warning,
                            pose_kind='online',pose_format='tx ty tz qx qy qz qw; camera-to-world',
                            map_epoch=slam_result.get('map_epoch',0),
                            cloud_semantics='live_sparse_and_local_dense',map_revision=sequence,fusion=fusion_status,
                            limitations=['Experimental online pose; may be revised by SLAM','Global sparse map plus replaceable local dense preview, not accumulated dense reconstruction','Arbitrary units, not meters'])
                        if keyframe_window:state['limitations'][1]='Bounded validated keyframe window; rebuilt with current poses, not complete room reconstruction'
                    states.write(json.dumps(state)+"\n")
                    states.flush()
                    timestamps.writerow([elapsed, sequence, frame.captured_at])
                    publish(queue, packet(state, jpeg.tobytes(),cloud,cloud_count))
                    saved += 1
            (directory/"capture_settings.json").write_text(json.dumps(camera.settings, indent=2), encoding="utf-8")
    except Exception as exc:
        (directory/"error.txt").write_text(str(exc), encoding="utf-8")
        publish(queue, packet({"state": "error", "mode": "live", "error": str(exc)}))
    finally:
        if feeder:feeder.close()
        elif bridge:bridge.close()
        (directory/'timing_summary.json').write_text(json.dumps(summary.report(),indent=2))
        if writer is not None:
            writer.release()
        queue.close()
        queue.join_thread()
