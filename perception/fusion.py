"""Align relative inverse depth to a monocular SLAM map (arbitrary scale)."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class DepthAlignment:
    scale: float
    shift: float
    inliers: int
    samples: int

    def depth(self, prediction):
        inverse = self.scale * prediction + self.shift
        result = np.full(inverse.shape, np.nan, dtype=np.float32)
        valid = np.isfinite(inverse) & (inverse > 1e-8)
        result[valid] = 1 / inverse[valid]
        return result


def fit_inverse_depth(predicted_values, sparse_depths, seed=0, relative_threshold=0.15):
    """Robustly fit 1/z = a * network_output + b; caller must split held-out points."""
    x = np.asarray(predicted_values, dtype=float).reshape(-1)
    z = np.asarray(sparse_depths, dtype=float).reshape(-1)
    if x.shape != z.shape:
        raise ValueError("Prediction/depth samples must have equal lengths")
    valid = np.isfinite(x) & np.isfinite(z) & (z > 0)
    x, y = x[valid], 1 / z[valid]
    if len(x) < 10 or np.ptp(x) < 1e-8:
        raise ValueError("Need at least 10 finite, varied inverse-depth correspondences")
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(300):
        i, j = rng.choice(len(x), 2, replace=False)
        if abs(x[i]-x[j]) < 1e-8:
            continue
        scale = (y[i]-y[j])/(x[i]-x[j])
        if scale <= 0:
            continue
        shift = y[i]-scale*x[i]
        error = np.abs(scale*x+shift-y)/y
        mask = error < relative_threshold
        score = (int(mask.sum()), -float(np.median(error[mask])) if mask.any() else -np.inf)
        if best is None or score > best[0]:
            best = (score, mask)
    if best is None or best[1].sum() < max(10, len(x)//2):
        raise ValueError("No positive-scale alignment with sufficient sparse support")
    mask = best[1]
    for _ in range(5):
        # Relative-error weighted least squares prevents nearest points dominating.
        design = np.column_stack((x[mask], np.ones(mask.sum()))) / y[mask, None]
        scale, shift = np.linalg.lstsq(design, np.ones(mask.sum()), rcond=None)[0]
        if scale <= 0:
            raise ValueError("Alignment produced a nonpositive inverse-depth scale")
        updated = np.abs(scale*x+shift-y)/y < relative_threshold
        if updated.sum() < 10:
            raise ValueError("Too few robust depth-alignment inliers")
        if np.array_equal(mask, updated):
            break
        mask = updated
    return DepthAlignment(float(scale), float(shift), int(mask.sum()), len(x))


def project_landmarks(points_world, world_from_camera, matrix, distortion, image_size):
    """Project sparse world points into distorted RGB pixels. Return indices, uv, z."""
    points = np.asarray(points_world, dtype=float).reshape(-1, 3)
    pose = np.asarray(world_from_camera)
    camera_points = (points-pose[:3, 3]) @ pose[:3, :3]
    candidate = np.flatnonzero(camera_points[:, 2] > 1e-6)
    if not len(candidate):
        return candidate, np.empty((0, 2)), np.empty(0)
    uv, _ = cv2.projectPoints(camera_points[candidate], np.zeros(3), np.zeros(3), matrix, distortion)
    uv = uv.reshape(-1, 2)
    width, height = image_size
    keep = np.isfinite(uv).all(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] < width-1) & (uv[:, 1] >= 0) & (uv[:, 1] < height-1)
    return candidate[keep], uv[keep], camera_points[candidate[keep], 2]


def sample_bilinear(image, uv):
    """Sample a scalar image at Nx2 float pixel coordinates."""
    uv = np.asarray(uv, np.float32)
    if not uv.size:
        return np.empty(0, dtype=np.float32)
    return cv2.remap(image.astype(np.float32), uv[:, 0].reshape(-1, 1),
                     uv[:, 1].reshape(-1, 1), cv2.INTER_LINEAR).reshape(-1)


def alignment_support(fit, prediction, training_uv, training_values, training_depths):
    """Training-only acceptance and conservative dense support; no held-out inputs."""
    estimated = fit.depth(np.asarray(training_values))
    z = np.asarray(training_depths)
    inliers = np.isfinite(estimated) & np.isfinite(z) & (z > 0)
    residual = np.full(z.shape, np.inf)
    residual[inliers] = np.abs(estimated[inliers]-z[inliers])/z[inliers]
    inliers &= residual < 0.15
    count = int(inliers.sum())
    fraction = count / max(1, len(z))
    stats = {"training_depth_inliers": count, "training_depth_inlier_fraction": fraction,
             "acceptance_basis": "training correspondences only"}
    from scipy.stats import spearmanr
    finite = np.isfinite(training_values) & np.isfinite(z) & (z > 0)
    correlation = float(spearmanr(np.asarray(training_values)[finite], 1/z[finite]).statistic) if finite.sum() >= 10 else float('nan')
    stats["training_inverse_depth_rank_correlation"] = correlation if np.isfinite(correlation) else None
    if not np.isfinite(correlation) or correlation < 0.3:
        return None, {**stats, "rejection": "Training depth ordering is weak or contradicts sparse geometry (rank correlation <0.3)"}
    if count < 50 or fraction < 0.7:
        return None, {**stats, "rejection": "Need >=50 training depth inliers and >=70% support"}
    hull = cv2.convexHull(np.asarray(training_uv[inliers], np.float32))
    coverage = float(cv2.contourArea(hull)/prediction.size)
    stats["training_hull_image_fraction"] = coverage
    if coverage < 0.05:
        return None, {**stats, "rejection": "Training inlier hull covers <5% of the image"}
    support = np.zeros(prediction.shape, np.uint8)
    cv2.fillConvexPoly(support, np.rint(hull).astype(np.int32), 1)
    low, high = np.percentile(np.asarray(training_values)[inliers], [1, 99])
    mask = support.astype(bool) & np.isfinite(prediction) & (prediction >= low) & (prediction <= high)
    stats.update(prediction_support_min=float(low), prediction_support_max=float(high),
                 dense_supported_pixel_fraction=float(mask.mean()))
    return mask, stats


def multiview_support(points, source_index, views, matrix, distortion,
                      relative_tolerance=0.10, min_other_views=1):
    """Require independent-view depth agreement; occluded points give no evidence.

    Each view is (camera-to-world pose, supported z-depth image). View predictions
    share a model and SLAM geometry, so this is consistency, not ground truth.
    """
    if relative_tolerance <= 0 or min_other_views < 1:
        raise ValueError("Positive tolerance and supporting-view count required")
    points = np.asarray(points).reshape(-1, 3)
    support = np.zeros(len(points), dtype=np.int32)
    conflicts = np.zeros(len(points), dtype=np.int32)
    source_center = views[source_index][0][:3, 3]
    source_rays = points-source_center
    source_norm = np.linalg.norm(source_rays, axis=1)
    for index, (pose, depth) in enumerate(views):
        if index == source_index:
            continue
        ids, uv, z = project_landmarks(points, pose, matrix, distortion, (depth.shape[1], depth.shape[0]))
        if not len(ids):
            continue
        rays = points[ids]-pose[:3, 3]
        norms = np.linalg.norm(rays, axis=1)*source_norm[ids]
        cosine = np.sum(rays*source_rays[ids], axis=1)/np.maximum(norms, 1e-12)
        # A second almost-identical viewpoint is not useful geometric evidence.
        baseline = (norms > 1e-12) & (cosine < np.cos(np.deg2rad(1.0)))
        target = sample_bilinear(depth, uv)
        valid = np.isfinite(target) & (target > 0) & baseline
        error = (z-target)/np.maximum(target, 1e-12)
        agree = valid & (np.abs(error) <= relative_tolerance)
        free_space = valid & (error < -relative_tolerance)
        support[ids[agree]] += 1
        conflicts[ids[free_space]] += 1
    keep = (support >= min_other_views) & (conflicts == 0)
    return keep, {"input_points": len(points), "retained_points": int(keep.sum()),
                  "unsupported_points": int((support < min_other_views).sum()),
                  "free_space_conflict_points": int((conflicts > 0).sum())}


def backproject(depth, bgr, matrix, distortion, world_from_camera, stride=4, max_depth=np.inf):
    """Back-project distorted RGB pixels using undistorted rays, with z-depth."""
    if stride < 1 or depth.shape != bgr.shape[:2]:
        raise ValueError("Positive stride and matching depth/RGB dimensions required")
    v, u = np.mgrid[0:depth.shape[0]:stride, 0:depth.shape[1]:stride]
    z = depth[v, u].reshape(-1)
    pixels = np.column_stack((u.reshape(-1), v.reshape(-1)))
    keep = np.isfinite(z) & (z > 0) & (z <= max_depth)
    pixels, z = pixels[keep], z[keep]
    if not len(z):
        return np.empty((0, 3)), np.empty((0, 3), np.uint8)
    normalized = cv2.undistortPoints(pixels.astype(np.float64).reshape(-1, 1, 2), matrix, distortion).reshape(-1, 2)
    camera_points = np.column_stack((normalized, np.ones(len(z)))) * z[:, None]
    world = camera_points @ world_from_camera[:3, :3].T + world_from_camera[:3, 3]
    rgb = bgr[pixels[:, 1], pixels[:, 0]][:, ::-1]
    return world, rgb


def voxel_downsample(points, colors, voxel_size):
    if voxel_size <= 0:
        raise ValueError("Voxel size must be positive")
    if not len(points):
        return points, colors
    cells = np.floor(points/voxel_size).astype(np.int64)
    _, inverse = np.unique(cells, axis=0, return_inverse=True)
    counts = np.bincount(inverse)
    positions = np.column_stack([np.bincount(inverse, weights=points[:, i])/counts for i in range(3)])
    rgb = np.column_stack([np.bincount(inverse, weights=colors[:, i])/counts for i in range(3)])
    return positions, np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
