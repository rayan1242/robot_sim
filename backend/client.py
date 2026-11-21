"""Command-line stream check; trigger recording/replay using the API separately."""
import argparse
import asyncio
import json


async def stream(url, frames):
    import websockets
    count = 0
    async with websockets.connect(url, max_size=4*1024*1024) as socket:
        while count < frames:
            header = json.loads(await socket.recv())
            for key in ("rgb_bytes", "cloud_bytes"):
                if header.get(key):
                    payload = await socket.recv()
                    if not isinstance(payload, bytes) or len(payload) != header[key]:
                        raise ValueError("Binary payload does not match header")
            print(json.dumps({k:header.get(k) for k in ("session_id", "mode", "state", "sequence", "timestamp", "cloud_point_count", "subscriber_skipped_updates")}))
            count += 1
            if header.get("state") in ("completed", "error"):
                return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/live")
    parser.add_argument("--frames", type=int, default=10)
    args = parser.parse_args()
    if args.frames < 1:
        parser.error("frames must be positive")
    asyncio.run(stream(args.url, args.frames))
