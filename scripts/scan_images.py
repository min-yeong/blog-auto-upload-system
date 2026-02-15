#!/usr/bin/env python3
"""바탕화면 이미지 스캔: ~/Desktop에서 이미지 파일 탐색 및 목록 반환."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.utils.image_utils import get_image_info, HEIF_SUPPORTED

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif"}
DESKTOP_PATH = Path.home() / "Desktop"


def scan_desktop_images(
    directory: str | None = None,
    max_age_hours: int | None = None,
    sort_by: str = "modified",
) -> list[dict]:
    """바탕화면(또는 지정 디렉토리)에서 이미지 파일 스캔.

    Args:
        directory: 스캔할 디렉토리 (기본: ~/Desktop)
        max_age_hours: 최근 N시간 이내 파일만 (None=전체)
        sort_by: 정렬 기준 ("modified", "name", "size")

    Returns:
        이미지 정보 딕셔너리 리스트
    """
    scan_dir = Path(directory) if directory else DESKTOP_PATH

    if not scan_dir.exists():
        print(f"[경고] 디렉토리가 존재하지 않습니다: {scan_dir}", file=sys.stderr)
        return []

    images = []
    now = datetime.now().timestamp()

    for f in scan_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if f.name.startswith("."):
            continue

        # HEIC 지원 여부 확인
        if f.suffix.lower() in (".heic", ".heif") and not HEIF_SUPPORTED:
            images.append({
                "path": str(f.resolve()),
                "filename": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "width": None,
                "height": None,
                "format": "HEIC",
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "note": "pillow-heif 미설치 - 변환 필요",
            })
            continue

        # 최근 N시간 필터
        if max_age_hours is not None:
            age_hours = (now - f.stat().st_mtime) / 3600
            if age_hours > max_age_hours:
                continue

        try:
            info = get_image_info(str(f))
            info["modified"] = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            images.append(info)
        except Exception as e:
            print(f"[경고] {f.name} 읽기 실패: {e}", file=sys.stderr)

    # 정렬
    if sort_by == "modified":
        images.sort(key=lambda x: x.get("modified", ""), reverse=True)
    elif sort_by == "name":
        images.sort(key=lambda x: x.get("filename", ""))
    elif sort_by == "size":
        images.sort(key=lambda x: x.get("size_kb", 0), reverse=True)

    return images


def main():
    import argparse

    parser = argparse.ArgumentParser(description="바탕화면 이미지 스캔")
    parser.add_argument("--dir", default=None, help="스캔할 디렉토리 (기본: ~/Desktop)")
    parser.add_argument("--hours", type=int, default=None, help="최근 N시간 이내 파일만")
    parser.add_argument("--sort", choices=["modified", "name", "size"], default="modified")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    args = parser.parse_args()

    images = scan_desktop_images(args.dir, args.hours, args.sort)

    if args.json:
        print(json.dumps(images, ensure_ascii=False, indent=2))
    else:
        if not images:
            print("이미지 파일이 없습니다.")
            return

        print(f"\n📸 발견된 이미지: {len(images)}개\n")
        for i, img in enumerate(images, 1):
            size = f"{img['size_kb']}KB"
            dims = f"{img.get('width', '?')}x{img.get('height', '?')}"
            mod = img.get("modified", "")[:16]
            note = f" ⚠️ {img['note']}" if "note" in img else ""
            print(f"  {i}. {img['filename']}  ({dims}, {size}, {mod}){note}")


if __name__ == "__main__":
    main()
