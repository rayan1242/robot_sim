"""Educational two-view monocular VO. Unit-length steps do not recover motion scale."""
import cv2
import numpy as np


FR1_MATRIX = np.array([[517.3, 0, 318.6], [0, 516.5, 255.3], [0, 0, 1]], dtype=float)
FR1_DISTORTION = np.array([0.2624, -0.9531, -0.0054, 0.0026, 1.1633])


def recover_motion(previous, current, matrix, distortion, min_inliers=20):
    """Return previous-camera -> current-camera R,t, with normalized translation."""
    if len(previous) < max(8, min_inliers):
        return None
    p = cv2.undistortPoints(np.asarray(previous, np.float32).reshape(-1, 1, 2), matrix, distortion)
    q = cv2.undistortPoints(np.asarray(current, np.float32).reshape(-1, 1, 2), matrix, distortion)
    essential, mask = cv2.findEssentialMat(p, q, np.eye(3), method=cv2.RANSAC,
                                          prob=0.999, threshold=1.0 / min(matrix[0, 0], matrix[1, 1]))
    if essential is None or mask is None:
        return None
    best = None
    for candidate in np.vsplit(essential, essential.shape[0] // 3):
        count, rotation, translation, valid = cv2.recoverPose(candidate, p, q, np.eye(3), mask=mask.copy())
        if count >= min_inliers and (best is None or count > best[2]):
            best = (rotation, translation.reshape(3), count)
    return best


def compose_camera_pose(world_from_previous, rotation, translation):
    """Invert recoverPose's coordinate transform before chaining camera-to-world poses."""
    previous_from_current = np.eye(4)
    previous_from_current[:3, :3] = rotation.T
    previous_from_current[:3, 3] = -rotation.T @ translation
    return world_from_previous @ previous_from_current


class VisualOdometry:
    def __init__(self, matrix=FR1_MATRIX, distortion=FR1_DISTORTION, features=2500,
                 ratio=0.75, min_inliers=20):
        self.matrix, self.distortion = matrix.copy(), distortion.copy()
        self.detector = cv2.ORB_create(nfeatures=features)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.ratio, self.min_inliers = ratio, min_inliers
        self.previous = None
        self.pose = np.eye(4)

    def update(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        keypoints, descriptors = self.detector.detectAndCompute(gray, None)
        status = {"status": "initializing" if self.previous is None else "lost", "matches": 0, "inliers": 0}
        if self.previous is not None and descriptors is not None:
            old_keys, old_descriptors = self.previous
            if old_descriptors is not None and len(descriptors) >= 2:
                pairs = self.matcher.knnMatch(old_descriptors, descriptors, k=2)
                good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < self.ratio * pair[1].distance]
                # Keep each current keypoint once, choosing its strongest match.
                unique = {}
                for match in sorted(good, key=lambda m: m.distance):
                    unique.setdefault(match.trainIdx, match)
                good = list(unique.values())
                status["matches"] = len(good)
                if len(good) >= self.min_inliers:
                    p = np.array([old_keys[m.queryIdx].pt for m in good])
                    q = np.array([keypoints[m.trainIdx].pt for m in good])
                    if np.median(np.linalg.norm(p-q, axis=1)) < 0.5:
                        status["status"] = "low_motion"
                    else:
                        motion = recover_motion(p, q, self.matrix, self.distortion, self.min_inliers)
                        if motion is not None:
                            rotation, translation, count = motion
                            self.pose = compose_camera_pose(self.pose, rotation, translation)
                            status.update(status="tracked", inliers=count)
        # On failure, hold the pose and reset the pairwise reference to this image.
        self.previous = (keypoints, descriptors)
        return self.pose.copy(), status
