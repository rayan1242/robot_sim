# Phase 4: common-timestamp comparison

Common poses: 795. Both systems aligned independently with Sim(3).

| System | ATE RMSE (m) | Median (m) | p95 (m) | Output poses |
|---|---:|---:|---:|---:|
| mini_vo | 0.1678 | 0.1317 | 0.2873 | 798 |
| stella_vslam | 0.0106 | 0.0079 | 0.0195 | 797 |

Mini VO holds poses on failed steps; SLAM can omit initialization/lost poses.
Comparison uses only shared ground-truth associations; report coverage alongside error.
These are scale-aligned positional errors, not recovered metric scale or orientation errors.
Processing times span different implementations/environments and are not a controlled speed comparison.
