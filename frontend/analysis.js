import {percentile} from './protocol.js';
const get=id=>document.getElementById(id);
let depthTimes=[],slamTimes=[],seenSequences=new Set();
export function updateRunInfo(session,report=null){
  const metadata=session?.metadata||{};
  get('run-info').textContent=session?`${session.name} | ${(metadata.image_size_wh||[]).join(' x ')||'Resolution unavailable'} | ${metadata.depth_model||report?.fusion?.depth_model||'Model unavailable'} | ${metadata.depth_device||'Device unavailable'} | Final static map`:'Select a session. Unrecorded measurements remain unavailable.';
}
export function resetOfflineDepthTiming(){depthTimes=[];seenSequences.clear();renderTimes();}
export function renderAnalysis(report=null,session=null){
  depthTimes=[];slamTimes=[];seenSequences.clear();
  const metadata=session?.metadata||{};
  get('run-info').textContent=session?`${session.name} | ${(metadata.image_size_wh||[]).join(' x ')||'Resolution unavailable'} | ${metadata.depth_model||report?.fusion?.depth_model||'Model unavailable'} | ${metadata.depth_device||'Device unavailable'} | Final static map`:'Select a session. Unrecorded measurements remain unavailable.';
  const tracking=report?.tracking;
  get('tracking-summary').textContent=tracking?`Live pose availability: ${tracking.available}/${tracking.total} frames (${(100*tracking.available/tracking.total).toFixed(1)}%)`:'Tracking measurements unavailable';
  const timeline=get('tracking-timeline'),ctx=timeline.getContext('2d');ctx.clearRect(0,0,timeline.width,timeline.height);
  if(tracking?.samples.length){
    tracking.samples.forEach((s,i)=>{ctx.fillStyle=s.available?'#a3f1c5':'#d3ad68';ctx.fillRect(i/tracking.samples.length*timeline.width,0,timeline.width/tracking.samples.length+1,timeline.height);});
    slamTimes=tracking.samples.map(s=>s.tracking_ms);
  }
  const fusion=report?.fusion;
  get('fusion-summary').textContent=fusion?`Fusion: ${fusion.fused_keyframes??0} retained views | ${fusion.map_points??0} total points | Held-out SLAM agreement: ${Number.isFinite(fusion.heldout_abs_rel_mean)?(100*fusion.heldout_abs_rel_mean).toFixed(2)+'%':'unavailable'} | Arbitrary units, not meters`:'Fusion measurements unavailable';
  const canvas=get('fusion-chart'),plot=canvas.getContext('2d');plot.clearRect(0,0,canvas.width,canvas.height);
  const rows=fusion?.keyframes||[],values=rows.map(r=>r.heldout_abs_rel_mean).filter(Number.isFinite),max=Math.max(...values,0.01);
  rows.forEach((r,i)=>{if(!Number.isFinite(r.heldout_abs_rel_mean))return;plot.fillStyle=r.status==='fused'?'#a3f1c5':'#d3ad68';const h=r.heldout_abs_rel_mean/max*70;plot.fillRect(i/rows.length*canvas.width,78-h,Math.max(1,canvas.width/rows.length-3),h);plot.fillStyle='#b8cbbd';plot.font='11px monospace';plot.fillText((r.heldout_abs_rel_mean*100).toFixed(1)+'%',i/rows.length*canvas.width,95);});
  renderTimes();
}
function renderTimes(){
  const describe=(name,values)=>{const p50=percentile(values,50),p95=percentile(values,95);return p50===null?`${name}: unavailable`:`${name}: p50 ${p50.toFixed(1)} ms / p95 ${p95.toFixed(1)} ms (${values.length} samples)`;};
  get('offline-timing').textContent=describe('Offline depth',depthTimes)+' | '+describe('Recorded SLAM call',slamTimes);
}
export function updateOfflineTiming(header){
  if(Number.isFinite(header.offline_depth_ms?.total_ms)&&!seenSequences.has(header.sequence)){seenSequences.add(header.sequence);depthTimes.push(header.offline_depth_ms.total_ms);renderTimes();}
}
