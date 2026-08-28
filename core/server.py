"""
Local application server.

    python -m core.server            # http://localhost:8765

Serves the web app and accepts documents. Ingestion is the difference between
a fixture and a tool: you can hand it a manual it has never seen and get a
world back, without touching a terminal.

The upload body is the raw PDF with the name in an X-Filename header, rather
than multipart -- the stdlib cgi module was removed in Python 3.13 and hand
parsing multipart to save a few bytes is not a good trade.
"""

from __future__ import annotations

import json
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.pipeline import LIBRARY, WEB, read_manifest, run

UPLOADS = Path(__file__).resolve().parents[1] / "data" / "uploads"
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
PDF_MAGIC = b"%PDF-"


def safe_filename(raw: str) -> str:
    """Basename only, conservative charset, forced .pdf.

    An upload filename is attacker-controlled: it must never be able to escape
    the uploads directory or land as something executable.
    """
    name = Path(raw.replace("\\", "/")).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._-")
    return f"{(stem or 'document')[:80]}.pdf"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)

    def end_headers(self):
        # Browsers cache ES modules hard. On a local install that means an edit
        # silently does nothing until a manual cache clear, which is a very bad
        # surprise to hit mid-demonstration.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/ingest":
            return self._json(404, {"error": "no such endpoint"})

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        if length <= 0:
            return self._json(400, {"error": "empty upload"})
        if length > MAX_UPLOAD_BYTES:
            return self._json(413, {"error": f"file exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB"})

        data = self.rfile.read(length)
        if not data.startswith(PDF_MAGIC):
            return self._json(415, {"error": "that file is not a PDF"})

        name = safe_filename(self.headers.get("X-Filename", "document.pdf"))
        UPLOADS.mkdir(parents=True, exist_ok=True)
        target = UPLOADS / name
        target.write_bytes(data)

        title = self.headers.get("X-Title") or None
        try:
            run(target, title, None, False)
        except Exception as e:                     # a bad document must not kill the server
            return self._json(500, {"error": f"extraction failed: {e}"})

        entry = next((e for e in read_manifest() if e["source"] == name), None)
        if entry is None:
            return self._json(500, {"error": "document produced no library entry"})
        if not entry["steps"]:
            entry["warning"] = (
                "No numbered procedure steps were found. This extractor looks for "
                "lines like '7. Fit the piston...'."
            )
        return self._json(200, entry)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    LIBRARY.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Crucivex on http://localhost:{port}  (serving {WEB})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
