# Positive depth ordering but no supported dense window

Session `1fbb44b27fc94a4daf7afc48883dc708`, strict live initialization, 224x168
depth, 119 outputs, 83 posed outputs. All 119 main depth predictions were saved.
There was no depth-inference failure or accepted dense window.

## Online evidence

The final cached views 0 and 7 have positive training ordering correlations of
0.730 and 0.752, but only 60.4% and 66.1% training depth support, below 70%.
Intermediate views 3, 5, 11 and 12 individually passed at some outputs, but their
identities subsequently disappeared from the active-map snapshot. They were not
dropped because the prediction cache was full. These passes never yielded two
simultaneously accepted views for cross-view validation.

There were 221 candidate-skip events for insufficient shared landmarks/parallax,
not 221 unique rejected images. The current policy anchors candidate geometry to
the newest cached view irrespective of whether its depth fit is accepted.

## Final-map diagnostic

Fresh 224x168 inference using the unchanged `aligned_depth` gates and keyframe-ID
split seeds produced these results on the six retained final-map keyframes:

| Keyframe | Training depth support | Fit |
|---|---:|---|
| 0 | 64.8% | Rejected |
| 7 | 66.1% | Rejected |
| 8 | 78.4% | Accepted |
| 20 | 68.9% | Rejected |
| 21 | 71.6% | Accepted |
| 22 | 70.0% | Accepted |

All six final-map views have positive ordering correlation (0.747–0.912).
Passing fits for views 8/21/22 have held-out mean SLAM disagreement of 8.19%,
12.40% and 13.20%, respectively. These are final optimized estimates, not proof
that these views would have passed at earlier online timestamps.

All newer views pass the shared-landmark/parallax geometry predicate relative to
view 0. None passes it relative to view 7. Thus a newest-cached-only anchor can
block evaluating potentially useful candidates when another cached anchor would
permit them. However, **none of the pairs among the three accepted final views
passes that geometry predicate either**. Removing the selection restriction alone
does not establish sufficient baseline for a supported dense window. The predicate
uses median ray angle and shared landmarks; it is not identical to per-point
cross-view validation, so its failure does not prove every pixel lacks support.

## Next change to evaluate

Consider candidates relative to more than the newest cached anchor, while retaining
the one-new-inference-per-output limit, cache bounds, fit gates and actual
cross-view rejection. Evaluate this as a candidate-selection change, not an accuracy
fix. Compare inference overhead and first-dense/output coverage on timed saved input;
do not infer online improvement from final-map fits alone. Persistent accepted
views with useful baseline remain necessary, and rejected depth should stay rejected.

No mapping/selection policy was changed during this inspection. Evidence:
[final fits and pair predicates](final_fits.json),
[ordering audit](audit/diagnostics.json).
