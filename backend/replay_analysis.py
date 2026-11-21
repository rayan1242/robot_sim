"""Measured offline-session diagnostics; no inference of unavailable stage timings."""
import csv
import json
from pathlib import Path

import numpy as np


def analysis_report(tracking=None, fusion_report=None):
    result = {"tracking": None, "fusion": None}
    if tracking:
        with Path(tracking).open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        samples = [{"timestamp": float(r["timestamp"]), "available": bool(int(r["pose_available"])),
                    "tracking_ms": float(r["tracking_ms"])} for r in rows]
        if not samples or any(not np.isfinite(s['timestamp']) or not np.isfinite(s['tracking_ms']) for s in samples):
            raise ValueError("Invalid tracking measurements")
        result["tracking"] = {"samples": samples, "available": sum(s['available'] for s in samples),
                              "total": len(samples), "note": "Live pose availability includes initialization; not tracking accuracy or pure loss rate"}
    if fusion_report:
        report = json.loads(Path(fusion_report).read_text())
        result["fusion"] = {key: report.get(key) for key in ["map_points", "fused_keyframes", "heldout_abs_rel_mean",
            "coordinate_units", "evaluation_note", "multiview_policy", "depth_model", "keyframes"]}
        result["fusion"]["note"] = "Agreement with SLAM points, not independent accuracy; per-view errors precede dense filtering"
    return result
