import csv
import io
import json
from pathlib import Path
from queue import Queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.import_session import import_session
from backend.store import SessionStore
from backend.worker import camera_worker, publish
from backend.protocol import packet
from perception.capture import FramePacket


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dataset = self.root/"dataset"
        self.dataset.mkdir()
        index = []
        for i in range(4):
            cv2.imwrite(str(self.dataset/f"{i}.png"), np.full((48, 64, 3), i*50, np.uint8))
            index.append(f"{i*0.05:.3f} {i}.png")
        (self.dataset/"rgb.txt").write_text("\n".join(index))
        self.trajectory = self.root/"poses.txt"
        np.savetxt(self.trajectory, [[i*0.05, i, 0, 0, 0, 0, 0, 1] for i in range(4)])
        self.cloud = self.root/"cloud.npz"
        np.savez(self.cloud, points=np.ones((10, 3)), rgb=np.full((10, 3), 255, np.uint8))
        self.sessions = self.root/"sessions"

    def tearDown(self):
        self.temp.cleanup()

    def imported(self):
        return import_session(SessionStore(self.sessions), self.dataset, self.trajectory, self.cloud)

    def test_completed_session_does_not_resample_live_send_age(self):
        app=create_app(self.sessions)
        with TestClient(app) as client:
            with client.websocket_connect('/ws/live') as socket:
                socket.receive_json()
                runtime=app.state.runtime
                for state in ['running','completed']:
                    with runtime.lock:
                        runtime.latest=packet({'mode':'live','state':state,'capture_receipt_monotonic':time.perf_counter()-1})
                        runtime.revision+=1
                    header=socket.receive_json()
                    self.assertEqual('capture_receipt_to_server_send_ms' in header,state=='running')

    def test_live_slam_requires_calibrated_size_and_enables_depth(self):
        app=create_app(self.sessions)
        with TestClient(app) as client:
            self.assertEqual(client.post('/sessions/start',json={'slam':True,'width':320,'height':240}).status_code,422)
            with patch.object(app.state.runtime,'start') as start:
                response=client.post('/sessions/start',json={'slam':True,'depth':False,'width':640,'height':480})
                self.assertEqual(response.status_code,201)
                options=start.call_args.args[2]
                self.assertTrue(options['depth'])
                self.assertTrue(options['slam'])
            with patch.object(app.state.runtime,'start') as start:
                response=client.post('/sessions/start',json={'keyframe_map':True,'slam':False,'depth':False})
                self.assertEqual(response.status_code,201)
                options=start.call_args.args[2]
                self.assertTrue(options['slam'] and options['depth'] and options['keyframe_map'])

    def test_strict_server_profile_reaches_worker_and_saved_metadata(self):
        with patch.dict('os.environ',{'ROBOT_SLAM_INITIALIZATION':'strict'}):
            app=create_app(self.sessions)
        with TestClient(app) as client:
            self.assertEqual(client.get('/health').json()['slam_initialization_profile'],'strict')
            with patch.object(app.state.runtime,'start') as start:
                response=client.post('/sessions/start',json={'keyframe_map':True})
                self.assertEqual(response.status_code,201)
                options=start.call_args.args[2]
                self.assertEqual(options['slam_initialization_profile'],'strict')
                self.assertEqual(Path(options['slam_config']).name,'webcam_640_mono_strict.yaml')
                self.assertEqual(response.json()['metadata']['options']['slam_config'],options['slam_config'])

    def test_invalid_initialization_profile_fails_before_server_start(self):
        with patch.dict('os.environ',{'ROBOT_SLAM_INITIALIZATION':'unknown'}):
            with self.assertRaisesRegex(ValueError,'ROBOT_SLAM_INITIALIZATION'):
                create_app(self.sessions)

    def test_replay_analysis_preserves_tracking_and_fusion_measurements(self):
        tracking=self.root/'tracking.csv'
        tracking.write_text('timestamp,pose_available,tracking_ms\n0,0,4\n0.05,1,8\n')
        report=self.root/'fusion.json'
        report.write_text(json.dumps({'map_points':10,'fused_keyframes':1,'heldout_abs_rel_mean':0.07,'keyframes':[]}))
        session=import_session(SessionStore(self.sessions),self.dataset,self.trajectory,self.cloud,
                               tracking=tracking,fusion_report=report)
        states=[json.loads(s) for s in (self.sessions/session['id']/'states.jsonl').read_text().splitlines()]
        self.assertFalse(states[0]['tracking_available'])
        self.assertEqual(states[1]['offline_slam_ms'],8)
        self.assertIsNone(states[1]['latency_ms'])
        with TestClient(create_app(self.sessions)) as client:
            result=client.get(f"/sessions/{session['id']}/analysis").json()
            self.assertEqual(result['tracking']['available'],1)
            self.assertEqual(result['tracking']['total'],2)
            self.assertEqual(result['fusion']['heldout_abs_rel_mean'],0.07)

    def test_import_depth_is_synchronized_and_not_reported_as_live_latency(self):
        class FakeDepth:
            model_id='test-model';device='cpu';last_timings={'total_ms':12.0}
            def predict(self,image):return image[:,:,0].astype(np.float32)
        with patch('perception.depth.DepthEstimator',return_value=FakeDepth()):
            session=import_session(SessionStore(self.sessions),self.dataset,with_depth=True)
        root=self.sessions/session['id']
        states=[json.loads(s) for s in (root/'states.jsonl').read_text().splitlines()]
        self.assertIsNone(states[2]['latency_ms'])
        self.assertEqual(states[2]['offline_depth_ms']['total_ms'],12)
        self.assertEqual(states[2]['depth_kind'],'relative_inverse')
        np.testing.assert_allclose(np.load(root/'depth_000002.npy'),100)

    def test_import_download_and_delete_are_self_contained(self):
        session = self.imported()
        with TestClient(create_app(self.sessions)) as client:
            self.assertEqual(len(client.get("/sessions").json()), 1)
            response = client.get(f"/sessions/{session['id']}/download")
            self.assertEqual(response.status_code, 200)
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                self.assertIn("rgb/000000.png", archive.namelist())
                self.assertIn("map.npz", archive.namelist())
                self.assertIn("poses.txt", archive.namelist())
                self.assertIn("session.json", archive.namelist())
            self.assertEqual(client.get("/sessions/not-a-valid-id").status_code, 404)
            self.assertEqual(client.delete(f"/sessions/{session['id']}").status_code, 200)
            self.assertEqual(client.get("/sessions").json(), [])
        self.assertTrue(self.dataset.exists())

    def test_dashboard_and_session_visual_artifacts(self):
        session = self.imported()
        directory = self.sessions/session["id"]
        np.save(directory/"depth_000000.npy", np.arange(48*64, dtype=np.float32).reshape(48,64))
        with TestClient(create_app(self.sessions)) as client:
            self.assertIn("Spatial workspace", client.get("/").text)
            self.assertIn("javascript", client.get("/app.js").headers["content-type"])
            self.assertEqual(client.get("/vendor/three.core.js").status_code, 200)
            prefix = f"/sessions/{session['id']}"
            self.assertEqual(client.get(prefix+"/preview").headers["content-type"], "image/png")
            cloud = client.get(prefix+"/snapshot")
            self.assertEqual(len(cloud.content), int(cloud.headers["x-point-count"])*24)
            depth = client.get(prefix+"/depth/0")
            self.assertEqual(depth.status_code, 200)
            self.assertEqual(cv2.imdecode(np.frombuffer(depth.content,np.uint8),cv2.IMREAD_COLOR).shape[:2], (48,64))
            self.assertEqual(client.get(prefix+"/depth/-1").status_code, 404)

    def test_real_replay_process_websocket_binary_and_completion(self):
        session = self.imported()
        with TestClient(create_app(self.sessions)) as client:
            with client.websocket_connect("/ws/live") as socket:
                self.assertEqual(socket.receive_json()["state"], "idle")
                self.assertEqual(client.post(f"/sessions/{session['id']}/replay", json={"speed": 0.5}).status_code, 200)
                self.assertEqual(client.post(f"/sessions/{session['id']}/replay", json={}).status_code, 409)
                images = 0
                for _ in range(15):
                    state = socket.receive_json()
                    if state["rgb_bytes"]:
                        jpeg = socket.receive_bytes()
                        self.assertEqual(len(jpeg), state["rgb_bytes"])
                        self.assertIsNotNone(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR))
                        images += 1
                    if state["cloud_bytes"]:
                        cloud = socket.receive_bytes()
                        self.assertEqual(len(cloud), state["cloud_point_count"]*6*4)
                        self.assertEqual(state["cloud_semantics"], "final_static_snapshot")
                    if state["state"] == "completed":
                        break
                else:
                    self.fail("Replay did not complete")
                self.assertGreater(images, 0)
                self.assertEqual(state["mode"], "replay")
                self.assertEqual(state["pose_status"], "available")
            self.assertEqual(client.get(f"/sessions/{session['id']}").json()["status"], "ready")

    def test_latest_state_queue_discards_backlog(self):
        queue = Queue(maxsize=1)
        for i in range(100):
            publish(queue, i)
        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(queue.get(), 99)

    def test_active_replay_stop_conflicts_and_recovery(self):
        session = self.imported()
        with TestClient(create_app(self.sessions)) as client:
            identifier = session["id"]
            self.assertEqual(client.post(f"/sessions/{identifier}/replay", json={"speed": 0.1}).status_code, 200)
            self.assertEqual(client.delete(f"/sessions/{identifier}").status_code, 409)
            self.assertEqual(client.get(f"/sessions/{identifier}/download").status_code, 409)
            self.assertEqual(client.post(f"/sessions/{identifier}/stop").status_code, 200)
            self.assertEqual(client.get(f"/sessions/{identifier}").json()["status"], "ready")
            self.assertEqual(client.post(f"/sessions/{identifier}/stop").status_code, 409)

    def test_missing_replay_frame_marks_error(self):
        session = self.imported()
        (self.sessions/session["id"]/"rgb/000000.png").unlink()
        with TestClient(create_app(self.sessions)) as client:
            client.post(f"/sessions/{session['id']}/replay", json={})
            deadline = time.perf_counter()+8
            while time.perf_counter() < deadline:
                if client.get(f"/sessions/{session['id']}").json()["status"] == "error":
                    break
                time.sleep(0.05)
            else:
                self.fail("Replay error was not persisted")

    def test_import_rejects_path_traversal(self):
        (self.dataset/"rgb.txt").write_text("0 ../outside.png\n")
        with self.assertRaisesRegex(ValueError, "escapes"):
            import_session(SessionStore(self.sessions), self.dataset)

    def test_recording_worker_saves_raw_video_and_timing_without_camera(self):
        class FakeCamera:
            settings = {"backend": "fake"}
            capture_fps = 100
            def __init__(self, **kwargs):
                self.sequence = 0
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def get_latest(self, sequence):
                time.sleep(0.01)
                frame = FramePacket(np.zeros((48,64,3), np.uint8), self.sequence, time.perf_counter())
                self.sequence += 1
                return frame
        class LocalQueue(Queue):
            def close(self):
                pass
            def join_thread(self):
                pass
        class FakeDepth:
            device = "cpu"
            model_id = "test-relative-depth"
            last_timings = {"inference_ms": 1.0}
            def __init__(self, **kwargs):
                pass
            def predict(self, image):
                return np.ones(image.shape[:2], np.float32)
        output = self.root/"recorded"
        output.mkdir()
        options = {"depth": True, "device": "cpu", "camera": 0, "width": 64, "height": 48,
                   "fps": 15, "backend": "dshow", "duration": 0.3}
        with patch("perception.capture.CameraCapture", FakeCamera), patch("perception.depth.DepthEstimator", FakeDepth):
            camera_worker(output, options, LocalQueue(maxsize=1), threading.Event())
        self.assertFalse((output/"error.txt").exists())
        states = [json.loads(line) for line in (output/"states.jsonl").read_text().splitlines()]
        self.assertGreater(len(states), 1)
        self.assertIsNone(states[0]["pose"])
        self.assertEqual(states[0]["depth_kind"], "relative_inverse")
        self.assertEqual(len(list(output.glob("depth_*.npy"))), len(states))
        self.assertTrue((output/"raw.avi").stat().st_size > 0)
        self.assertEqual(len(list((output/"rgb").glob("*.png"))), len(states))
        report=json.loads((output/'timing_summary.json').read_text())
        self.assertEqual(report['capture_receipt_to_packet']['samples'],len(states))
        self.assertIn('timing_summary',states[-1])
        self.assertGreaterEqual(states[-1]['capture_receipt_monotonic'],states[0]['capture_receipt_monotonic'])


if __name__ == "__main__":
    unittest.main()
