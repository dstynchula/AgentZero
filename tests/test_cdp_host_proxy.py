import socket
import threading
import time
from unittest.mock import patch

from agentzero.scrape.cdp_host_proxy import (
    chrome_debug_port,
    expose_for_docker_enabled,
    rewrite_cdp_request_headers,
    run_cdp_host_proxy,
    stop_cdp_host_proxy,
)


def test_chrome_debug_port_with_docker_expose():
    assert chrome_debug_port(9222, expose_for_docker=True) == 9223
    assert chrome_debug_port(9222, expose_for_docker=False) == 9222


def test_rewrite_host_and_origin_for_chrome():
    block = (
        b"GET /json/version HTTP/1.1\r\n"
        b"Host: host.docker.internal:9222\r\n"
        b"Origin: http://host.docker.internal:9222\r\n"
        b"\r\n"
    )
    out = rewrite_cdp_request_headers(block, target_port=9223)
    assert b"Host: 127.0.0.1:9223" in out
    assert b"Origin: http://127.0.0.1:9223" in out
    assert b"host.docker.internal" not in out


def test_stop_cdp_host_proxy_targets_marker():
    with patch("agentzero.scrape.cdp_host_proxy._pids_listening_on_port", return_value=[111, 222]):
        with patch(
            "agentzero.scrape.cdp_host_proxy._process_command_line",
            side_effect=[
                "python -m agentzero.scrape.cdp_host_proxy --listen-port 9222",
                "chrome.exe",
            ],
        ):
            with patch("agentzero.scrape.cdp_host_proxy.subprocess.run") as run:
                assert stop_cdp_host_proxy(listen_port=9222) == 1
                assert run.call_count == 1


def test_expose_for_docker_env(monkeypatch):
    monkeypatch.setenv("AGENTZERO_CDP_EXPOSE_FOR_DOCKER", "false")
    assert expose_for_docker_enabled() is False
    assert expose_for_docker_enabled(True) is True


def test_proxy_forwards_to_target():
    body = b"HTTP/1.0 200 OK\r\n\r\nok"
    ready = threading.Event()
    target_port_holder: dict[str, int] = {}

    def echo_server() -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        target_port_holder["port"] = srv.getsockname()[1]
        ready.set()
        conn, _ = srv.accept()
        conn.recv(4096)
        conn.sendall(body)
        conn.close()
        srv.close()

    threading.Thread(target=echo_server, daemon=True).start()
    assert ready.wait(timeout=2.0)
    target_port = target_port_holder["port"]

    bind_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bind_probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bind_probe.bind(("127.0.0.1", 0))
    listen_port = bind_probe.getsockname()[1]
    bind_probe.close()

    threading.Thread(
        target=run_cdp_host_proxy,
        kwargs={
            "listen_host": "127.0.0.1",
            "listen_port": listen_port,
            "target_host": "127.0.0.1",
            "target_port": target_port,
        },
        daemon=True,
    ).start()
    time.sleep(0.05)

    client = socket.create_connection(("127.0.0.1", listen_port), timeout=2.0)
    client.sendall(b"GET / HTTP/1.0\r\n\r\n")
    data = client.recv(256)
    client.close()
    assert b"ok" in data
