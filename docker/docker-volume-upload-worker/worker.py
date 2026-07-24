from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path("/data")
TOKEN = os.environ.get("UPLOAD_TOKEN", "")
CHUNK_SIZE = 16 * 1024 * 1024


def safe_relative_path(value: str) -> str:
    raw = unquote(value or "").replace("\\", "/").strip("/")
    path = PurePosixPath(raw)
    if not raw or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Invalid destination path")
    return str(path)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"detail": "Not found"})

    def do_POST(self) -> None:
        if not TOKEN or self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._json(401, {"detail": "Unauthorized"})
            return
        parsed = urlparse(self.path)
        if parsed.path != "/upload":
            self._json(404, {"detail": "Not found"})
            return
        try:
            query = parse_qs(parsed.query)
            relative = safe_relative_path(query.get("path", [""])[0])
            overwrite = query.get("overwrite", ["false"])[0].lower() == "true"
            length_text = self.headers.get("Content-Length")
            if not length_text or not re.fullmatch(r"\d+", length_text):
                raise ValueError("Content-Length is required")
            remaining = int(length_text)
            destination = ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not overwrite:
                self._json(409, {"detail": "Destination already exists"})
                return
            staging = destination.with_name(
                f".{destination.name}.uploading-{uuid.uuid4().hex[:10]}"
            )
            written = 0
            try:
                with staging.open("wb", buffering=CHUNK_SIZE) as output:
                    while remaining:
                        chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            raise ConnectionError("Upload ended before Content-Length")
                        output.write(chunk)
                        written += len(chunk)
                        remaining -= len(chunk)
                    output.flush()
                os.replace(staging, destination)
            except Exception:
                staging.unlink(missing_ok=True)
                raise
            self._json(200, {"success": True, "path": relative, "size": written})
        except ValueError as exc:
            self._json(400, {"detail": str(exc)})
        except Exception as exc:
            self._json(500, {"detail": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        print(f"[upload-worker] {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8765), Handler)
    server.serve_forever()
