"""Report shared landmarks and estimated ray-angle change without tuning SLAM."""
import argparse
import json
from pathlib import Path

import msgpack
import numpy as np
from perception.keyframes import pair_geometry


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();data=msgpack.unpackb(a.map.read_bytes(),raw=False,strict_map_key=False)
    keys=sorted(data['keyframes'].values(),key=lambda k:k['ts'])
    pairs={str(gap):[pair_geometry(keys[i],keys[i+gap],data['landmarks']) for i in range(len(keys)-gap)] for gap in [1,2,3]}
    summary={gap:{'pairs':len(rows),'median_shared_landmarks':float(np.median([r['shared_landmarks'] for r in rows])) if rows else None,
        'median_pair_angle_deg':float(np.median([r['median_ray_angle_deg'] for r in rows if r['median_ray_angle_deg'] is not None])) if any(r['median_ray_angle_deg'] is not None for r in rows) else None} for gap,rows in pairs.items()}
    report={'keyframes':len(keys),'summary_by_keyframe_gap':summary,'pairs':pairs,
        'note':'Internal estimates from the final optimized map, not measured motion or RGB-area overlap. One degree is a diagnostic reference, not a safety/confidence threshold. No SLAM settings or fusion gates were changed.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2));print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
