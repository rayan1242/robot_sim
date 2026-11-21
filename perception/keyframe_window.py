"""Bounded, rebuilt dense window using current keyframe poses and landmark depths."""
from collections import OrderedDict
import time

import cv2
import numpy as np

from .fusion import backproject,multiview_support,voxel_downsample
from .live_slam import aligned_depth


def identity(key):return int(key['id']),round(float(key['timestamp']),9)


class ActiveKeyframeWindow:
    def __init__(self,window_size=4,cache_size=8,min_shared=70,min_angle=1.,min_sharpness=50.,selection_policy='all_cached',window_policy='diverse'):
        if window_size<2 or cache_size<window_size:raise ValueError('Need at least two views and sufficient cache capacity')
        if selection_policy not in ('newest','all_cached'):raise ValueError('Unknown keyframe selection policy')
        self.selection_policy=selection_policy
        if window_policy not in ('newest','diverse'):raise ValueError('Unknown active window policy')
        self.window_policy=window_policy
        self.window_size=window_size;self.cache_size=cache_size;self.min_shared=min_shared
        self.min_angle=min_angle;self.min_sharpness=min_sharpness
        self.items=OrderedDict();self.bad_images=OrderedDict();self.epoch=None

    def geometry_ok(self,anchor,key,landmarks):
        return self.geometry_score(anchor,key,landmarks)>0

    def geometry_score(self,anchor,key,landmarks):
        shared=list(set(anchor['landmark_ids'])&set(key['landmark_ids'])&set(landmarks))
        if len(shared)<self.min_shared:return 0.
        points=np.array([landmarks[i] for i in shared]);a=np.asarray(anchor['pose']).reshape(4,4);b=np.asarray(key['pose']).reshape(4,4)
        u=points-a[:3,3];v=points-b[:3,3];norm=np.linalg.norm(u,axis=1)*np.linalg.norm(v,axis=1)
        valid=norm>1e-12
        if not valid.any():return 0.
        angles=np.degrees(np.arccos(np.clip(np.sum(u[valid]*v[valid],axis=1)/norm[valid],-1,1)))
        angle=float(np.median(angles))
        return len(shared)*min(angle,5.) if angle>=self.min_angle else 0.

    def select_window(self,accepted,landmarks):
        if self.window_policy=='newest' or len(accepted)<=self.window_size:
            return accepted[-self.window_size:]
        # Reserve a geometry-supported pair; fill remaining slots by recency.
        # No held-out depth measurements enter this choice.
        best=None;score=0.
        for i,a in enumerate(accepted):
            for b in accepted[i+1:]:
                candidate=self.geometry_score(a['key'],b['key'],landmarks)
                if candidate>score:score=candidate;best=(a,b)
        if best is None:return accepted[-self.window_size:]
        chosen=list(best);chosen_ids={identity(v['key']) for v in chosen}
        for view in reversed(accepted):
            if len(chosen)>=self.window_size:break
            if identity(view['key']) not in chosen_ids:
                chosen.append(view);chosen_ids.add(identity(view['key']))
        return sorted(chosen,key=lambda v:v['key']['timestamp'])

    def update(self,reply,load_image,predict,matrix,distortion,size):
        started=time.perf_counter();epoch=reply.get('map_epoch',0)
        removals=[];decisions=[]
        if self.epoch!=epoch:
            removals.extend({'id':k[0],'timestamp':k[1],'reason':'map_epoch_changed'} for k in self.items)
            self.items.clear();self.bad_images.clear();self.epoch=epoch
        keys=sorted(reply.get('keyframes',[]),key=lambda k:k['timestamp'])[-12:]
        metadata={identity(k):k for k in keys}
        active={identity(k) for k in reply.get('active_keyframes',[])} if 'active_keyframes' in reply else None
        for key in list(self.items):
            if key not in metadata:
                reason=('omitted_from_metadata_window' if key in active else 'absent_from_active_map_snapshot') if active is not None else 'absent_from_metadata_unknown'
                removals.append({'id':key[0],'timestamp':key[1],'reason':reason})
                del self.items[key]
        landmarks={int(row[0]):np.asarray(row[1:],float) for row in reply.get('landmarks',[])}
        if any(p.shape!=(3,) or not np.isfinite(p).all() for p in landmarks.values()):raise ValueError('Invalid landmark snapshot')
        updated=None;inference_ms=0.
        anchor=metadata[next(reversed(self.items))] if self.items else None
        # At most one new image/inference per output; no work backlog.
        if reply.get('pose') is not None:
            for key in keys:
                ident=identity(key)
                if ident in self.items or ident in self.bad_images:continue
                if anchor is not None and key['timestamp']<=anchor['timestamp']:continue
                if len(set(key['landmark_ids'])&set(landmarks))<self.min_shared:
                    decisions.append({'id':key['id'],'reason':'insufficient_landmarks'});continue
                anchors=([anchor] if self.selection_policy=='newest' else [metadata[i] for i in reversed(self.items)]) if anchor is not None else []
                matching_anchor=next((a for a in anchors if self.geometry_ok(a,key,landmarks)),None)
                if anchors and matching_anchor is None:
                    decisions.append({'id':key['id'],'reason':'insufficient_shared_landmarks_or_parallax'});continue
                image=load_image(key['timestamp'])
                if image is None:
                    decisions.append({'id':key['id'],'reason':'image_not_archived_yet'});continue
                check=cv2.resize(image,(320,240),interpolation=cv2.INTER_AREA)
                sharpness=float(cv2.Laplacian(cv2.cvtColor(check,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var())
                if sharpness<self.min_sharpness:
                    decisions.append({'id':key['id'],'reason':'insufficient_sharpness','sharpness':sharpness})
                    self.bad_images[ident]=True
                    while len(self.bad_images)>64:self.bad_images.popitem(last=False)
                    break
                resized=cv2.resize(image,size,interpolation=cv2.INTER_AREA)
                inference_started=time.perf_counter();prediction=predict(resized)
                inference_ms=(time.perf_counter()-inference_started)*1000
                if prediction.shape!=resized.shape[:2]:raise ValueError('Keyframe depth/image dimensions differ')
                self.items[ident]={'prediction':prediction.copy(),'image':resized,'sharpness':sharpness}
                while len(self.items)>self.cache_size:
                    evicted,_=self.items.popitem(last=False)
                    removals.append({'id':evicted[0],'timestamp':evicted[1],'reason':'prediction_cache_capacity'})
                decisions.append({'id':key['id'],'reason':'prediction_cached','sharpness':sharpness,
                                  'geometry_anchor_id':matching_anchor['id'] if matching_anchor else None})
                updated=key['id'];break
        accepted=[];reports=[]
        for ident,item in self.items.items():
            key=metadata[ident];pose=np.asarray(key['pose'],float).reshape(4,4)
            if not np.isfinite(pose).all():raise ValueError('Invalid keyframe pose')
            observed=np.array([landmarks[i] for i in key['landmark_ids'] if i in landmarks]).reshape(-1,3)
            signature=(pose.tobytes(),observed.tobytes())
            if item.get('geometry_signature')!=signature:
                depth,status=aligned_depth(observed,pose,item['prediction'],matrix,distortion,int(key['id']))
                item.update(geometry_signature=signature,depth=depth,status=status)
                if depth is not None:
                    item['local'],item['colors']=backproject(depth,item['image'],matrix,distortion,np.eye(4),stride=3)
            depth,status=item['depth'],item['status']
            reports.append({'id':key['id'],'timestamp':key['timestamp'],**status})
            if depth is not None:
                # Camera-local points are rebuilt, not accumulated in old world poses.
                local,colors=item['local'],item['colors']
                world=local@pose[:3,:3].T+pose[:3,3]
                accepted.append({'key':key,'pose':pose,'depth':depth,'points':world,'colors':colors})
        accepted=self.select_window(accepted,landmarks)
        views=[(v['pose'],v['depth']) for v in accepted];chunks=[];colors=[];checks=[]
        for index,view in enumerate(accepted):
            keep,stats=multiview_support(view['points'],index,views,matrix,distortion)
            checks.append({'id':view['key']['id'],**stats})
            if keep.any():chunks.append(view['points'][keep]);colors.append(view['colors'][keep])
        sparse=np.array(list(landmarks.values()),float).reshape(-1,3)
        sparse_rgb=np.full(sparse.shape,160,np.uint8);dense_count=sum(len(p) for p in chunks)
        if chunks:sparse,sparse_rgb=voxel_downsample(np.vstack([sparse,*chunks]),np.vstack([sparse_rgb,*colors]),.002)
        pose=np.asarray(reply['pose']).reshape(4,4) if reply.get('pose') is not None else None
        status={'state':'keyframe_window' if dense_count else 'sparse_only',
            'reason':None if dense_count else 'No cross-view-supported keyframe depth in active window',
            'dense_history':'bounded active keyframe window; rebuilt with current poses and landmark depths',
            'window_keyframes':[v['key']['id'] for v in accepted],'prediction_cache_size':len(self.items),
            'window_limit':self.window_size,'cache_limit':self.cache_size,'dense_points':dense_count,
            'new_keyframe_id':updated,'keyframe_inference_ms':inference_ms,
            'keyframe_removals':removals,'candidate_decisions':decisions,
            'selection_policy':self.selection_policy,
            'window_policy':self.window_policy,
            'per_keyframe':reports,'cross_view':checks,'window_update_ms':(time.perf_counter()-started)*1000}
        return sparse,sparse_rgb,pose,status
