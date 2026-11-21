"""Run the shared depth wrapper on a saved simulated RGB frame, then audit the floor fit."""
import json
import os
from pathlib import Path
import sys
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from perception.depth import DepthEstimator,colorize_depth
from sim.vision import local_grid,velocity_command

root=Path(__file__).resolve().parents[1]
directory=root/"data/simulation/depth_check";directory.mkdir(parents=True,exist_ok=True)
image=cv2.imread(str(root/"data/simulation/current/camera_latest.png"))
if image is None:raise RuntimeError("No simulated camera frame is available")
import torch
torch.set_num_threads(2)
device=os.environ.get("SIM_DEPTH_DEVICE","cuda")
if device not in ("cuda","cpu"):
    raise SystemExit("SIM_DEPTH_DEVICE must be cuda or cpu")
model=DepthEstimator(device=device,local_files_only=True)
prediction=model.predict(image)
cv2.imwrite(str(directory/"rgb_depth.png"),np.hstack((image,colorize_depth(prediction))))
report={"model":model.model_id,"device":model.device,"timings_ms":model.last_timings,"depth_finite":bool(np.isfinite(prediction).all())}
try:
    grid,diagnostic=local_grid(prediction,image)
    command=velocity_command(grid)
    np.savez_compressed(directory/"grid.npz",grid=grid)
    report.update(floor_alignment_valid=True,diagnostic=diagnostic,occupied_cells=int((grid==100).sum()),free_cells=int((grid==0).sum()),command={"linear":command[0],"angular":command[1],"state":command[2]})
except ValueError as exc:report.update(floor_alignment_valid=False,error=str(exc))
(directory/"report.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
