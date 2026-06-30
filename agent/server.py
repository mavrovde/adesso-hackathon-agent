"""Simple HTTP server exposing the coordinator as a REST endpoint.

Usage:
    python -m agent.server          # default port 8765
    python -m agent.server --port 9000
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

_REPO_ROOT = pathlib.Path(__file__).parent.parent

from agent.coordinator import run_coordinator
from agent.tools.mock_store import USERS

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": %(message)s}',
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict | list) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def _send_html(self, path: pathlib.Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/demo", "/demo.html"):
            html = _REPO_ROOT / "demo.html"
            if html.exists():
                self._send_html(html)
            else:
                self._send(404, {"error": "demo.html not found"})
        elif self.path == "/users":
            users = [
                {
                    "user_id": uid,
                    "name": u["name"],
                    "role": u["role"],
                    "department": u["department"],
                    "account_status": u["account_status"],
                    "vip": u["vip"],
                }
                for uid, u in USERS.items()
            ]
            self._send(200, users)
        elif self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/triage":
            self._send(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
            return

        request_text: str = body.get("input", "").strip()
        user_id: str | None = body.get("user_id") or None

        if not request_text:
            self._send(400, {"error": "input is required"})
            return

        logger.info(f"Triage request: user_id={user_id!r} input={request_text[:80]!r}")

        try:
            result = run_coordinator(request_text, user_id)
            self._send(200, result)
        except Exception as exc:
            logger.exception("Coordinator error")
            self._send(500, {"error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # suppress default access log; structured log above is enough


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(description="IT Helpdesk Triage Agent — HTTP Server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="localhost")
    args = parser.parse_args()

    server = ThreadedHTTPServer((args.host, args.port), Handler)
    logger.info(f"Server listening on http://{args.host}:{args.port}  →  Demo: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
