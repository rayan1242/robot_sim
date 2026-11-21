# Phase 2: CPU relative-depth results

Depth Anything V2 Small, CPU fp32, PyTorch 2.2.2+cpu, Windows 11. Each controlled
benchmark used 640x480 camera frames through DirectShow, three warmup inferences,
and 100 measured frames. Network dimensions are rounded to multiples of 14.
Power mode was not recorded, which limits reproducibility.

| Depth image input | Network tensor H x W | Throughput FPS | Median wrapper ms | p95 wrapper ms |
|---|---|---:|---:|---:|
| 320 x 240 | 238 x 322 | 4.50 | 218.6 | 266.6 |
| 480 x 360 | 364 x 476 | 1.57 | 584.0 | 776.1 |
| 640 x 480 | 476 x 644 | 0.69 | 1379.3 | 1706.0 |

All three runs had zero camera read failures. Wrapper time includes model
preprocessing, inference, and postprocessing; explicit input resize time is separate.
Throughput includes resizing. These measurements describe speed, not depth accuracy.
CUDA comparisons were not run because the installed PyTorch build is CPU-only.
Memory comparisons remain unmeasured on CPU.

Source reports: `data/depth_fixed_320_cpu.json`, `depth_fixed_480_cpu.json`,
and `depth_fixed_640_cpu.json`. Earlier reports used camera-negotiated resolutions
and must not be mixed into this controlled comparison.

## Qualitative examples

Saved RGB/depth pairs and raw depth arrays are in `data/depth_examples/`.

| Example filename stem | Visible condition | Observation and limit |
|---|---|---|
| example_1793489490088991100 | Mirror | Depth responds to reflected content; cannot assume it represents the mirror surface. |
| example_1793489503257148900 | Very low light | A coarse shape is predicted despite little visible detail. No ground truth establishes its accuracy. |
| example_1793489586225075600 | Translucent cup | A solid-looking depth shape is predicted. Transparency and surface depth cannot be evaluated from this screenshot alone. |
| example_1793489613035420500 | Moving hand | The RGB hand is blurred. A single screenshot does not establish temporal depth stability or a measured failure. |

The earlier close-object examples are also saved, but their true surface distances
were not measured. A controlled blank-wall example has not been identified. This
gallery is therefore partial, and it should not be described as an accuracy benchmark.

The saved `depth_1793490028618952400.avi` decoded successfully with 22 frames at
640x240. Fixed 10 FPS playback gives a 2.2-second clip, not the actual capture timing.
It is a side-by-side visualization and is unsuitable as raw SLAM footage.

For the CPU preview, 320x240 is the fastest measured configuration. Relative depth
still has no metric scale, and per-frame visualization colors do not establish
consistent distances over time.
