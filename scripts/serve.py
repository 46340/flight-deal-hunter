"""Local preview server that mimics the published site layout.

The site serves web/ at the root, with the repo's data/ and config/ next to it.
Usage: python scripts/serve.py [--port 8000] [--data DIR] [--config DIR]
then open http://localhost:8000. --data/--config let you preview mock runs
without touching the repo's files.
"""

from __future__ import annotations

import argparse
import http.server
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make_handler(data_dir: Path, config_dir: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            rel = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
            if ".." in Path(rel).parts:
                return str(ROOT / "web" / "404")
            if rel.startswith("config/"):
                return str(config_dir / rel.removeprefix("config/"))
            if rel.startswith("data/") and (data_dir / rel.removeprefix("data/")).exists():
                return str(data_dir / rel.removeprefix("data/"))
            return str(ROOT / "web" / (rel or "index.html"))

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    return Handler


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--data", type=Path, default=ROOT / "data")
    p.add_argument("--config", type=Path, default=ROOT / "config")
    a = p.parse_args()
    print(f"Serving on http://localhost:{a.port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(a.data.resolve(), a.config.resolve())).serve_forever()
