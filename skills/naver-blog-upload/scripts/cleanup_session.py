#!/usr/bin/env python3
"""Safely remove a repo-local OpenClaw blog upload session."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SESSIONS_ROOT = (PROJECT_ROOT / "openclaw_sessions").resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean a blog upload session folder")
    parser.add_argument("session", help="Session id or openclaw_sessions/<id> path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    raw = Path(args.session)
    target = raw if raw.is_absolute() else PROJECT_ROOT / raw
    if raw.name == args.session and not target.exists():
        target = SESSIONS_ROOT / args.session
    target = target.resolve()

    if SESSIONS_ROOT not in [target, *target.parents]:
        raise SystemExit(f"refusing to delete outside {SESSIONS_ROOT}: {target}")
    if target == SESSIONS_ROOT:
        raise SystemExit("refusing to delete the sessions root")
    if not target.exists():
        print(f"already clean: {target}")
        return
    if not target.is_dir():
        raise SystemExit(f"not a directory: {target}")

    if args.dry_run:
        print(f"would remove: {target}")
        return

    shutil.rmtree(target)
    print(f"removed: {target}")


if __name__ == "__main__":
    main()
