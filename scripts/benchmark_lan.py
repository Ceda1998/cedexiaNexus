"""NX-003: bounded two-host LAN test. Run with --help on each device."""

import argparse
import ipaddress
import json
import math
import os
import platform
import socket
import statistics
import subprocess
import sys
import time


PORT = 5201
SIZE = 64 * 1024**2
RUNS = 3
PING_COUNT = 20
RUN_TIMEOUT = 30
LISTENER_TIMEOUT = 300
LAN_RANGES = tuple(map(ipaddress.IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))


def lan_address(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Enter a private LAN IPv4 address.") from None
    if not any(address in network for network in LAN_RANGES):
        raise argparse.ArgumentTypeError("Only RFC 1918 LAN addresses are supported.")
    return str(address)


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError
    return seconds


def send(sock, data, deadline):
    sock.settimeout(remaining(deadline))
    sock.sendall(data)


def receive(sock, size, deadline):
    sock.settimeout(remaining(deadline))
    return sock.recv(size)


def send_payload(sock, size, block, deadline):
    while size:
        chunk = block[:size]
        send(sock, chunk, deadline)
        size -= len(chunk)


def receive_payload(sock, size, deadline):
    while size:
        chunk = receive(sock, min(size, 256 * 1024), deadline)
        if not chunk:
            raise ConnectionError("Peer closed before sending the complete payload.")
        size -= len(chunk)


def serve_transfer(sock, size, block, deadline):
    direction = receive(sock, 1, deadline)
    if direction == b"U":
        receive_payload(sock, size, deadline)
        send(sock, b"K", deadline)
    elif direction == b"D":
        send_payload(sock, size, block, deadline)
    else:
        raise ValueError("Invalid benchmark request.")


def listen(bind, peer, block):
    deadline = time.monotonic() + LISTENER_TIMEOUT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((bind, PORT))
        listener.listen(1)
        print("LAN listener ready. Start the Windows client now.", flush=True)
        completed = 0
        while completed < RUNS * 2:
            listener.settimeout(remaining(deadline))
            sock, (remote, _) = listener.accept()
            with sock:
                if remote != peer:
                    continue
                serve_transfer(sock, SIZE, block, min(deadline, time.monotonic() + RUN_TIMEOUT))
                completed += 1
                print(f"Transfer {completed}/{RUNS * 2} complete.", flush=True)


def ping_windows(peer):
    # Read only numeric RTTs. Windows ping.exe output depends on the OS language.
    command = (
        "$p = New-Object System.Net.NetworkInformation.Ping; "
        f"for ($i = 0; $i -lt {PING_COUNT}; $i++) {{ "
        f"try {{ $r = $p.Send('{peer}', 1000); "
        "if ($r.Status -eq 'Success') { $r.RoundtripTime } } catch {}; "
        "Start-Sleep -Milliseconds 200 }; $p.Dispose()"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, errors="replace", timeout=45, check=True,
    )
    return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]


def summarize_ping(samples):
    ordered = sorted(samples)
    return {
        "sent": PING_COUNT,
        "received": len(samples),
        "loss_percent": round(100 * (PING_COUNT - len(samples)) / PING_COUNT, 2),
        "median_ms": statistics.median(ordered) if ordered else None,
        "p95_ms": ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None,
        "sample_ms": samples,
    }


def measure_transfer(peer, direction, block):
    with socket.create_connection((peer, PORT), timeout=5) as sock:
        start = time.monotonic()
        deadline = start + RUN_TIMEOUT
        send(sock, direction, deadline)
        if direction == b"U":
            send_payload(sock, SIZE, block, deadline)
            if receive(sock, 1, deadline) != b"K":
                raise ConnectionError("Mac did not acknowledge the full upload.")
        else:
            receive_payload(sock, SIZE, deadline)
        return round(SIZE * 8 / (time.monotonic() - start) / 1_000_000, 2)


def client(args, block):
    if platform.system() != "Windows":
        raise ValueError("Run the client on Windows and the listener on the Mac.")
    ping = summarize_ping(ping_windows(args.peer))
    report = {
        "experiment_id": "NX-003-LAN",
        "windows_connection": args.windows_connection,
        "mac_connection": args.mac_connection,
        "windows_link_mbps": args.windows_link_mbps,
        "mac_link_mbps": args.mac_link_mbps,
        "ping_windows_to_mac": ping,
        "tcp_bytes_per_transfer": SIZE,
    }
    for direction, key in ((b"U", "windows_to_mac"), (b"D", "mac_to_windows")):
        samples = [measure_transfer(args.peer, direction, block) for _ in range(RUNS)]
        report[key] = {"samples_mbps": samples, "median_mbps": statistics.median(samples)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    server = modes.add_parser("listen", help="run the temporary listener on the Mac")
    server.add_argument("--bind", type=lan_address, required=True, help="Mac LAN IPv4")
    server.add_argument("--peer", type=lan_address, required=True, help="Windows LAN IPv4")
    runner = modes.add_parser("measure", help="run on Windows with the Mac listener active")
    runner.add_argument("--peer", type=lan_address, required=True, help="Mac LAN IPv4")
    for host in ("windows", "mac"):
        runner.add_argument(f"--{host}-connection", choices=("ethernet", "wi-fi"), required=True)
        runner.add_argument(f"--{host}-link-mbps", type=int)
    args = parser.parse_args()
    if args.mode == "measure" and any(
        value is not None and value <= 0 for value in (args.windows_link_mbps, args.mac_link_mbps)
    ):
        parser.error("Link rates must be positive.")
    block = os.urandom(256 * 1024)
    try:
        if args.mode == "listen":
            listen(args.bind, args.peer, block)
        else:
            print(json.dumps(client(args, block), indent=2))
    except TimeoutError:
        print("LAN test timed out. Check the peer, link, and firewall settings.", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError, ValueError):
        print("LAN test failed. Check the LAN addresses, TCP port 5201, and PowerShell.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
