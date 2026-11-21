# Controlled desk scan: 1793510528100184300

Processed all 300 raw frames with the existing webcam calibration and baseline
stella configuration. No previous maps or recordings were overwritten.

| Run | Inputs | Available poses | Final keyframes | Final landmarks |
|---|---:|---:|---:|---:|
| Original | 300 | 0 | 0 | 0 |
| Luminance-CLAHE trial | 300 | 0 | 0 | 0 |

Both runs failed to initialize a valid map, so fusion was not attempted. This is
a SLAM initialization failure before fusion, not a new depth-alignment failure.

The median per-frame grayscale median is **1/255**; the median fraction of pixels
below 30/255 is **75.5%**. Sampled frames show a dim desk, mouse, laptop and screen.
ORB detector counts increased from a median 285.5 to 621.5 with luminance CLAHE,
but more detected features did not establish valid geometry. These standalone ORB
counts are not stella's exact extractor outputs or proof of usable matches.
Darkness is an observed problem, not an isolated explanation for failed initialization;
viewpoint change, planar content and changing screen content can also contribute.

The trial kept resolution, timestamps, calibration and SLAM settings unchanged.
The existing configuration nominal FPS is 15.599; actual receipt times are supplied
to SLAM. This is not a newly tuned profile or controlled physical-motion experiment.

Artifacts:

- Original run: `data/slam_webcam_1793510528100184300/`.
- Contrast input and photometric summary: `data/experiments/contrast_1793510528100184300/`.
- Contrast SLAM run: `data/slam_webcam_1793510528100184300_contrast/`.
- Source-frame strip: `data/controlled_scan_frames.jpg`.

## Correct the preview before recording again

Capture has historically requested manual exposure even without an explicit
manual exposure value. Its contribution to this clip's darkness is unverified.
`--auto-exposure` now explicitly requests auto exposure without changing the
default calibration/capture behavior. It cannot be combined with `--exposure`.
Driver acceptance/readback are recorded, but acceptance does not prove hardware
behavior. Automatic exposure can lengthen exposures and increase blur; illuminate
the scene sufficiently and verify the preview before starting another scan.

```powershell
python cam_live.py --backend dshow --width 640 --height 480 --auto-exposure
```

Use a well-lit arrangement of stationary textured objects (books/boxes), rather
than relying on the laptop display for texture. Confirm visible surface details
in the preview before another slow sideways scan. No new recording is required
until the preview looks suitable.
