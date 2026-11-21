"""Explicit timing statistics in a single monotonic clock domain."""
import numpy as np


def distribution(values):
    values=np.asarray(values,dtype=float)
    if not len(values):return {'samples':0,'p50_ms':None,'p95_ms':None,'p99_ms':None}
    return dict(samples=len(values),**{f'p{p}_ms':float(np.percentile(values,p)) for p in [50,95,99]})


class TimingSummary:
    def __init__(self,deadline_ms=500):
        if deadline_ms<=0:raise ValueError('Deadline must be positive')
        self.deadline_ms=deadline_ms;self.ages=[];self.intervals=[];self.last=None;self.skipped=0

    def add(self,age_ms,completed_at,skipped=0):
        if not np.isfinite(age_ms) or age_ms<0:raise ValueError('Invalid frame age')
        self.ages.append(age_ms);self.skipped+=skipped
        if self.last is not None:self.intervals.append((completed_at-self.last)*1000)
        self.last=completed_at

    def report(self):
        median=float(np.median(self.intervals)) if self.intervals else 0
        return {'capture_receipt_to_packet':distribution(self.ages),
            'output_interval':distribution(self.intervals),
            'interval_jitter_abs_deviation_from_median':distribution(np.abs(np.asarray(self.intervals)-median)),
            'deadline_ms':self.deadline_ms,'deadline_misses':sum(a>self.deadline_ms for a in self.ages),
            'skipped_capture_frames':self.skipped,
            'scope':'Software capture receipt to packet readiness. Excludes sensor buffering and network/browser display.'}
