# Latest live recording: optimized-geometry audit

Session: `818d5311fda343eab93f617e25ea9b71`. This audit uses the saved final
SLAM map and eight uniformly selected retained keyframes, with the same cached
Depth Anything V2 Small model at 224x168. It does not change fusion acceptance.

The live recording produced 120 outputs, 101 with poses (84.2%), and no validated
dense window. Its final snapshot contains 717 sparse points. Capture-receipt to
packet age was 277 ms median and 534 ms p95, with 13/120 misses of 500 ms.

## Findings

- All eight sampled final-map views still disagree in depth ordering: Spearman
  correlation between predicted inverse depth and SLAM inverse depth ranges from
  -0.756 to -0.547. Waiting for final pose optimization did not resolve this.
- Exact saved RGB timestamp matches were available for every sampled keyframe.
- Exported poses agree with poses reconstructed from the map within 9.6e-10;
  saved camera intrinsics agree with calibration within 4.3e-10. These checks
  exclude those specific export/configuration mismatches, not every possible
  projection or calibration error.
- Internal reprojection residuals are 0.95 px median and 3.14 px p95. Low residuals
  demonstrate internal consistency, not physically correct geometry.
- Median estimated maximum landmark ray angle is 4.45 degrees. Restricting the
  diagnostic to landmarks with at least 5 degrees still gives negative ordering
  correlations in all eight views (-0.772 to -0.325). Weak parallax alone does not
  explain away the disagreement in these fixed subsets.

The cause is not yet isolated between model predictions, ambiguous/wrong SLAM
geometry, and remaining image/projection assumptions. A lighter model is not an
established fix. Keep dense rejection enabled.

Next investigate spatially localized correspondences on the saved images, checking
recognizable foreground/background objects against projected sparse depths. Then
compare an alternative depth inference configuration on identical correspondences
and use an independent measured reference before claiming accuracy.

Evidence: [diagnostics](diagnostics.json), [correspondence plots](correspondences.png),
[fixed parallax subsets](geometric_subsets.json). All correlations use final
estimated SLAM geometry; none is independent ground-truth accuracy.

Follow-up: [object-level spatial inspection](spatial/results.md) shows that saved
SLAM reverses the apparent bed/rear-wall ordering, while the model's ordering for
that pair is plausible. This prioritizes calibration/SLAM geometry diagnosis.

[Stricter initialization comparison](initialization_comparison.md): fresh offline
SLAM with a 2-degree initialization threshold yielded positive ordering on all
seven retained keyframes and 3,222 cross-view-filtered dense points. Tracking
coverage decreased; live behavior and repeatability still need validation.
