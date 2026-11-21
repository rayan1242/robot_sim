# Why dense mapping arrived at the end

Read-only inspection of all 122 saved outputs from session
`9086c570212e41899113fc580f536605`. Per-output evidence is in
[acceptance_timeline.json](acceptance_timeline.json).

Dense mapping requires two simultaneously accepted, geometrically useful views.
The first accepted view was available at 11.61 seconds, immediately after SLAM
initialized. Until 29.26 seconds, no processed output had two accepted views.
The cross-view validator therefore had insufficient supported views, rather than
rejecting an otherwise available valid pair.

Most rejected cached views had enough training points but failed the unchanged
70% training depth-support gate. Examples: view 2 at 12.01 s had 50 inliers but
66.7% support; view 6 at 14.56 s had 144 inliers but 67.3% support. View 9 at
17.58 s was close to the threshold (69.9%) but still correctly rejected.

Accepted views also changed: at 15.65 s only view 7 passed; at 18.72 s only view
10 passed; at 19.66 s only view 11 passed. View 0's fit itself oscillated across
the 70% boundary as SLAM geometry changed. A pass at one output is not permission
to reuse old depth against subsequently rejected geometry.

Cached-keyframe reports generally contained only the anchor and one newer view.
Newer IDs disappear as subsequent candidates arrive, despite the configured cache
limit of eight. The implementation removes cached predictions when their identities
are absent from the current newest-12 keyframe snapshot. Saved states do not
contain that full snapshot, so they cannot distinguish actual SLAM keyframe culling
from omission by the snapshot limit. Do not call this a proven cache-eviction bug.
Nor should removed keyframes be retained with stale poses merely to increase points.

At 29.26 s, views 0 and 20 simultaneously passed (72.5% and 72.0% support).
Cross-view checks then retained 2,321 dense points. Thus both per-view fit stability
and availability of suitable persistent keyframes matter here.

## Next implementation target

Add explicit metadata for candidate selection and cached-keyframe removal reasons,
including whether a keyframe was culled or merely omitted from the limited snapshot.
Then test selecting stable surviving keyframes with sufficient shared landmarks and
parallax. Keep depth acceptance and cross-view checks unchanged. Evaluate earlier
first-dense time, dense-output coverage, pose coverage and additional inference cost
on identical saved input. Current logs cannot reliably simulate historical map
snapshots after the fact; a final optimized map is not an online replay of decisions.

## Implemented follow-up instrumentation

The live runner now sends identities of all keyframes in its active-map snapshot
alongside the limited detailed metadata. Fusion records `keyframe_removals`:
omitted metadata, absent active-map identity, cache capacity or map-epoch change.
Absence from a snapshot is not definitive evidence of a particular culling event.
`candidate_decisions` records insufficient landmarks, overlap/parallax, missing
archived images, sharpness rejection and newly cached predictions. Existing depth
fit reasons remain in `per_keyframe`. No selection or acceptance thresholds changed.

Seven keyframe-window unit tests passed, including distinct omission/absence cases.
The WSL runner was rebuilt. New recording workers load this instrumentation;
existing recordings cannot retroactively recover these missing decisions.
