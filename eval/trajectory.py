"""Timestamp association and Sim(3) position alignment for TUM trajectories."""
import numpy as np


def associate(estimate, truth, tolerance=0.02):
    """Greedy smallest-time-difference, one-to-one association within tolerance."""
    candidates = []
    for i, timestamp in enumerate(estimate[:, 0]):
        lower = np.searchsorted(truth[:, 0], timestamp-tolerance)
        upper = np.searchsorted(truth[:, 0], timestamp+tolerance, side="right")
        candidates.extend((abs(timestamp-truth[j, 0]), i, j) for j in range(lower, upper))
    used_est, used_truth, pairs = set(), set(), []
    for delta, i, j in sorted(candidates):
        if i not in used_est and j not in used_truth:
            used_est.add(i)
            used_truth.add(j)
            pairs.append((i, j))
    pairs.sort()
    if len(pairs) < 3:
        raise ValueError("Need at least three timestamp-associated poses")
    i, j = np.array(pairs).T
    return estimate[i], truth[j]


def align_similarity(source, target):
    """Umeyama least-squares Sim(3), mapping source positions into target coordinates."""
    center_source, center_target = source.mean(axis=0), target.mean(axis=0)
    x, y = source-center_source, target-center_target
    variance = np.mean(np.sum(x*x, axis=1))
    if variance < 1e-12:
        raise ValueError("Estimated trajectory has no translation; cannot align scale")
    u, singular, vt = np.linalg.svd(y.T @ x / len(x))
    signs = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        signs[-1] = -1
    rotation = (u * signs) @ vt
    scale = float(np.sum(singular * signs) / variance)
    if scale <= 0:
        raise ValueError("Degenerate trajectory alignment")
    translation = center_target-scale * rotation @ center_source
    aligned = scale * source @ rotation.T + translation
    return aligned, scale
