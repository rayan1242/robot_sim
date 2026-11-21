import {PacketAssembler, decodeCloud, percentile, formatTime} from './protocol.js';
import {renderAnalysis,updateOfflineTiming,resetOfflineDepthTiming,updateRunInfo} from './analysis.js';

const $=id=>document.getElementById(id);
const state={sessions:[],selected:null,activeId:null,connected:false,busy:false,lastSequence:-1,lastSession:null,cloudSession:null,depth:false,timings:[],jpegUrl:null,ws:null,refreshToken:0,previewController:null};
let spatial=null, reconnectTimer=null, toastTimer=null;
const analyses=new Map();
let timingKind='live';
let liveMapEpoch=null;
let lastArrival=null,browserIntervals=[];
function showRecordedRate(session){
  const samples=analyses.get(session?.id)?.tracking?.samples;
  if(!samples||samples.length<2)return;
  const duration=samples.at(-1).timestamp-samples[0].timestamp;
  if(duration<=0)return;
  $('fps').innerHTML=`${((samples.length-1)/duration).toFixed(1)} <small>FPS</small>`;
  $('fps-note').textContent='Original recording rate from frame timestamps';
}

function toast(message,error=false) {
  $('toast').textContent=message; $('toast').classList.toggle('error',error); $('toast').hidden=false;
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,6000);
}
async function api(path,options={}) {
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  if(!response.ok) {let detail;try{detail=(await response.json()).detail;}catch{}throw new Error(typeof detail==='string'?detail:`Request failed (${response.status})`);}
  return response.json();
}
function activeSession() {return state.sessions.find(s=>['recording','replaying'].includes(s.status));}
function updateButtons() {
  const active=!!state.activeId;
  $('play').disabled=!state.connected||state.busy||active||!state.selected||['error','importing','interrupted'].includes(state.selected.status);
  $('stop').disabled=!state.connected||state.busy||!active;
  $('new-recording').disabled=!state.connected||state.busy||active;
  $('record-submit').disabled=state.busy||active||!state.connected;
  $('quick-replay').disabled=state.busy||!state.connected||(!active&&$('play').disabled);
  $('quick-replay').textContent=active?'■ Stop source':'▶ Start replay';
  for(const button of document.querySelectorAll('[data-play]')) button.disabled=!state.connected||state.busy||active;
}
function connection(online,label) {
  state.connected=online;
  $('connection').className=`connection ${online?'online':'offline'}`;
  $('connection').querySelector('span').textContent=label;
  $('endpoint').textContent=location.origin;
  $('connection-detail').textContent=online?'Connected over a local WebSocket. Session controls are available.':'The stream is disconnected. Check that the backend is running; reconnect is automatic.';
  $('footer-state').textContent=online?'Stream connected':label;
  updateButtons();
}
function resetVisuals() {
  liveMapEpoch=null;
  lastArrival=null;browserIntervals=[];
  timingKind='live';
  $('freshness').textContent='Start a live recording to measure frame age and update jitter.';
  $('browser-timing').textContent='Browser image decoding: unavailable';
  renderAnalysis();
  spatial?.reset(); state.cloudSession=null; state.lastSequence=-1; state.lastSession=null;
  state.timings=[]; state.depth=false;
  $('points').textContent='0'; $('points-note').textContent='No snapshot in this session';
  $('map-kind').textContent='NO MAP'; $('map-empty').hidden=false;
  $('camera-image').hidden=true; $('depth-image').hidden=true; $('camera-empty').hidden=false;
  $('camera-image').onload=null; $('camera-image').onerror=null; $('camera-image').removeAttribute('src');
  if(state.jpegUrl){URL.revokeObjectURL(state.jpegUrl);state.jpegUrl=null;}
  $('rgb-mode').classList.add('active'); $('rgb-mode').setAttribute('aria-pressed','true');
  $('depth-mode').classList.remove('active'); $('depth-mode').setAttribute('aria-pressed','false'); $('depth-mode').disabled=true;
  $('depth-mode').title='Start replay to check for saved relative depth';
  $('pose-status').textContent='Unavailable'; $('pose-note').textContent='Start replay for saved poses';
  $('fps').innerHTML='— <small>FPS</small>'; $('fps-note').textContent='No measured source rate';
  $('latency').innerHTML='— <small>ms</small>'; $('latency-note').textContent='No recorded timing samples';
  $('frame-label').textContent='FRAME —'; $('camera-time').textContent='00:00.0';
  $('progress').value=0; $('source-kind').textContent='SAVED'; $('stream-state').textContent='READY';
  updateTiming();
}
function setCloud(buffer,count,sessionId,semantics=null,fusion=null) {
  const values=decodeCloud(buffer,count);
  spatial?.setCloud(values); state.cloudSession=sessionId;
  $('points').textContent=count.toLocaleString(); $('points-note').textContent='Final snapshot · up to 5,000 displayed';
  $('map-kind').textContent='SNAPSHOT'; $('map-empty').hidden=count>0&&!!spatial;
  $('map-description').textContent='Saved final map · drag to orbit · scroll to zoom';
  if(semantics==='live_sparse_and_local_dense'){
    $('points-note').textContent='Live sparse map + local dense preview · capped at 5,000';
    $('map-kind').textContent='LIVE MAP';
    $('map-description').textContent='Sparse map updated by SLAM · current dense patch only';
    if(fusion?.state==='sparse_only'){
      $('points-note').textContent='Live sparse map only · dense preview withheld';$('map-kind').textContent='LIVE SPARSE';
      $('map-description').textContent='Current sparse SLAM snapshot · no accepted dense patch';
    }else if(fusion?.state==='local_dense_preview')$('map-kind').textContent='LIVE + DENSE';
    else if(fusion?.state==='keyframe_window'){
      $('map-kind').textContent='LIVE WINDOW';$('points-note').textContent='Sparse map + validated keyframe window · capped at 5,000';
      $('map-description').textContent='Bounded dense window rebuilt using updated keyframe poses';
    }
  }
}
async function selectSession(session,{preview=true}={}) {
  if(!session) return;
  const same=state.selected?.id===session.id;
  state.selected=session;
  if(!same) resetVisuals();
  $('selected-name').textContent=session.name;
  const size=session.metadata.image_size_wh||session.metadata.actual_image_size_wh;
  $('resolution').textContent=size?`${size[0]} × ${size[1]}`:'— × —';
  $('progress').max=session.metadata.duration_seconds||session.metadata.options?.duration||1;
  $('session-limitations').replaceChildren();
  for(const limitation of session.metadata.limitations||[]) {const li=document.createElement('li');li.textContent=limitation;$('session-limitations').append(li);}
  const imported=session.metadata.source==='offline_import';
  document.querySelector('[aria-label="Recorded reconstruction diagnostics"]').hidden=!imported;
  $('source-note').querySelector('p').textContent=imported?'Offline replay. Saved poses and a final map are shown when available; live reconstruction and missing timing are not inferred.':'Saved or live RGB capture. Camera poses and a map are unavailable without offline SLAM integration.';
  if(session.metadata.options?.slam)$('source-note').querySelector('p').textContent='Experimental live SLAM. Sparse map grows after initialization; dense preview is local and replaced each update. Units are arbitrary.';
  if(session.metadata.options?.keyframe_map)$('source-note').querySelector('p').textContent='Experimental bounded keyframe window. Dense points require multiple accepted views and are rebuilt after pose changes; not a complete room reconstruction.';
  renderSessions(); updateButtons();
  if(!same){
    renderAnalysis(null,session);
    api(`/sessions/${session.id}/analysis`).then(report=>{analyses.set(session.id,report);if(state.selected?.id===session.id){renderAnalysis(report,state.selected);showRecordedRate(state.selected);}}).catch(()=>{});
  }
  if(!preview || same) return;
  state.previewController?.abort(); const controller=new AbortController();state.previewController=controller;
  const id=session.id;
  $('camera-image').src=`/sessions/${id}/preview`;
  $('camera-image').onload=()=>{if(state.selected?.id===id){$('camera-image').hidden=false;$('camera-empty').hidden=true;}};
  $('camera-image').onerror=()=>{if(state.selected?.id===id&&!state.jpegUrl){$('camera-image').hidden=true;$('camera-empty').hidden=false;}};
  try {
    const response=await fetch(`/sessions/${id}/snapshot`,{signal:controller.signal});
    if(response.status===404) return;
    if(!response.ok) throw new Error('Could not load the saved map');
    const buffer=await response.arrayBuffer();
    if(state.selected?.id===id) setCloud(buffer,Number(response.headers.get('X-Point-Count')),id);
  } catch(error) {if(error.name!=='AbortError')toast(error.message,true);}
}
function renderSessions() {
  const container=$('session-list');container.replaceChildren();
  $('session-count').textContent=state.sessions.length;
  if(!state.sessions.length){const empty=document.createElement('div');empty.className='list-empty';empty.textContent='No sessions yet. Start a recording, or import saved pipeline outputs.';container.append(empty);return;}
  for(const session of state.sessions) {
    const row=document.createElement('div');row.className=`session-row ${state.selected?.id===session.id?'selected':''}`;
    const active=['recording','replaying'].includes(session.status);
    const source=session.metadata.source==='offline_import'?'OFFLINE':'CAMERA';
    row.innerHTML='<span class="session-icon" aria-hidden="true">⌗</span><div class="session-info" role="button" tabindex="0"><h3></h3><p></p></div><span class="session-badge"></span><div class="session-actions"><button data-play title="Replay session" aria-label="Replay session">▶</button><a title="Download session archive" aria-label="Download session archive">↓</a><button data-delete title="Delete session" aria-label="Delete session">×</button></div>';
    row.querySelector('h3').textContent=session.name;
    const date=new Date(session.created_at).toLocaleDateString(undefined,{month:'short',day:'numeric'});
    const count=session.metadata.frames??session.metadata.saved_rgb_frames;
    row.querySelector('p').textContent=`${date} · ${count??'—'} frames · ${session.status}`;
    row.querySelector('.session-badge').textContent=source;
    const info=row.querySelector('.session-info'); info.onclick=()=>selectSession(session);info.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectSession(session);}};
    row.querySelector('[data-play]').onclick=()=>startReplay(session);
    const download=row.querySelector('a');download.href=`/sessions/${session.id}/download`;download.setAttribute('aria-disabled',String(active));
    const del=row.querySelector('[data-delete]');del.disabled=active;
    del.onclick=()=>{$('delete-description').textContent=session.name;$('confirm-delete').dataset.id=session.id;$('delete-dialog').showModal();};
    container.append(row);
  }
  updateButtons();
}
async function refreshSessions() {
  const token=++state.refreshToken;
  try {
    const sessions=await api('/sessions');if(token!==state.refreshToken)return;
    state.sessions=sessions;
    const active=activeSession();
    state.activeId=active?.id??null;
    const selected=sessions.find(s=>s.id===state.selected?.id);
    if(selected){state.selected=selected;updateRunInfo(selected,analyses.get(selected.id));showRecordedRate(selected);}
    else {state.selected=null;const first=active||sessions.find(s=>s.metadata.source==='offline_import'&&s.status==='ready')||sessions[0];if(first)await selectSession(first);else{resetVisuals();$('selected-name').textContent='Select a session';}}
    renderSessions();
  } catch(error) {$('library-note').textContent='Could not load the session library';if(!state.sessions.length)$('session-list').textContent='Backend unavailable. Check the server connection.';}
}
async function startReplay(session=state.selected) {
  if(!session || state.busy)return;
  state.busy=true;updateButtons();
  try {
    await selectSession(session);
    await api(`/sessions/${session.id}/replay`,{method:'POST',body:JSON.stringify({speed:Number($('speed').value)})});
    state.activeId=session.id;state.lastSequence=-1;spatial?.resetTrail();state.timings=[];updateTiming();resetOfflineDepthTiming();
    toast('Replay started. The map is a saved snapshot.');await refreshSessions();
  } catch(error) {toast(error.message,true);}
  finally {state.busy=false;updateButtons();}
}
function updateDepth(header) {
  const available=!!header.depth_kind&&Number.isInteger(header.sequence)&&!!header.session_id;
  $('depth-mode').disabled=!available;
  $('depth-mode').title=available?'Overlay saved relative inverse depth; not meters':'Depth was not recorded for this source';
  if(state.depth&&available){requestDepth(header.session_id,header.sequence);}
  else $('depth-image').hidden=true;
}
function requestDepth(sessionId,sequence){
  const image=$('depth-image');image.hidden=true;
  image.onload=()=>{image.hidden=!(state.depth&&state.selected?.id===sessionId&&state.lastSequence===sequence);};
  image.src=`/sessions/${sessionId}/depth/${sequence}`;
}
function handlePacket({header,rgb,cloud}) {
  const active=['running','starting'].includes(header.state);
  if(active&&header.session_id){state.activeId=header.session_id;const session=state.sessions.find(s=>s.id===header.session_id);if(session&&state.selected?.id!==session.id)selectSession(session,{preview:false});}
  if(!header.session_id){updateButtons();return;}
  if(state.selected?.id!==header.session_id)return;
  if(state.lastSession!==header.session_id || (Number.isInteger(header.sequence)&&header.sequence<state.lastSequence)) {spatial?.resetTrail();state.timings=[];resetOfflineDepthTiming();lastArrival=null;browserIntervals=[];}
  const newFrame=Number.isInteger(header.sequence)&&header.sequence!==state.lastSequence;
  if(header.map_epoch!==undefined){if(liveMapEpoch!==null&&liveMapEpoch!==header.map_epoch)spatial?.resetTrail();liveMapEpoch=header.map_epoch;}
  if(newFrame){const now=performance.now();if(lastArrival!==null){browserIntervals.push(now-lastArrival);if(browserIntervals.length>120)browserIntervals.shift();}lastArrival=now;}
  state.lastSession=header.session_id;
  if(rgb) {
    const receivedAt=performance.now();
    const url=URL.createObjectURL(new Blob([rgb],{type:'image/jpeg'}));
    $('camera-image').onload=()=>{
      $('camera-image').hidden=false;$('camera-empty').hidden=true;
      const median=percentile(browserIntervals,50),interval=percentile(browserIntervals,95),jitter=percentile(browserIntervals.map(v=>Math.abs(v-median)),95);
      $('browser-timing').textContent=`Packet assembly → image load: ${(performance.now()-receivedAt).toFixed(1)} ms | Browser packet interval p95: ${interval===null?'unavailable':interval.toFixed(1)+' ms'} | Interval jitter p95: ${jitter===null?'unavailable':jitter.toFixed(1)+' ms'} (last ${browserIntervals.length} intervals; browser clock only)`;
    };
    $('camera-image').onerror=()=>{toast('The camera image could not be decoded',true);};
    $('camera-image').src=url;if(state.jpegUrl)URL.revokeObjectURL(state.jpegUrl);state.jpegUrl=url;
  }
  if(cloud&&(state.cloudSession!==header.session_id||header.cloud_semantics==='live_sparse_and_local_dense'))setCloud(cloud,header.cloud_point_count,header.session_id,header.cloud_semantics,header.fusion);
  if(header.cloud_semantics==='live_sparse_and_local_dense'&&!header.cloud_point_count){
    spatial?.setCloud(new Float32Array(0));$('points').textContent='0';$('map-empty').hidden=false;$('map-kind').textContent='INITIALIZING';
  }
  if(newFrame){spatial?.setPose(header.pose);state.lastSequence=header.sequence;updateOfflineTiming(header);}
  $('source-kind').textContent=header.mode==='replay'?'REPLAY':'LIVE RGB';
  if(header.mode==='live'&&header.slam_sequence!==undefined)$('source-kind').textContent='LIVE SLAM';
  $('stream-state').textContent=header.stopped?'STOPPED':header.state.toUpperCase();
  $('frame-label').textContent=Number.isInteger(header.sequence)?`FRAME ${String(header.sequence+1).padStart(4,'0')}`:'FRAME —';
  $('camera-time').textContent=formatTime(header.timestamp);
  $('progress').value=Number.isFinite(header.timestamp)?header.timestamp:0;
  if(header.image_size_wh)$('resolution').textContent=header.image_size_wh.join(' × ');
  const pose=Array.isArray(header.pose);
  $('pose-status').textContent=pose?'Available':'Unavailable';
  $('pose-note').textContent=pose?'Saved optimized pose · arbitrary scale':header.mode==='live'?'Live SLAM is not integrated':'No saved pose for this frame';
  if(header.mode==='live'&&header.slam_sequence!==undefined)$('pose-note').textContent=pose?'Online SLAM pose · experimental, arbitrary scale':'SLAM initializing or tracking lost';
  if(header.mode==='replay'&&pose&&header.pose_kind==='online')$('pose-note').textContent='Recorded online SLAM pose; not optimized';
  if(header.mode==='live'&&header.fusion){
    const fusion=header.fusion;
    $('source-note').querySelector('p').textContent=fusion.state==='keyframe_window'?
      `Validated dense window: ${fusion.window_keyframes.length}/${fusion.window_limit} keyframes. Rebuilt with current poses; not a complete room map.${pose?'':' Current camera tracking is lost.'}`:pose?
      (fusion.state==='local_dense_preview'?`Live sparse map + current dense preview. Held-out SLAM agreement: ${Number.isFinite(fusion.heldout_abs_rel_mean)?(100*fusion.heldout_abs_rel_mean).toFixed(1)+'%':'unavailable'}; not independent accuracy.`:`Live sparse map only. Dense preview withheld: ${fusion.reason}.`):
      'SLAM is initializing or tracking is lost. No depth points are fused without a tracked pose.';
    if(header.map_snapshot_warning)$('source-note').querySelector('p').textContent+=' '+header.map_snapshot_warning;
  }
  const firstTracked=analyses.get(header.session_id)?.tracking?.samples?.find(s=>s.available);
  if(!pose&&header.mode==='replay'&&firstTracked&&header.source_timestamp<firstTracked.timestamp){
    $('pose-note').textContent=`Before SLAM initialization at ${firstTracked.timestamp.toFixed(1)} s`;
  }
  $('fps').innerHTML=Number.isFinite(header.fps)?`${header.fps.toFixed(1)} <small>FPS</small>`:'— <small>FPS</small>';
  $('fps-note').textContent=Number.isFinite(header.fps)?'Measured camera capture rate':'Source FPS not recorded in replay';
  if(header.mode==='replay'&&!Number.isFinite(header.fps))showRecordedRate(state.selected);
  const offline=header.mode==='replay'&&!!header.offline_depth_ms;
  timingKind=offline?'offline':'live';
  const timing=offline?header.offline_depth_ms:header.latency_ms;
  const total=timing?.capture_to_state??timing?.total_ms;
  $('latency').innerHTML=Number.isFinite(total)?`${Math.round(total)} <small>ms</small>`:'— <small>ms</small>';
  $('latency-note').textContent=Number.isFinite(total)?'Capture receipt → state · excludes sensor buffering':'Unavailable for imported replay';
  if(offline)$('latency-note').textContent='Offline depth only; not end-to-end latency';
  if(newFrame&&timing&&Number.isFinite(total)){state.timings.push({...timing,capture_to_state:total});if(state.timings.length>120)state.timings.shift();updateTiming();}
  updateDepth(header);
  if(header.mode==='live'&&header.timing_summary){
    const s=header.timing_summary,a=s.capture_receipt_to_packet,j=s.interval_jitter_abs_deviation_from_median;
    const fmt=v=>Number.isFinite(v)?v.toFixed(1):'unavailable';
    $('freshness').textContent=`Capture receipt → packet: p50 ${fmt(a.p50_ms)} / p95 ${fmt(a.p95_ms)} / p99 ${fmt(a.p99_ms)} ms | Output jitter p95 ${fmt(j.p95_ms)} ms | Deadline ${s.deadline_ms} ms: ${s.deadline_misses}/${a.samples} misses | Skipped capture frames: ${s.skipped_capture_frames} | Receipt → server send: ${fmt(header.capture_receipt_to_server_send_ms)} ms`;
    $('latency-note').textContent='Capture receipt → packet; excludes sensor/network/display';
  }else if(header.mode==='replay')$('freshness').textContent='Recorded replay: live freshness is not measured by playback speed.';
  $('footer-state').textContent=`${header.mode==='replay'?'Replay':'Capture'} · ${header.state} · ${header.subscriber_skipped_updates||0} skipped updates`;
  if(['completed','error'].includes(header.state)){
    const wasActive=!!state.activeId;state.activeId=null;
    if(wasActive){toast(header.state==='error'?(header.error||'Pipeline stopped with an error'):'Session complete',header.state==='error');refreshSessions();}
  }
  updateButtons();
}
function connect() {
  clearTimeout(reconnectTimer);
  if(state.ws){state.ws.onclose=null;state.ws.close();}
  const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/live`);state.ws=socket;socket.binaryType='arraybuffer';
  const assembler=new PacketAssembler(handlePacket);
  socket.onopen=()=>{connection(true,'Connected');refreshSessions();};
  socket.onmessage=event=>{try{assembler.receive(event.data);}catch(error){toast(`Stream error: ${error.message}`,true);socket.close();}};
  socket.onerror=()=>connection(false,'Disconnected');
  socket.onclose=()=>{connection(false,'Reconnecting');reconnectTimer=setTimeout(connect,2500);};
}
function updateTiming() {
  $('timing-title').textContent=timingKind==='offline'?'Offline depth timing':'Pipeline timing';
  $('timing-scope').textContent=timingKind==='offline'?'Depth processing only; capture, SLAM, fusion and network excluded':'Capture → state';
  $('latency-chart').setAttribute('aria-label',timingKind==='offline'?'Measured offline depth processing time chart':'Measured capture-to-state latency chart');
  const values=state.timings.map(s=>s.capture_to_state);
  const p50=percentile(values,50),p95=percentile(values,95);
  $('p50').innerHTML=p50===null?'— <small>ms</small>':`${Math.round(p50)} <small>ms</small>`;
  $('p95').innerHTML=p95===null?'— <small>ms</small>':`${Math.round(p95)} <small>ms</small>`;
  for(const [prefix,key] of [['pre','preprocess_ms'],['infer','inference_ms'],['post','postprocess_ms']])for(const p of [50,95]){
    const result=percentile(state.timings.map(s=>s[key]),p);$(`${prefix}-p${p}`).textContent=result===null?'—':`${result.toFixed(1)} ms`;
  }
  for(const [prefix,key] of [['input','input_age_ms'],['roundtrip','slam_roundtrip_ms'],['slam','slam_ms'],['fusion','fusion_ms'],['save','rgb_save_ms']])for(const p of [50,95]){
    const result=percentile(state.timings.map(s=>s[key]),p);$(`${prefix}-p${p}`).textContent=result===null?'—':`${result.toFixed(1)} ms`;
  }
  $('timing-empty').hidden=values.length>0;
  const canvas=$('latency-chart'),rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
  canvas.width=Math.max(1,Math.round(rect.width*dpr));canvas.height=Math.max(1,Math.round(rect.height*dpr));
  const context=canvas.getContext('2d');context.scale(dpr,dpr);const w=rect.width,h=rect.height;
  context.strokeStyle='#2a3c31';context.lineWidth=0.6;
  for(let i=0;i<4;i++){const y=8+i*(h-16)/3;context.beginPath();context.moveTo(0,y);context.lineTo(w,y);context.stroke();}
  if(!values.length)return;
  const max=Math.max(...values,1)*1.15;context.strokeStyle='#a3f1c5';context.lineWidth=1.6;context.beginPath();
  values.forEach((v,i)=>{const x=i/Math.max(values.length-1,1)*w,y=h-8-v/max*(h-16);if(i===0)context.moveTo(x,y);else context.lineTo(x,y);});context.stroke();
}

$('play').onclick=()=>startReplay();
$('quick-replay').onclick=()=>state.activeId?$('stop').click():startReplay();
$('stop').onclick=async()=>{if(!state.activeId)return;state.busy=true;updateButtons();try{await api(`/sessions/${state.activeId}/stop`,{method:'POST'});state.activeId=null;toast('Source stopped. Replay restarts from the beginning.');await refreshSessions();}catch(error){toast(error.message,true);}finally{state.busy=false;updateButtons();}};
$('new-recording').onclick=()=>$('record-dialog').showModal();
$('record-form').onsubmit=async event=>{
  event.preventDefault();if(state.busy)return;state.busy=true;updateButtons();const form=new FormData(event.target);
  const body={name:form.get('name'),backend:'dshow',auto_exposure:true,fps:15,duration:Number(form.get('duration')),camera:Number(form.get('camera')),width:Number(form.get('width')),height:Number(form.get('height')),depth:form.has('depth'),device:'auto'};
  [body.depth_width,body.depth_height]=String(form.get('depth_size')||'320,240').split(',').map(Number);
  body.slam=form.has('slam');if(body.slam)body.depth=true;
  body.keyframe_map=form.has('keyframe_map');if(body.keyframe_map){body.slam=true;body.depth=true;}
  try{const saved=await api('/sessions/start',{method:'POST',body:JSON.stringify(body)});state.activeId=saved.id;state.sessions.unshift(saved);await selectSession(saved,{preview:false});$('record-dialog').close();toast('Recording started using DirectShow.');await refreshSessions();}catch(error){toast(error.message,true);}finally{state.busy=false;updateButtons();}
};
$('confirm-delete').onclick=async()=>{const id=$('confirm-delete').dataset.id;$('confirm-delete').disabled=true;try{await api(`/sessions/${id}`,{method:'DELETE'});$('delete-dialog').close();toast('Session deleted');await refreshSessions();}catch(error){toast(error.message,true);}finally{$('confirm-delete').disabled=false;}};
for(const button of document.querySelectorAll('.close-dialog'))button.onclick=()=>button.closest('dialog').close();
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
$('connection-button').onclick=()=>$('connection-dialog').showModal();
$('reconnect').onclick=()=>{connect();$('connection-dialog').close();};
$('refresh-sessions').onclick=()=>refreshSessions();
$('nav-sessions').onclick=()=>$('sessions-panel').scrollIntoView({behavior:'smooth',block:'center'});
$('nav-diagnostics').onclick=()=>{$('limitations').open=true;$('timing-panel').scrollIntoView({behavior:'smooth',block:'start'});};
$('nav-workspace').onclick=()=>window.scrollTo({top:0,behavior:'smooth'});
$('fit-map').onclick=()=>spatial?.fit();
for(const [id,method] of [['toggle-grid','showGrid'],['toggle-trail','showTrail']])$(id).onclick=()=>{const active=$(id).getAttribute('aria-pressed')!=='true';$(id).setAttribute('aria-pressed',String(active));$(id).classList.toggle('active',active);spatial?.[method](active);};
$('rgb-mode').onclick=()=>{state.depth=false;$('depth-image').hidden=true;$('rgb-mode').classList.add('active');$('depth-mode').classList.remove('active');$('rgb-mode').setAttribute('aria-pressed','true');$('depth-mode').setAttribute('aria-pressed','false');};
$('depth-mode').onclick=()=>{state.depth=true;$('depth-mode').classList.add('active');$('rgb-mode').classList.remove('active');$('depth-mode').setAttribute('aria-pressed','true');$('rgb-mode').setAttribute('aria-pressed','false');if(state.selected&&state.lastSequence>=0)requestDepth(state.selected.id,state.lastSequence);};
$('depth-image').onerror=()=>{if(state.depth){state.depth=false;$('depth-image').hidden=true;toast('No saved depth array is available for this frame',true);$('rgb-mode').click();}};
window.addEventListener('resize',()=>updateTiming());
window.addEventListener('beforeunload',()=>{if(state.jpegUrl)URL.revokeObjectURL(state.jpegUrl);state.ws?.close();});

async function init() {
  try {const {SpatialView}=await import('./viewport.js');spatial=new SpatialView($('viewport'));}
  catch(error){$('map-empty').querySelector('h3').textContent='3D view unavailable';$('map-empty').querySelector('p').textContent='Enable WebGL to inspect point clouds. Replay and recording still work.';for(const id of ['fit-map','toggle-grid','toggle-trail'])$(id).disabled=true;console.warn('3D view unavailable:',error.message);}
  await refreshSessions();connect();updateTiming();
  setInterval(refreshSessions,5000);
}
init();
