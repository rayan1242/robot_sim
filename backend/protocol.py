"""Each packet: JSON header, optional JPEG bytes, optional little-endian float32 Nx6 cloud."""
import numpy as np
import io


def encode_cloud(path, limit=5000):
    if path is None or not path.exists():
        return b"", 0
    # Release the Windows file handle before ZIP decompression and validation.
    with np.load(io.BytesIO(path.read_bytes()), allow_pickle=False) as cloud:
        points = cloud["points"]
        colors = cloud["rgb"]
    return encode_cloud_arrays(points,colors,limit)


def encode_cloud_arrays(points,colors,limit=5000):
    if points.ndim != 2 or points.shape[1] != 3 or colors.shape != points.shape or not np.isfinite(points).all():
        raise ValueError("Invalid point cloud")
    indices = np.linspace(0, len(points)-1, min(len(points), limit), dtype=int)
    data = np.column_stack((points[indices], colors[indices]/255)).astype("<f4")
    return data.tobytes(), len(indices)


def packet(state, jpeg=b"", cloud=b"", point_count=0):
    return ({"protocol_version": 1, **state, "rgb_bytes": len(jpeg),
             "cloud_bytes": len(cloud), "cloud_point_count": point_count,
             "cloud_format": "float32-le xyzrgb; RGB normalized to 0..1",
             "cloud_semantics": state.get('cloud_semantics',"final_static_snapshot" if cloud else None)}, jpeg, cloud)
