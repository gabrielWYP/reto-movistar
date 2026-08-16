"""Local-only static frontend and reverse proxy used by the Windows launcher."""

from __future__ import annotations

import argparse
import http.client
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def create_server(front_dir: Path, host: str, port: int, backend_host: str, backend_port: int) -> ThreadingHTTPServer:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(front_dir), **kwargs)

        def _proxy(self) -> None:
            connection: http.client.HTTPConnection | None = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else None
                connection = http.client.HTTPConnection(backend_host, backend_port, timeout=60)
                headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "connection"}}
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception:
                payload = b'{"error":"Backend no disponible."}'
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            finally:
                if connection:
                    connection.close()

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health" or self.path.startswith("/api/"):
                self._proxy()
            else:
                super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            self._proxy()

        def do_DELETE(self) -> None:  # noqa: N802
            self._proxy()

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"front {self.address_string()} {fmt % args}")

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Frontend local SON-IA Billing")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8503)
    parser.add_argument("--backend-host", default=os.getenv("BACKEND_HOST", "127.0.0.1"))
    parser.add_argument("--backend-port", type=int, default=int(os.getenv("BACKEND_PORT", "8080")))
    args = parser.parse_args()
    server = create_server(Path(__file__).resolve().parent, args.host, args.port, args.backend_host, args.backend_port)
    print(f"SON-IA Billing FRONT en http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
