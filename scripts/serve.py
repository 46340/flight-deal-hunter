"""Local preview server that mimics the published site layout.

The site serves web/ at the root, with the repo's data/ and config/ next to it.
Usage: python scripts/serve.py [port]   then open http://localhost:8000
"""

from __future__ import annotations

import http.server
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        rel = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if rel.startswith("config/"):
            return str(ROOT / rel)
        if rel.startswith("data/") and (ROOT / rel).exists():
            return str(ROOT / rel)
        return str(ROOT / "web" / (rel or "index.html"))

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Serving on http://localhost:{port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
