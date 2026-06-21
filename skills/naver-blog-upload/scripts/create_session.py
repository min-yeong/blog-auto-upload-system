#!/usr/bin/env python3
"""Create an OpenClaw blog upload session folder."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SESSIONS_ROOT = PROJECT_ROOT / "openclaw_sessions"


def main() -> None:
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = SESSIONS_ROOT / session_id
    (root / "images").mkdir(parents=True, exist_ok=True)
    meta = {
        "id": session_id,
        "path": str(root.resolve()),
        "images": str((root / "images").resolve()),
        "post": str((root / "post.json").resolve()),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (root / "session.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
