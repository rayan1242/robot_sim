export function decodeCloud(buffer, count) {
  if (!(buffer instanceof ArrayBuffer) || !Number.isInteger(count) || count < 0 || count > 5000 || buffer.byteLength !== count * 24) throw new Error('Invalid point-cloud payload');
  const view = new DataView(buffer);
  const values = new Float32Array(count * 6);
  for (let i = 0; i < values.length; i++) {
    const value = view.getFloat32(i * 4, true);
    if (!Number.isFinite(value) || (i % 6 >= 3 && (value < 0 || value > 1))) throw new Error('Nonfinite geometry or invalid RGB values');
    values[i] = value;
  }
  return values;
}

export class PacketAssembler {
  constructor(onPacket) { this.onPacket = onPacket; this.reset(); }
  reset() { this.header = null; this.pending = []; this.rgb = null; this.cloud = null; }
  receive(data) {
    if (typeof data === 'string') {
      if (this.header) throw new Error('Incomplete stream update');
      const header = JSON.parse(data);
      if (header.protocol_version !== 1) throw new Error('Unsupported stream version');
      for (const field of ['rgb_bytes', 'cloud_bytes']) if (!Number.isInteger(header[field]) || header[field] < 0 || header[field] > 8 * 1024 * 1024) throw new Error('Invalid payload length');
      if (header.cloud_bytes !== (header.cloud_point_count || 0) * 24 || header.cloud_point_count > 5000) throw new Error('Invalid geometry header');
      this.header = header;
      if (header.rgb_bytes) this.pending.push('rgb');
      if (header.cloud_bytes) this.pending.push('cloud');
    } else {
      if (!(data instanceof ArrayBuffer) || !this.header || !this.pending.length) throw new Error('Unexpected binary message');
      const kind = this.pending.shift();
      if (data.byteLength !== this.header[`${kind}_bytes`]) throw new Error('Payload length mismatch');
      this[kind] = data;
    }
    if (this.header && !this.pending.length) {
      const update = { header: this.header, rgb: this.rgb, cloud: this.cloud };
      this.reset();
      this.onPacket(update);
    }
  }
}

export function percentile(values, p) {
  const sorted = values.filter(Number.isFinite).sort((a,b) => a-b);
  if (!sorted.length) return null;
  const index = (sorted.length - 1) * p / 100;
  const lo = Math.floor(index), hi = Math.ceil(index);
  return sorted[lo] + (sorted[hi]-sorted[lo])*(index-lo);
}

export function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return '00:00.0';
  const value = Math.max(0, seconds);
  return `${String(Math.floor(value/60)).padStart(2,'0')}:${(value%60).toFixed(1).padStart(4,'0')}`;
}
