"""Create an auditable report from saved live-session measurements."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from backend.store import SessionStore
from perception.timing import distribution


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',default='79c2df1975674ee6bfce9c3f2bad374f')
    p.add_argument('--root',type=Path,default=Path('data/sessions'))
    p.add_argument('--output',type=Path,default=Path('docs/successful_live_session'))
    a=p.parse_args();store=SessionStore(a.root);session=store.get(a.session);directory=store.path(a.session)
    states=[json.loads(s) for s in (directory/'states.jsonl').read_text().splitlines()]
    if not states:raise ValueError('No saved live outputs')
    posed=[s for s in states if s.get('pose') is not None]
    dense=[s for s in states if s.get('fusion',{}).get('state')=='local_dense_preview']
    stages=sorted({key for s in states for key in s.get('latency_ms',{})})
    timings={key:distribution([s['latency_ms'][key] for s in states if isinstance(s.get('latency_ms',{}).get(key),(int,float))]) for key in stages}
    with np.load(directory/'map.npz',allow_pickle=False) as cloud:point_count=len(cloud['points'])
    result={'session_id':a.session,'session':session,'processed_outputs':len(states),
        'outputs_with_pose':len(posed),'outputs_with_dense_preview':len(dense),
        'first_output_pose_timestamp':posed[0]['timestamp'] if posed else None,
        'output_duration_seconds':states[-1]['timestamp']-states[0]['timestamp'],
        'fusion_rejections':dict(Counter(s.get('fusion',{}).get('reason') for s in states if s.get('fusion',{}).get('state')!='local_dense_preview')),
        'final_map_points':point_count,'final_fusion_state':states[-1].get('fusion'),
        'timestamp_pairs_match':all(s.get('slam_sequence')==s.get('capture_sequence') and abs(s.get('slam_timestamp',-1)-s['timestamp'])<1e-7 for s in states),
        'timing':states[-1].get('timing_summary'),'stage_distributions':timings,
        'accepted_view_heldout_means':distribution([100*s['fusion']['heldout_abs_rel_mean'] for s in dense if s['fusion'].get('heldout_abs_rel_mean') is not None]),
        'limitations':['Pose fraction refers to processed outputs, not all captured frames or independent pose accuracy',
            'Dense preview fraction measures acceptance, not geometric correctness',
            'Accepted-view heldout mean distribution is percent, not milliseconds, and is not independent ground truth',
            'Stage medians do not add to total median; timings overlap where stated',
            'Only the final map is stored; historical point counts cannot be reconstructed from this session']}
    quality=result['accepted_view_heldout_means']
    quality.update({key.replace('_ms','_percent'):quality.pop(key) for key in list(quality) if key.endswith('_ms')})
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'measurements.json').write_text(json.dumps(result,indent=2))
    rows=['| Stage | Samples | p50 (ms) | p95 (ms) |','|---|---:|---:|---:|']
    for key,r in timings.items():
        median='—' if r['p50_ms'] is None else f"{r['p50_ms']:.2f}"
        tail='—' if r['p95_ms'] is None else f"{r['p95_ms']:.2f}"
        rows.append(f"| {key} | {r['samples']} | {median} | {tail} |")
    text=f'''# Successful physical-webcam live session

Session: `{a.session}`. Source measurements and metadata are preserved in
[measurements.json](measurements.json). The source recording is unchanged.

## Outcome

- {len(states)} processed outputs; {len(posed)} had online poses ({100*len(posed)/len(states):.1f}% of outputs).
- {len(dense)} outputs included an accepted local dense preview ({100*len(dense)/len(states):.1f}%).
- {point_count} points in the final map, which was sparse-only.
- Exact capture/SLAM frame and timestamp pairing: {result['timestamp_pairs_match']}.
- The full historical dense map was not accumulated or saved.

The final-frame warning does not mean dense fusion never worked. Earlier frames
passed the checks. Rejection counts and accepted-view disagreement are in the JSON.
Acceptance is not proof of accuracy; depth agreement is against estimated SLAM.

## Recorded timing

'''+ '\n'.join(rows)+'''

`input_age_ms` is age on entry to the depth worker, including SLAM handoff and
latest-result waiting. `fusion_ms` also includes snapshot saving and cloud packing.
`total_ms` is depth-model preprocessing, inference and postprocessing only.
Capture-to-state ends at JPEG/packet readiness, excluding sensor buffering,
network, browser display and state serialization. Stage medians are not additive.

## Interpretation and next work

The run establishes a working live sparse-mapping baseline and intermittent
local dense previews. It does not establish a reliable full-room reconstruction.
The saved data attributes much of frame age to stages before depth processing;
the old trace cannot isolate file transfer, result waiting and SLAM execution.

Next changes add that instrumentation and test lossless raw BGR transfer to WSL
instead of reading a shared PNG on the critical path. Both paths keep exact
timestamps, and archive original frames for audit. No quality thresholds are
relaxed. Dense rejection diagnostics are retained for both accepted and rejected
frames. The UI must distinguish sparse-only maps and stop sampling send age on
completed sessions.
'''
    (a.output/'report.md').write_text(text,encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True)
    timestamps=[s['timestamp'] for s in states]
    for key,label in [('capture_to_state','Receipt to packet'),('input_age_ms','Age before depth'),('total_ms','Depth model total')]:
        axes[0].plot(timestamps,[s['latency_ms'].get(key,np.nan) for s in states],label=label)
    axes[0].axhline(500,color='gray',linestyle='--',label='Provisional 500 ms budget')
    axes[0].set(ylabel='Time (ms)',title='Successful physical-webcam session: measured software timing');axes[0].legend(fontsize=8)
    modes=[0 if s.get('pose') is None else 2 if s.get('fusion',{}).get('state')=='local_dense_preview' else 1 for s in states]
    axes[1].scatter(timestamps,modes,s=12);axes[1].set(xlabel='Capture-relative time (seconds)',ylabel='Output mode',yticks=[0,1,2],yticklabels=['No pose','Sparse only','Dense preview'])
    fig.tight_layout();fig.savefig(a.output/'session_timing.png',dpi=160);plt.close(fig)
    print(json.dumps({k:result[k] for k in ['processed_outputs','outputs_with_pose','outputs_with_dense_preview','final_map_points','timestamp_pairs_match']},indent=2))


if __name__=='__main__':main()
