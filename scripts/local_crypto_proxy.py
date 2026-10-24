#!/usr/bin/env python3
"""Minimal HTTP CONNECT proxy bound to the Tailscale interface.

Why this exists: Binance answers HTTP 451 to the VPS region, but the local
connection is allowed. The cloud container sends its crypto traffic through a
Tailscale relay to this proxy, so egress happens from this machine.

Only CONNECT tunnels are implemented (that is all HTTPS needs), and the socket
binds to the tailnet address by default so nothing on the LAN or the internet
can use it. There is no authentication: the tailnet is the trust boundary.

Usage:
    python3 scripts/local_crypto_proxy.py                 # bind 100.x.y.z:3128
    LOCAL_PROXY_BIND=127.0.0.1 LOCAL_PROXY_PORT=3128 python3 scripts/local_crypto_proxy.py
"""

import asyncio
import os
import socket
import sys

BIND = os.getenv("LOCAL_PROXY_BIND", "")
PORT = int(os.getenv("LOCAL_PROXY_PORT", "3128"))
IDLE_TIMEOUT = float(os.getenv("LOCAL_PROXY_TIMEOUT", "600"))


def tailnet_address():
    """Return the first IPv4 address of the tailscale interface, if any."""
    for _, name in socket.if_nameindex():
        if not name.startswith("tailscale"):
            continue
        try:
            out = os.popen(f"ip -4 -o addr show dev {name}").read()
        except OSError:
            continue
        for token in out.split():
            if token.count(".") == 3 and "/" in token:
                return token.split("/")[0]
    return None


async def pipe(reader, writer):
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(reader, writer):
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=15)
        if not request_line:
            return
        parts = request_line.decode("latin-1").split()
        if len(parts) < 2:
            return
        method, target = parts[0], parts[1]
        # Drain the request headers.
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=15)
            if line in (b"\r\n", b"\n", b""):
                break

        if method != "CONNECT":
            writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            await writer.drain()
            return

        host, _, port = target.rpartition(":")
        if not host or not port.isdigit():
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            return

        remote_reader, remote_writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port)), timeout=20
        )
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        print(f"CONNECT {host}:{port}", flush=True)

        await asyncio.gather(
            pipe(reader, remote_writer),
            pipe(remote_reader, writer),
        )
    except Exception as exc:  # pragma: no cover - network errors
        print(f"proxy error: {exc}", file=sys.stderr, flush=True)
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    bind = BIND or tailnet_address()
    if not bind:
        print("No tailscale address found. Set LOCAL_PROXY_BIND explicitly.", file=sys.stderr)
        return 1
    server = await asyncio.start_server(handle, bind, PORT)
    print(f"Crypto proxy listening on {bind}:{PORT} (CONNECT only)", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
