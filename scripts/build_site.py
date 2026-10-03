"""Assemble the published site in _site/: web/ at the root, plus data/ and config/.

Usage: python scripts/build_site.py [--out _site]
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILES = ("searches.json", "settings.json")


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    # Repo data/ (results, runs, spend) merges into web/data/ (airports.json).
    shutil.copytree(ROOT / "data", out / "data", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".gitkeep"))
    (out / "config").mkdir()
    for name in CONFIG_FILES:
        src = ROOT / "config" / name
        if src.exists():
            shutil.copy2(src, out / "config" / name)
    (out / ".nojekyll").touch()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    a = p.parse_args()
    build(a.out)
    files = sum(1 for f in a.out.rglob("*") if f.is_file())
    print(f"Built {a.out} ({files} files)")
