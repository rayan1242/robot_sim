"""Collect, solve, and inspect checkerboard calibration: python -m perception.calibrate."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .capture import add_camera_arguments, camera_from_args


def detect(image, board):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, board)
    if not found:
        return None
    return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))


def collect(args):
    args.images.mkdir(parents=True, exist_ok=True)
    metadata_path = args.images / "collection.json"
    board = (args.columns, args.rows)
    with camera_from_args(args) as camera:
        sequence = -1
        size = None
        if metadata_path.exists():
            raise ValueError("Collection already exists; use a fresh --images directory to avoid mixing settings")
        while True:
            packet = camera.get_latest(sequence)
            sequence = packet.sequence
            image = packet.image
            size = (image.shape[1], image.shape[0])
            corners = detect(image, board)
            preview = image.copy()
            if corners is not None:
                cv2.drawChessboardCorners(preview, board, corners, True)
            cv2.putText(preview, "S: save detected board | Q: finish", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imshow("Collect calibration", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("s") and corners is not None:
                index = len(list(args.images.glob("frame_*.png")))
                destination = args.images / f"frame_{index:04d}.png"
                if destination.exists() or not cv2.imwrite(str(destination), image):
                    raise RuntimeError(f"Could not save {destination}")
                print(f"Saved {destination}")
        metadata_path.write_text(json.dumps({"board": board, "square_size": args.square_size,
                                             "image_size": size, "camera_settings": camera.settings},
                                            indent=2), encoding="utf-8")


def solve(args):
    board = (args.columns, args.rows)
    metadata_path = args.images / "collection.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    if metadata and (tuple(metadata["board"]) != board or metadata["square_size"] != args.square_size):
        raise ValueError("Board parameters differ from collection metadata")
    object_template = np.zeros((board[0] * board[1], 3), np.float32)
    object_template[:, :2] = np.mgrid[0:board[0], 0:board[1]].T.reshape(-1, 2) * args.square_size
    objects, observations, names = [], [], []
    size = None
    for path in sorted(args.images.glob("*.png")):
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Cannot read {path}")
        current_size = (image.shape[1], image.shape[0])
        if size is not None and size != current_size:
            raise ValueError("Calibration images have mixed resolutions")
        size = current_size
        corners = detect(image, board)
        if corners is None:
            print(f"No checkerboard: {path}")
            continue
        objects.append(object_template.copy())
        observations.append(corners)
        names.append(str(path))
    if len(objects) < 10:
        raise ValueError(f"Only {len(objects)} usable images; need at least 10, aim for 25–40")
    rms, matrix, distortion, rotations, translations = cv2.calibrateCamera(objects, observations, size, None, None)
    errors = []
    for obj, observed, rotation, translation in zip(objects, observations, rotations, translations):
        projected, _ = cv2.projectPoints(obj, rotation, translation, matrix, distortion)
        errors.append(float(np.sqrt(np.mean(np.sum((observed - projected) ** 2, axis=2)))))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.output, camera_matrix=matrix, distortion_coefficients=distortion,
             image_size=np.array(size), board_size=np.array(board), square_size=args.square_size,
             rms=rms, per_image_errors=np.array(errors), image_names=np.array(names),
             collection_metadata=json.dumps(metadata))
    report = {"rms_pixels": rms, "target_met": bool(rms < 0.5), "image_size": size,
              "images": dict(zip(names, errors)),
              "note": "Training reprojection error; also validate on additional views visually"}
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def compare(args):
    with np.load(args.calibration, allow_pickle=False) as data:
        matrix = data["camera_matrix"]
        distortion = data["distortion_coefficients"]
        size = tuple(int(v) for v in data["image_size"])
    with camera_from_args(args) as camera:
        sequence = -1
        maps = None
        while True:
            packet = camera.get_latest(sequence)
            sequence = packet.sequence
            image = packet.image
            if (image.shape[1], image.shape[0]) != size:
                raise ValueError(f"Camera resolution must match calibration: {size}")
            if maps is None:
                adjusted, _ = cv2.getOptimalNewCameraMatrix(matrix, distortion, size, 1, size)
                maps = cv2.initUndistortRectifyMap(matrix, distortion, None, adjusted, size, cv2.CV_32FC1)
            undistorted = cv2.remap(image, *maps, cv2.INTER_LINEAR)
            comparison = np.hstack((image, undistorted))
            cv2.imshow("Raw (left) | Undistorted (right) | S: save | Q: exit", comparison)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("s"):
                args.output.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(args.output), comparison):
                    raise RuntimeError("Could not save comparison")
                np.savez(args.output.with_suffix(".npz"), undistorted_camera_matrix=adjusted,
                         image_size=np.array(size))
                print(f"Saved {args.output} and adjusted intrinsics")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("collect", "solve"):
        command = commands.add_parser(name)
        command.add_argument("--images", type=Path, default=Path("data/calibration_images"))
        command.add_argument("--columns", type=int, default=9, help="Inner corners across")
        command.add_argument("--rows", type=int, default=6, help="Inner corners down")
        command.add_argument("--square-size", type=float, required=True, help="Measured square edge in meters")
        if name == "collect":
            add_camera_arguments(command)
        else:
            command.add_argument("--output", type=Path, default=Path("data/calibration.npz"))
    command = commands.add_parser("compare")
    add_camera_arguments(command)
    command.add_argument("--calibration", type=Path, default=Path("data/calibration.npz"))
    command.add_argument("--output", type=Path, default=Path("docs/calibration_comparison.png"))
    args = parser.parse_args()
    if args.command in ("collect", "solve") and (args.columns < 2 or args.rows < 2 or args.square_size <= 0):
        parser.error("Board dimensions must be >=2 and square size must be positive")
    try:
        {"collect": collect, "solve": solve, "compare": compare}[args.command](args)
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
