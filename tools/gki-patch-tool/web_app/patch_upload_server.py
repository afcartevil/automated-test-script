"""Temporary local HTTP server so remote hosts can curl/wget a patch file."""
from __future__ import annotations

import contextlib
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterator, List


def _local_candidate_ips() -> List[str]:
    ips: List[str] = []
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        ips.extend(a for a in addrs if a and not a.startswith("127."))
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        if ip and not ip.startswith("127."):
            ips.append(ip)
    except OSError:
        pass
    return list(dict.fromkeys(ips))


def _build_urls(host_ips: List[str], port: int, token: str, filename: str) -> List[str]:
    path = f"/{token}/{filename}"
    urls = [f"http://127.0.0.1:{port}{path}"]
    for ip in host_ips:
        urls.append(f"http://{ip}:{port}{path}")
    return list(dict.fromkeys(urls))


@contextlib.contextmanager
def serve_patch_temporarily(
    file_path: Path,
    *,
    port: int = 0,
    bind: str = "0.0.0.0",
) -> Iterator[Dict[str, object]]:
    """Serve a single file at /{token}/{filename}; yield {urls, port, token}."""
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))

    token = secrets.token_hex(8)
    filename = file_path.name
    expected_path = f"/{token}/{filename}"
    data = file_path.read_bytes()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != expected_path:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((bind, port), _Handler)
    server.daemon_threads = True
    actual_port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host_ips = _local_candidate_ips()
    info = {
        "urls": _build_urls(host_ips, actual_port, token, filename),
        "port": actual_port,
        "token": token,
        "filename": filename,
        "host_ips": host_ips,
    }
    try:
        yield info
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
