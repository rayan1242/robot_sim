"""Depth Anything V2 relative inverse depth; larger values indicate nearer surfaces."""
import time
import os
from pathlib import Path

import cv2
import numpy as np


def prepare_depth_frame(frame, width, height):
    """Fit a camera image into the requested size without stretching (black padding)."""
    if width <= 0 or height <= 0:
        raise ValueError("Depth input dimensions must be positive")
    source_h, source_w = frame.shape[:2]
    if (source_w, source_h) == (width, height):
        return frame
    scale = min(width / source_w, height / source_h)
    resized_w = max(1, min(width, round(source_w * scale)))
    resized_h = max(1, min(height, round(source_h * scale)))
    resized = cv2.resize(frame, (resized_w, resized_h),
                         interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    output = np.zeros((height, width, 3), dtype=frame.dtype)
    left, top = (width-resized_w)//2, (height-resized_h)//2
    output[top:top+resized_h, left:left+resized_w] = resized
    return output


class DepthEstimator:
    def __init__(self, device="auto", precision="fp32", local_files_only=False):
        os.environ.setdefault("USE_TF", "0")
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        self.torch = torch
        self.device = "cuda" if device == "auto" and torch.cuda.is_available() else device
        if self.device == "auto":
            self.device = "cpu"
        if self.device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA requested but unavailable in this PyTorch installation")
        if precision == "fp16" and self.device != "cuda":
            raise ValueError("fp16 is supported only on CUDA; use fp32 on CPU")
        self.precision = precision
        self.dtype = torch.float16 if precision == "fp16" else torch.float32
        self.model_id = "depth-anything/Depth-Anything-V2-Small-hf"
        cache = str(Path(__file__).resolve().parents[1] / ".cache" / "huggingface" / "hub")
        self.processor = AutoImageProcessor.from_pretrained(
            self.model_id, local_files_only=local_files_only, cache_dir=cache, use_fast=False)
        self.model = AutoModelForDepthEstimation.from_pretrained(
            self.model_id, local_files_only=local_files_only, cache_dir=cache).to(device=self.device, dtype=self.dtype).eval()
        self.last_timings = {}
        self.input_shape = None

    def sync(self):
        if self.device == "cuda":
            self.torch.cuda.synchronize()

    def predict(self, frame):
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("Expected a uint8 HxWx3 BGR image")
        self.sync()
        started = time.perf_counter()
        # Explicit dimensions prevent the processor from upscaling every benchmark
        # case to its default size. Network dimensions must be multiples of 14.
        height, width = frame.shape[:2]
        network_h = max(14, round(height / 14) * 14)
        network_w = max(14, round(width / 14) * 14)
        inputs = self.processor(images=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                                size={"height": network_h, "width": network_w},
                                keep_aspect_ratio=False, ensure_multiple_of=14,
                                return_tensors="pt")
        inputs = {key: value.to(device=self.device, dtype=self.dtype) for key, value in inputs.items()}
        self.input_shape = list(inputs["pixel_values"].shape)
        self.sync()
        prepared = time.perf_counter()
        with self.torch.inference_mode():
            predicted = self.model(**inputs).predicted_depth
        self.sync()
        inferred = time.perf_counter()
        with self.torch.inference_mode():
            depth = self.torch.nn.functional.interpolate(
                predicted.unsqueeze(1).float(), size=(height, width),
                mode="bicubic", align_corners=False)[0, 0].cpu().numpy()
        ended = time.perf_counter()
        self.last_timings = {"preprocess_ms": (prepared-started)*1000,
                             "inference_ms": (inferred-prepared)*1000,
                             "postprocess_ms": (ended-inferred)*1000,
                             "total_ms": (ended-started)*1000}
        return depth


def colorize_depth(depth):
    """Per-frame percentile visualization; colors do not represent meters."""
    finite = np.isfinite(depth)
    scaled = np.zeros(depth.shape, np.uint8)
    if finite.any():
        low, high = np.percentile(depth[finite], [2, 98])
        if high > low:
            scaled[finite] = (np.clip((depth[finite]-low)/(high-low), 0, 1)*255).astype(np.uint8)
    return cv2.applyColorMap(scaled, cv2.COLORMAP_INFERNO)
