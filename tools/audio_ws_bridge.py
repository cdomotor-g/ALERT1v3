#!/usr/bin/env python3
import argparse
import asyncio
import os
import signal

import websockets


async def pcm_producer(clients, arecord_dev: str, rate: int, chunk_samples: int):
    cmd = [
        "arecord",
        "-D", arecord_dev,
        "-f", "S16_LE",
        "-c", "1",
        "-r", str(rate),
        "-t", "raw",
        "-q",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    chunk_bytes = chunk_samples * 2
    try:
        while True:
            buf = await proc.stdout.readexactly(chunk_bytes)
            if not clients:
                continue
            stale = []
            for ws in list(clients):
                try:
                    await ws.send(buf)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                clients.discard(ws)
    except asyncio.IncompleteReadError:
        pass
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()


async def main():
    ap = argparse.ArgumentParser(description="PCM audio websocket bridge")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--arecord-device", default=os.environ.get("FWLAB_ARECORD_DEVICE", "hw:Loopback,1,0"))
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--chunk-samples", type=int, default=960, help="20ms at 48k")
    args = ap.parse_args()

    clients = set()

    async def handler(ws):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, args.host, args.port, max_size=2**20):
        task = asyncio.create_task(pcm_producer(clients, args.arecord_device, args.rate, args.chunk_samples))
        stop = asyncio.Event()

        def _sig(*_):
            stop.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _sig)

        await stop.wait()
        task.cancel()
        with contextlib.suppress(Exception):
            await task


if __name__ == "__main__":
    import contextlib
    asyncio.run(main())
