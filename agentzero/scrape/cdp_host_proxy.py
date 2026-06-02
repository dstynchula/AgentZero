"""TCP proxy so Docker can reach Chrome CDP bound to 127.0.0.1 only."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import threading
from pathlib import Path

_HEADER_END = b"\r\n\r\n"
_MAX_HTTP_HEADERS = 65536


def rewrite_cdp_request_headers(block: bytes, *, target_port: int) -> bytes:
    """Chrome rejects Host values that are not localhost or an IP (e.g. host.docker.internal)."""
    if _HEADER_END not in block:
        return block
    head, rest = block.split(_HEADER_END, 1)
    lines = head.split(b"\r\n")
    out: list[bytes] = []
    for line in lines:
        lower = line.lower()
        if lower.startswith(b"host:"):
            out.append(f"Host: 127.0.0.1:{target_port}".encode())
        elif lower.startswith(b"origin:"):
            out.append(f"Origin: http://127.0.0.1:{target_port}".encode())
        else:
            out.append(line)
    return b"\r\n".join(out) + _HEADER_END + rest


def _read_http_headers(sock: socket.socket) -> bytes:
    buf = b""
    while _HEADER_END not in buf and len(buf) < _MAX_HTTP_HEADERS:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def _forward(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            src.close()
        except OSError:
            pass


def _handle_client(
    client: socket.socket,
    *,
    target_host: str,
    target_port: int,
) -> None:
    try:
        remote = socket.create_connection((target_host, target_port), timeout=5.0)
    except OSError:
        client.close()
        return
    initial = _read_http_headers(client)
    if initial:
        remote.sendall(rewrite_cdp_request_headers(initial, target_port=target_port))
    t_back = threading.Thread(target=_forward, args=(remote, client), daemon=True)
    t_back.start()
    _forward(client, remote)
    t_back.join(timeout=300.0)
    for sock in (client, remote):
        try:
            sock.close()
        except OSError:
            pass


def run_cdp_host_proxy(
    *,
    listen_host: str,
    listen_port: int,
    target_host: str,
    target_port: int,
) -> None:
    """Listen on *listen_host*:*listen_port* and forward to the CDP target."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((listen_host, listen_port))
    except OSError as exc:
        raise OSError(
            f"Cannot bind CDP proxy on {listen_host}:{listen_port}: {exc}. "
            "Stop other processes using that port or restart Chrome via launch_chrome_cdp."
        ) from exc
    server.listen(64)
    while True:
        client, _addr = server.accept()
        threading.Thread(
            target=_handle_client,
            args=(client,),
            kwargs={"target_host": target_host, "target_port": target_port},
            daemon=True,
        ).start()


def _process_command_line(pid: int) -> str:
    if sys.platform == "win32":
        result = subprocess.run(  # noqa: S603
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout or ""
    proc = Path(f"/proc/{pid}/cmdline")
    if proc.is_file():
        return proc.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace")
    return ""


def _pids_listening_on_port(port: int) -> list[int]:
    if sys.platform == "win32":
        result = subprocess.run(  # noqa: S603
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        )
        pids: list[int] = []
        token = f":{port}"
        for line in result.stdout.splitlines():
            if "LISTENING" not in line or token not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pids.append(int(parts[-1]))
            except ValueError:
                continue
        return pids
    result = subprocess.run(  # noqa: S603
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [int(pid) for pid in result.stdout.split() if pid.strip().isdigit()]


def stop_cdp_host_proxy(*, listen_port: int) -> int:
    """Stop proxy process(es) bound to *listen_port*; returns count terminated."""
    marker = "agentzero.scrape.cdp_host_proxy"
    stopped = 0
    for pid in dict.fromkeys(_pids_listening_on_port(listen_port)):
        cmd = _process_command_line(pid)
        if marker not in cmd or f"--listen-port {listen_port}" not in cmd.replace("=", " "):
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(  # noqa: S603
                    ["taskkill", "/PID", str(pid), "/F"],
                    check=False,
                    capture_output=True,
                )
            else:
                subprocess.run(["kill", str(pid)], check=False, capture_output=True)  # noqa: S603
            stopped += 1
        except OSError:
            continue
    return stopped


def start_cdp_host_proxy_process(
    *,
    listen_port: int,
    target_port: int,
    listen_host: str = "0.0.0.0",
    target_host: str = "127.0.0.1",
) -> subprocess.Popen[bytes]:
    """Start a detached proxy process (survives after the launch script exits)."""
    stop_cdp_host_proxy(listen_port=listen_port)
    return subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "agentzero.scrape.cdp_host_proxy",
            "--listen-host",
            listen_host,
            "--listen-port",
            str(listen_port),
            "--target-host",
            target_host,
            "--target-port",
            str(target_port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def expose_for_docker_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    import os

    raw = os.environ.get("AGENTZERO_CDP_EXPOSE_FOR_DOCKER", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def chrome_debug_port(expose_port: int, *, expose_for_docker: bool) -> int:
    """Port Chrome listens on; public/probe port may differ when a proxy is used."""
    return expose_port + 1 if expose_for_docker else expose_port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Forward CDP so host.docker.internal can reach Chrome on 127.0.0.1.",
    )
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        run_cdp_host_proxy(
            listen_host=args.listen_host,
            listen_port=args.listen_port,
            target_host=args.target_host,
            target_port=args.target_port,
        )
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
