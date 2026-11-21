"""Experimental geometry-only selection; never uses held-out depth errors."""
import numpy as np
from scipy.spatial.transform import Rotation


def pair_geometry(first,second,landmarks):
    ids=[set(i for i in k['lm_ids'] if str(i) in landmarks) for k in [first,second]]
    shared=ids[0]&ids[1]
    centers=[-Rotation.from_quat(k['rot_cw']).as_matrix().T@np.asarray(k['trans_cw']) for k in [first,second]]
    angles=[]
    for identifier in shared:
        point=np.asarray(landmarks[str(identifier)]['pos_w']);u,v=point-centers[0],point-centers[1]
        norm=np.linalg.norm(u)*np.linalg.norm(v)
        if norm>1e-12:angles.append(float(np.degrees(np.arccos(np.clip(u@v/norm,-1,1)))))
    return {'first_timestamp':first['ts'],'second_timestamp':second['ts'],'shared_landmarks':len(shared),
        'shared_fraction_of_smaller_view':len(shared)/max(1,min(len(ids[0]),len(ids[1]))),
        'median_ray_angle_deg':float(np.median(angles)) if angles else None,
        'fraction_shared_points_below_one_degree':float(np.mean(np.asarray(angles)<1)) if angles else None}


def select_keyframes(keys,landmarks,sharpness,min_shared=70,min_angle_deg=1.,min_sharpness=50.):
    if min_shared<1 or min_angle_deg<=0 or min_sharpness<0:raise ValueError('Invalid selection policy')
    selected=[];decisions=[]
    for key in sorted(keys,key=lambda k:k['ts']):
        row={'timestamp':key['ts'],'sharpness_laplacian_variance':sharpness[key['ts']]}
        if not np.isfinite(sharpness[key['ts']]) or sharpness[key['ts']]<min_sharpness:
            row['status']='rejected_image_quality'
        elif len(set(i for i in key['lm_ids'] if str(i) in landmarks))<min_shared:
            row['status']='rejected_observation_count'
        elif not selected:
            selected.append(key);row['status']='seed_needs_cross_view_support'
        else:
            geometry=pair_geometry(selected[-1],key,landmarks);row['geometry']=geometry
            angle=geometry['median_ray_angle_deg']
            if geometry['shared_landmarks']>=min_shared and angle is not None and angle>=min_angle_deg:
                selected.append(key);row['status']='selected'
            else:row['status']='insufficient_shared_baseline'
        decisions.append(row)
    return selected,decisions
