"""이미지 유틸리티: HEIC→JPEG 변환, 리사이즈"""

import os
from pathlib import Path
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

MAX_WIDTH = 1600
MAX_HEIGHT = 1200
JPEG_QUALITY = 85


def convert_heic_to_jpeg(heic_path: str, output_dir: str | None = None) -> str:
    """HEIC 파일을 JPEG로 변환. 변환된 파일 경로 반환."""
    if not HEIF_SUPPORTED:
        raise RuntimeError("pillow-heif 패키지가 필요합니다: pip install pillow-heif")

    path = Path(heic_path)
    if output_dir:
        out = Path(output_dir) / f"{path.stem}.jpeg"
    else:
        out = path.with_suffix(".jpeg")

    img = Image.open(heic_path)
    img = img.convert("RGB")
    img.save(str(out), "JPEG", quality=JPEG_QUALITY)
    return str(out)


def resize_image(image_path: str, max_width: int = MAX_WIDTH, max_height: int = MAX_HEIGHT) -> str:
    """이미지를 최대 크기 내로 리사이즈. 원본 파일 덮어쓰기."""
    img = Image.open(image_path)
    if img.width <= max_width and img.height <= max_height:
        return image_path

    img.thumbnail((max_width, max_height), Image.LANCZOS)
    img.save(image_path, quality=JPEG_QUALITY)
    return image_path


def prepare_image(image_path: str, output_dir: str | None = None) -> str:
    """이미지를 업로드 가능한 형태로 준비 (HEIC 변환 + 리사이즈)."""
    path = Path(image_path)
    ext = path.suffix.lower()

    if ext in (".heic", ".heif"):
        image_path = convert_heic_to_jpeg(image_path, output_dir)

    return resize_image(image_path)


def stitch_images_horizontally(
    image_paths: list[str],
    output_path: str,
    gap: int = 10,
    max_height: int = 800,
    bg_color: tuple = (255, 255, 255),
) -> str:
    """여러 이미지를 가로로 합쳐서 한 장으로 만듦.

    Args:
        image_paths: 합칠 이미지 경로 리스트
        output_path: 저장할 경로
        gap: 이미지 사이 간격 (px)
        max_height: 합친 이미지의 최대 높이
        bg_color: 배경색 (흰색)

    Returns:
        저장된 파일 경로
    """
    if len(image_paths) < 2:
        return image_paths[0] if image_paths else ""

    images = []
    for p in image_paths:
        img = Image.open(p)
        img = ImageOps.exif_transpose(img)  # EXIF 회전 정보 적용
        img = img.convert("RGB")
        images.append(img)

    # 모든 이미지를 동일 높이로 리사이즈 (가장 작은 높이 기준, max_height 이내)
    target_h = min(img.height for img in images)
    target_h = min(target_h, max_height)

    resized = []
    for img in images:
        ratio = target_h / img.height
        new_w = int(img.width * ratio)
        resized.append(img.resize((new_w, target_h), Image.LANCZOS))

    # 캔버스 크기 계산
    total_w = sum(img.width for img in resized) + gap * (len(resized) - 1)
    canvas = Image.new("RGB", (total_w, target_h), bg_color)

    # 이미지 붙이기
    x_offset = 0
    for img in resized:
        canvas.paste(img, (x_offset, 0))
        x_offset += img.width + gap

    canvas.save(output_path, "JPEG", quality=JPEG_QUALITY)
    return output_path


def get_image_info(image_path: str) -> dict:
    """이미지 기본 정보 반환."""
    path = Path(image_path)
    img = Image.open(image_path)
    return {
        "path": str(path.resolve()),
        "filename": path.name,
        "size_kb": round(path.stat().st_size / 1024, 1),
        "width": img.width,
        "height": img.height,
        "format": img.format or path.suffix.upper().strip("."),
    }
