# Camera-only perception: five-minute video script

**Rayyan | Project demonstration | November 2026**

## 0:00-0:40 | Working system

**On screen:** Successful dashboard replay with RGB, depth overlay and point cloud.
Visible label: **Replay of a recorded live session**.

Hi, I'm Rayyan. I built this camera-only perception prototype using one ordinary
USB webcam and CPU inference.

It estimates relative depth, tracks camera motion with visual SLAM, and combines
supported views into a bounded 3D point-cloud window.

What you're seeing is replay of a session that ran live. I also built the local
dashboard, recording system and diagnostics.

My focus became more than producing a point cloud: I wanted to understand when
the geometry is trustworthy and how fresh the output actually is.

## 0:40-1:20 | Pipeline

**On screen:** Architecture diagram from the project report.

The capture thread keeps the latest frame, so slow processing doesn't create an
ever-growing queue of old observations.

SLAM supplies camera poses and sparse landmarks. A pretrained Depth Anything V2
Small model supplies dense relative-depth predictions.

Fusion aligns the depth predictions with the sparse geometry, then requires
support across views before emitting dense points.

The map remains in arbitrary units. Monocular SLAM doesn't independently provide
metric scale, so I don't claim these coordinates are meters.

## 1:20-2:15 | Diagnosing a misleading result

**On screen:** Bed/wall comparison from the spatial investigation: RGB, model
nearness, SLAM nearness and predicted inverse depth.

One of the most useful failures was this recording.

SLAM could track features with low reprojection error, but its estimated geometry
placed the rear wall closer than the foreground bed. The depth model gave the
visually plausible ordering, and fusion rejected the disagreement.

I checked frame timestamps, pose conventions and calibration rather than
immediately changing the depth model.

Fresh checkerboard validation didn't reveal a large calibration mismatch.
Stricter initialization helped one recording, but the improvement didn't repeat
consistently.

That taught me to separate tracking availability from correct geometry, and to
preserve failed recordings instead of treating one successful demo as proof.

## 2:15-3:20 | Controlled improvements

**On screen:** Two-panel controlled-comparison chart.

I then found two keyframe-selection limitations.

New candidates were being compared only against the newest cached view.
Sometimes an older view supplied useful baseline that the newest one didn't.

Also, keeping only the newest four accepted views could discard an older view
that was important for cross-view support.

To isolate these changes, I froze SLAM snapshots and shared identical depth
predictions between policies.

In the first experiment, multiple-anchor selection increased validated dense
coverage from one of 57 snapshots to 27.

In a separate experiment, keeping geometric diversity increased coverage from
29 of 58 snapshots to 38.

The quality checks stayed unchanged. These experiments show improved supported
coverage on those recordings; they don't establish independent mapping accuracy.

## 3:20-4:15 | Final live result

**On screen:** Successful replay, followed by the final session's dense-coverage
and timing chart.

In the final 30-second webcam session, SLAM initialized at about four seconds and
maintained a pose on every processed output afterward.

Validated dense mapping appeared at 4.43 seconds. Seventy-nine of 84 tracked
outputs contained dense points. That's 94 percent of tracked outputs, not
94 percent accuracy.

Timing remains a limitation. Median capture-receipt-to-packet age was
310 milliseconds, and p95 was 687 milliseconds.

That measurement excludes hidden sensor buffering, network transit and physical
display latency. The pipeline processes live input, but I wouldn't describe it
as ready for low-latency robot control.

## 4:15-5:00 | Connection to Efference

**On screen:** Timing chart, then the dashboard.

The connection I see to Efference is the engineering around perception:
observation integrity, freshness, transport overhead and controlled evaluation.

This is a local prototype, not a reproduction of your sensor-to-datacenter
infrastructure. I haven't tested wireless offload, cloud inference or physical
robot task success.

But the project taught me how to isolate failures across capture, geometry, model
output and delivery, and how to distinguish a visual improvement from a measured
one.

The remaining limitations are tail latency, repeatability across scenes and
independent geometry accuracy.

That's the work I wanted to demonstrate: building the system, investigating its
failures, and being precise about what the evidence supports.

## Visual assets and references

- [Successful-session report and timing chart](successful_live_session/diverse_window/report.md)
- [Bed/wall ordering overlay](fusion_diagnostics/latest_live_session/spatial/view_0.png)
- [Controlled-comparison chart](project_report/controlled_comparisons.png)
- [Complete engineering report](project_report.md)
- [Efference systems-validation role](https://efference.ai/careers/systems-test-engineer-end-to-end-validation/)

The timestamps are recording segments, not measured processing timings. Screen
directions and references are production notes; the paragraphs are spoken narration.
