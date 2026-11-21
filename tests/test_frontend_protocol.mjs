import test from 'node:test';
import assert from 'node:assert/strict';
import {PacketAssembler,decodeCloud,percentile,formatTime} from '../frontend/protocol.js';

test('ordered JSON, JPEG, and binary geometry are assembled as one update',()=>{
  const received=[];
  const assembler=new PacketAssembler(packet=>received.push(packet));
  assembler.receive(JSON.stringify({protocol_version:1,rgb_bytes:3,cloud_bytes:24,cloud_point_count:1}));
  assembler.receive(new Uint8Array([1,2,3]).buffer);
  assert.equal(received.length,0);
  assembler.receive(new Float32Array([1,2,3,0.5,0.5,1]).buffer);
  assert.equal(received.length,1);
  assert.equal(received[0].rgb.byteLength,3);
  assert.deepEqual([...decodeCloud(received[0].cloud,1)],[1,2,3,0.5,0.5,1]);
});
test('zero-payload states complete immediately and reset',()=>{
  let count=0;
  const assembler=new PacketAssembler(()=>count++);
  for(let i=0;i<2;i++)assembler.receive(JSON.stringify({protocol_version:1,rgb_bytes:0,cloud_bytes:0,cloud_point_count:0}));
  assert.equal(count,2);
});
test('length mismatches and incomplete packets are rejected',()=>{
  const assembler=new PacketAssembler(()=>{});
  assembler.receive(JSON.stringify({protocol_version:1,rgb_bytes:3,cloud_bytes:0,cloud_point_count:0}));
  assert.throws(()=>assembler.receive(new ArrayBuffer(2)),/length mismatch/);
  assert.throws(()=>assembler.receive('{}'),/Incomplete/);
  assert.throws(()=>decodeCloud(new Float32Array([Infinity,0,0,1,1,1]).buffer,1),/Nonfinite/);
});
test('measurements preserve missing values and timestamps',()=>{
  assert.equal(percentile([undefined,null,NaN],50),null);
  assert.equal(percentile([0,10,20],95),19);
  assert.equal(formatTime(65.25),'01:05.3');
});
