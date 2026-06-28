#!/usr/bin/env python3
"""Print image inventory for an OpenClaw blog upload session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def orientation(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def image_info(path: Path) -> dict:
    with Image.open(path) as raw:
        transposed = ImageOps.exif_transpose(raw)
        return {
            "path": str(path.resolve()),
            "filename": path.name,
            "width": transposed.width,
            "height": transposed.height,
            "orientation": orientation(transposed.width, transposed.height),
            "format": raw.format or path.suffix.upper().strip("."),
            "size_kb": round(path.stat().st_size / 1024, 1),
        }


def resolve_images_dir(session: str) -> Path:
    raw = Path(session)
    session_root = raw if raw.is_absolute() else PROJECT_ROOT / raw
    if raw.name == session and not session_root.exists():
        session_root = PROJECT_ROOT / "openclaw_sessions" / session
    images_dir = session_root / "images"
    if not images_dir.is_dir():
        raise SystemExit(f"images directory not found: {images_dir}")
    return images_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze session images")
    parser.add_argument("session", help="Session id or openclaw_sessions/<id> path")
    args = parser.parse_args()

    images_dir = resolve_images_dir(args.session)
    paths = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
    )
    data = {
        "images_dir": str(images_dir.resolve()),
        "count": len(paths),
        "images": [image_info(p) for p in paths],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
