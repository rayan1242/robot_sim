"""Publish a complete map without failing immediately on Windows reader locks."""
from pathlib import Path
import tempfile
import time

import numpy as np


def save_snapshot(path,points,colors,attempts=5):
    path=Path(path)
    if attempts<1:raise ValueError('At least one save attempt required')
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='map_pending_',suffix='.npz',delete=False) as handle:
        pending=Path(handle.name)
        np.savez_compressed(handle,points=points,rgb=colors)
    try:
        for attempt in range(attempts):
            try:
                pending.replace(path)
                return
            except PermissionError:
                if attempt+1==attempts:raise
                time.sleep(.01*(2**attempt))
    finally:
        try:pending.unlink(missing_ok=True)
        except OSError:pass
