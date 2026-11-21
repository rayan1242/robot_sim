"""Timed replay experiment: actual wall-clock queues with injected consumer delays.

This measures scheduling/freshness, not model speed or network latency.
"""
import argparse
import csv
import json
import platform
from pathlib import Path
from queue import Queue,Empty,Full
import threading
import time

from perception.timing import TimingSummary


def run(policy,duration,fps,service_ms,spike_ms):
    queue=Queue(maxsize=1 if policy=='latest' else 32)
    stop=threading.Event();dropped=[0];generated=[0]
    started=time.perf_counter()
    def producer():
        sequence=0
        while not stop.is_set():
            due=started+sequence/fps
            if due-started>=duration:break
            if stop.wait(max(0,due-time.perf_counter())):break
            frame=(sequence,time.perf_counter());generated[0]+=1
            try:queue.put_nowait(frame)
            except Full:
                try:queue.get_nowait();dropped[0]+=1
                except Empty:pass
                queue.put_nowait(frame)
            sequence+=1
    thread=threading.Thread(target=producer);thread.start()
    summary=TimingSummary(500);rows=[]
    try:
        while time.perf_counter()-started<duration:
            try:sequence,receipt=queue.get(timeout=.1)
            except Empty:continue
            input_age=(time.perf_counter()-receipt)*1000
            delay=service_ms+(spike_ms if len(rows)%10==9 else 0)
            time.sleep(delay/1000)
            completed=time.perf_counter();age=(completed-receipt)*1000
            summary.add(age,completed)
            rows.append({'sequence':sequence,'completed_seconds':completed-started,'input_age_ms':input_age,'result_age_ms':age,'injected_service_ms':delay})
    finally:stop.set();thread.join()
    return {'policy':policy,'capacity':queue.maxsize,'generated_frames':generated[0],
        'overwritten_frames':dropped[0],'pending_frames_at_stop':queue.qsize(),
        'measurement':summary.report(),'samples':rows}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--duration',type=float,default=8)
    p.add_argument('--fps',type=float,default=15)
    p.add_argument('--service-ms',type=float,default=150)
    p.add_argument('--spike-ms',type=float,default=300)
    p.add_argument('--output',type=Path,default=Path('data/freshness_benchmark'))
    a=p.parse_args()
    if not 0<a.duration<=120 or not 0<a.fps<=120 or a.service_ms<0 or a.spike_ms<0:p.error('Invalid experiment parameters')
    results=[run(policy,a.duration,a.fps,a.service_ms,a.spike_ms) for policy in ['fifo','latest']]
    a.output.mkdir(parents=True,exist_ok=True)
    for result in results:
        with (a.output/(result['policy']+'.csv')).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['sequence','completed_seconds','input_age_ms','result_age_ms','injected_service_ms'])
            writer.writeheader();writer.writerows(result['samples'])
    report={'experiment':'Real wall-clock producer/consumer experiment with synthetic frame tokens and injected delays; NOT measured depth inference, sensor or network performance',
        'platform':platform.platform(),'processor':platform.processor(),'parameters':vars(a)|{'output':str(a.output)},'runs':results,
        'policy_note':'Bounded FIFO keeps arrival order, drops oldest on overflow; latest keeps one pending frame. Producer timestamps software arrival, not scheduled due time. Pending frames are not drained at the end.'}
    (a.output/'report.json').write_text(json.dumps(report,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,4))
    for r in results:ax.plot([s['completed_seconds'] for s in r['samples']],[s['result_age_ms'] for s in r['samples']],label=r['policy'])
    ax.set(xlabel='Experiment time (seconds)',ylabel='Software receipt to result (ms)',title='Injected-delay queue experiment (not model inference)');ax.legend();fig.tight_layout();fig.savefig(a.output/'frame_age.png',dpi=150);plt.close(fig)
    print(json.dumps([{k:v for k,v in r.items() if k!='samples'} for r in results],indent=2))


if __name__=='__main__':main()
