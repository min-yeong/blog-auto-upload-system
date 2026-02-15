#!/usr/bin/env python3
"""네이버 블로그 업로드: Playwright로 SmartEditor ONE 자동화.

기본 모드: 임시저장 (안전)
옵션: --publish로 발행

네이버 블로그 에디터는 iframe 없이 직접 페이지에 렌더링됨.
주요 셀렉터: div.se-title-text, div.se-component.se-text, div[contenteditable]
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.utils.naver_auth import ensure_login, BLOG_ID, NAVER_ID, NAVER_PW
from scripts.utils.image_utils import stitch_images_horizontally

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EDITOR_URL = f"https://blog.naver.com/{BLOG_ID}/postwrite"

# SmartEditor ONE 타임아웃 (ms)
EDITOR_LOAD_TIMEOUT = 20000
ACTION_DELAY = 500  # 액션 간 딜레이 (ms)


async def _auto_login_if_needed(page) -> None:
    """로그인 페이지로 리다이렉트된 경우 자동 로그인."""
    if "nidlogin" not in page.url:
        return

    print("  로그인 필요 - 자동 로그인 시도...")
    await page.evaluate(f'document.getElementById("id").value = "{NAVER_ID}"')
    await asyncio.sleep(0.3)
    await page.evaluate(f'document.getElementById("pw").value = "{NAVER_PW}"')
    await asyncio.sleep(0.3)

    login_btn = page.locator("#log\\.login")
    if await login_btn.count() == 0:
        login_btn = page.locator("button.btn_login")
    await login_btn.first.click()
    await asyncio.sleep(5)

    if "captcha" in page.url or "2step" in page.url:
        print("  ⚠️  캡차/2차인증 감지 - 브라우저에서 직접 완료해주세요")
        await page.wait_for_url(f"**/{BLOG_ID}/**", timeout=120000)


async def open_editor(page) -> None:
    """블로그 에디터 페이지 열기."""
    await page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=EDITOR_LOAD_TIMEOUT)
    await asyncio.sleep(3)

    # 로그인 리다이렉트 처리
    await _auto_login_if_needed(page)

    if "postwrite" not in page.url:
        await page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=EDITOR_LOAD_TIMEOUT)
        await asyncio.sleep(3)

    # 에디터 로드 대기 (iframe 없이 직접 접근)
    await page.wait_for_selector("div.se-component", timeout=EDITOR_LOAD_TIMEOUT)
    await asyncio.sleep(2)

    # "작성 중인 글이 있습니다" 팝업 처리 → 취소 (새 글 작성)
    cancel_btn = page.locator("div.se-popup-alert-confirm button:has-text('취소')")
    if await cancel_btn.count() > 0:
        await cancel_btn.first.click()
        await asyncio.sleep(1)
        print("  이전 임시저장 무시 (새 글 작성)")


async def set_title(page, title: str) -> None:
    """글 제목 입력."""
    import pyperclip

    # 제목 영역 클릭 (div를 먼저 시도 - span이 invisible일 수 있음)
    title_area = page.locator("div.se-title-text")
    await title_area.click()
    await asyncio.sleep(ACTION_DELAY / 1000)

    pyperclip.copy(title)
    await page.keyboard.press("Meta+a")
    await page.keyboard.press("Meta+v")
    await asyncio.sleep(ACTION_DELAY / 1000)


async def set_content(page, content: str) -> None:
    """본문 내용 입력."""
    import pyperclip

    # 본문 영역 클릭
    body_area = page.locator("p.se-text-paragraph")
    if await body_area.count() == 0:
        body_area = page.locator("div.se-component.se-text")
    if await body_area.count() == 0:
        body_area = page.locator("span.se-placeholder")

    await body_area.first.click()
    await asyncio.sleep(ACTION_DELAY / 1000)

    # 본문을 단락별로 입력
    paragraphs = content.split("\n")

    for i, para in enumerate(paragraphs):
        if para.strip():
            pyperclip.copy(para.strip())
            await page.keyboard.press("Meta+v")
        if i < len(paragraphs) - 1:
            await page.keyboard.press("Enter")
        await asyncio.sleep(0.1)

    await asyncio.sleep(ACTION_DELAY / 1000)


async def _type_text_block(page, text: str) -> None:
    """텍스트 블록 입력 (커서 위치에)."""
    import pyperclip

    paragraphs = text.split("\n")
    for i, para in enumerate(paragraphs):
        if para.strip():
            pyperclip.copy(para.strip())
            await page.keyboard.press("Meta+v")
        if i < len(paragraphs) - 1:
            await page.keyboard.press("Enter")
        await asyncio.sleep(0.1)
    await asyncio.sleep(ACTION_DELAY / 1000)


async def insert_place_widget(page, place_name: str) -> None:
    """네이버 지도 장소 위젯 삽입.

    에디터 툴바의 '장소' 버튼 → 장소 검색 → 결과 클릭 → 확인 순서로 동작.
    """
    if not place_name:
        return

    # 장소 버튼 찾기 (툴바 상단)
    place_btn = page.locator("button[data-name='place']")
    if await place_btn.count() == 0:
        place_btn = page.locator("button:has-text('장소')")

    if await place_btn.count() == 0:
        print("  [경고] 장소 버튼을 찾을 수 없습니다", file=sys.stderr)
        return

    try:
        await place_btn.first.click()
        await asyncio.sleep(2)

        # 장소 검색 입력
        search_input = page.locator("input[placeholder*='장소명']")
        if await search_input.count() == 0:
            search_input = page.locator("div.se-popup-placesMap input")

        if await search_input.count() == 0:
            print("  [경고] 장소 검색 입력창을 찾을 수 없습니다", file=sys.stderr)
            await _close_place_popup(page)
            return

        await search_input.first.fill(place_name)
        await asyncio.sleep(0.5)
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)

        # 검색 결과 항목에 hover → "추가" 버튼이 나타남 → 클릭
        clicked = False

        item_rect = await page.evaluate("""() => {
            const item = document.querySelector('li.se-place-map-search-result-item');
            if (!item) return null;
            const r = item.getBoundingClientRect();
            return r.width > 0 ? {x: r.x, y: r.y, w: r.width, h: r.height} : null;
        }""")

        if item_rect:
            # 1단계: 결과 항목 위로 마우스 이동 (hover)
            cx = item_rect["x"] + item_rect["w"] / 2
            cy = item_rect["y"] + item_rect["h"] / 2
            await page.mouse.move(cx, cy)
            await asyncio.sleep(1)

            # 2단계: hover 후 "추가" 버튼 좌표 다시 확인
            add_rect = await page.evaluate("""() => {
                const btn = document.querySelector('.se-place-map-search-add-button-text');
                if (!btn) return null;
                // 부모 button 요소의 좌표를 사용
                const parent = btn.closest('button') || btn;
                const r = parent.getBoundingClientRect();
                return r.width > 0 ? {x: r.x, y: r.y, w: r.width, h: r.height} : null;
            }""")

            if add_rect and add_rect["w"] > 0:
                # "추가" 버튼 클릭
                ax = add_rect["x"] + add_rect["w"] / 2
                ay = add_rect["y"] + add_rect["h"] / 2
                await page.mouse.click(ax, ay)
                clicked = True
                await asyncio.sleep(2)
            else:
                # "추가" 버튼이 안 보이면 결과 항목 자체를 클릭
                await page.mouse.click(cx, cy)
                clicked = True
                await asyncio.sleep(2)

        if not clicked:
            print("  ℹ️ 장소 검색 결과 클릭 실패 - 수동으로 추가해주세요")
            await _close_place_popup(page)
            return

        # "확인" 버튼 클릭 (결과 선택 후 활성화됨)
        confirm_btn = page.locator(
            "div.se-popup-placesMap button.se-popup-button-confirm"
        )
        try:
            # 확인 버튼이 enabled 될 때까지 대기
            await page.wait_for_selector(
                "div.se-popup-placesMap button.se-popup-button-confirm:not([disabled])",
                timeout=5000,
            )
            await confirm_btn.first.click()
            await asyncio.sleep(2)
            print(f"  📍 장소 삽입 완료: {place_name}")
            return
        except Exception:
            # 버튼이 여전히 disabled → bounding_box로 직접 클릭 시도
            try:
                box = await confirm_btn.first.bounding_box(timeout=3000)
                if box:
                    await page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                    )
                    await asyncio.sleep(2)
                    popup = page.locator("div.se-popup-placesMap")
                    if await popup.count() == 0 or not await popup.is_visible():
                        print(f"  📍 장소 삽입 완료: {place_name}")
                        return
            except Exception:
                pass

            print("  ℹ️ 장소 자동 삽입 실패 - 수동으로 추가해주세요")
            await _close_place_popup(page)

    except Exception as e:
        print(f"  [경고] 장소 삽입 실패: {e}", file=sys.stderr)
        await _close_place_popup(page)


async def _close_place_popup(page) -> None:
    """장소 팝업을 확실히 닫는 헬퍼."""
    try:
        # 방법 1: 닫기 버튼
        close_btn = page.locator("div.se-popup-placesMap button.se-popup-close-button")
        if await close_btn.count() > 0:
            await close_btn.first.click(force=True)
            await asyncio.sleep(1)
            return

        # 방법 2: JS로 팝업 제거
        await page.evaluate("""() => {
            const popup = document.querySelector('div.se-popup-placesMap');
            if (popup) popup.remove();
            // dim 레이어도 제거
            document.querySelectorAll('.se-popup-dim').forEach(el => el.remove());
        }""")
        await asyncio.sleep(0.5)
    except Exception:
        pass


async def _insert_image_block(page, img_path: str) -> None:
    """현재 커서 위치에 이미지 삽입."""
    if not Path(img_path).exists():
        print(f"  [경고] 이미지 파일 없음: {img_path}", file=sys.stderr)
        return

    # 툴바의 사진 버튼 클릭
    photo_btn = page.locator("button.se-image-toolbar-button")
    if await photo_btn.count() == 0:
        photo_btn = page.locator("button[data-name='image']")
    if await photo_btn.count() == 0:
        # 상단 툴바의 "사진" 텍스트 포함 버튼
        photo_btn = page.locator("button:has-text('사진')")

    if await photo_btn.count() > 0:
        await photo_btn.first.click()
        await asyncio.sleep(1)

        file_input = page.locator("input[type='file']")
        if await file_input.count() > 0:
            await file_input.first.set_input_files(img_path)
            await asyncio.sleep(3)

            insert_btn = page.locator("button.se-popup-button-confirm")
            if await insert_btn.count() > 0:
                await insert_btn.first.click()
                await asyncio.sleep(2)

    print(f"  📸 {Path(img_path).name}")


async def set_content_with_images(page, blocks: list[dict]) -> None:
    """텍스트와 이미지를 교차 입력.

    blocks 형식:
      [
        {"type": "text", "content": "글 내용..."},
        {"type": "image", "paths": ["/path/to/img1.jpeg", ...]},
        {"type": "text", "content": "다음 글 내용..."},
        ...
      ]
    """
    # 본문 영역 클릭
    body_area = page.locator("p.se-text-paragraph")
    if await body_area.count() == 0:
        body_area = page.locator("div.se-component.se-text")
    if await body_area.count() == 0:
        body_area = page.locator("span.se-placeholder")

    await body_area.first.click()
    await asyncio.sleep(ACTION_DELAY / 1000)

    for block in blocks:
        if block["type"] == "text":
            await _type_text_block(page, block["content"])
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.3)
        elif block["type"] == "image":
            paths = block.get("paths", [])
            valid_paths = [p for p in paths if Path(p).exists()]
            if len(valid_paths) >= 2:
                # 2장 이상이면 가로로 합쳐서 한 장으로 업로드
                combined_path = str(PROJECT_ROOT / "output" / f"combined_{id(block)}.jpeg")
                stitch_images_horizontally(valid_paths, combined_path)
                await _insert_image_block(page, combined_path)
                print(f"  🔗 이미지 {len(valid_paths)}장 합침")
            else:
                for img_path in valid_paths:
                    await _insert_image_block(page, img_path)
            await asyncio.sleep(0.5)


async def upload_images(page, image_paths: list[str]) -> None:
    """이미지 업로드."""
    if not image_paths:
        return

    for img_path in image_paths:
        if not Path(img_path).exists():
            print(f"  [경고] 이미지 파일 없음: {img_path}", file=sys.stderr)
            continue

        # 사진 추가 버튼
        photo_btn = page.locator("button.se-image-toolbar-button")
        if await photo_btn.count() == 0:
            photo_btn = page.locator("button[data-name='image']")
        if await photo_btn.count() == 0:
            photo_btn = page.locator("button.se-toolbar-button-image")

        if await photo_btn.count() > 0:
            await photo_btn.first.click()
            await asyncio.sleep(1)

            file_input = page.locator("input[type='file']")
            if await file_input.count() > 0:
                await file_input.first.set_input_files(img_path)
                await asyncio.sleep(2)

                insert_btn = page.locator("button.se-popup-button-confirm")
                if await insert_btn.count() > 0:
                    await insert_btn.first.click()
                    await asyncio.sleep(1)

        print(f"  📸 이미지 업로드: {Path(img_path).name}")


async def set_category(page, category_name: str) -> None:
    """카테고리 설정."""
    if not category_name:
        return

    cat_btn = page.locator("button.publish_category__btn")
    if await cat_btn.count() == 0:
        cat_btn = page.locator("div.category button")

    if await cat_btn.count() > 0:
        await cat_btn.first.click()
        await asyncio.sleep(0.5)

        cat_item = page.locator(f"li:has-text('{category_name}')")
        if await cat_item.count() > 0:
            await cat_item.first.click()
            print(f"  📂 카테고리 설정: {category_name}")
        else:
            print(f"  [경고] 카테고리 '{category_name}'을 찾을 수 없습니다.", file=sys.stderr)

        await asyncio.sleep(ACTION_DELAY / 1000)


async def set_tags(page, tags: list[str]) -> None:
    """태그 입력."""
    if not tags:
        return

    tag_input = page.locator("input.publish_tag__input")
    if await tag_input.count() == 0:
        tag_input = page.locator("input[placeholder*='태그']")
    if await tag_input.count() == 0:
        tag_input = page.locator("div.tag input")

    if await tag_input.count() > 0:
        for tag in tags:
            await tag_input.first.fill(tag)
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.3)
        print(f"  🏷️ 태그 {len(tags)}개 입력")
    else:
        print("  [경고] 태그 입력 영역을 찾을 수 없습니다.", file=sys.stderr)


async def set_thumbnail(page, thumbnail: str, blocks: list[dict]) -> None:
    """대표이미지 설정: 본문에 이미 올라간 이미지 중 thumbnail에 해당하는 것을 선택.

    네이버 에디터에서 본문 내 이미지를 클릭하면 '대표이미지로 설정' 옵션이 나타남.
    thumbnail 경로가 몇 번째 이미지인지 계산하여 해당 이미지를 클릭 후 대표이미지로 설정.
    """
    if not thumbnail:
        return

    # thumbnail이 blocks에서 몇 번째 이미지인지 찾기
    img_index = 0
    found = False
    for block in blocks:
        if block["type"] == "image":
            paths = block.get("paths", [])
            if len(paths) >= 2:
                # 합쳐진 이미지는 1장으로 카운트
                if thumbnail in paths:
                    found = True
                    break
                img_index += 1
            else:
                for p in paths:
                    if p == thumbnail:
                        found = True
                        break
                    img_index += 1
                if found:
                    break

    if not found:
        print(f"  [경고] 대표이미지를 blocks에서 찾을 수 없습니다: {Path(thumbnail).name}", file=sys.stderr)
        return

    # 에디터 내 이미지 요소들 찾기
    img_elements = page.locator("div.se-component.se-image img.se-image-resource")
    img_count = await img_elements.count()

    if img_index >= img_count:
        print(f"  [경고] 이미지 인덱스({img_index})가 범위를 벗어남 (총 {img_count}장)", file=sys.stderr)
        return

    print(f"  대표이미지 대상: {img_index + 1}번째 이미지 (총 {img_count}장)")

    try:
        target_img = img_elements.nth(img_index)

        # 이미지를 뷰포트 중앙으로 스크롤 (툴바가 위에 나타나므로 여유 필요)
        await page.evaluate("""(idx) => {
            const imgs = document.querySelectorAll('div.se-component.se-image img.se-image-resource');
            if (imgs[idx]) {
                const rect = imgs[idx].getBoundingClientRect();
                const scrollY = window.scrollY + rect.top - window.innerHeight / 3;
                window.scrollTo({top: scrollY, behavior: 'instant'});
            }
        }""", img_index)
        await asyncio.sleep(1)

        box = await target_img.bounding_box()
        if not box:
            print(f"  ℹ️ 대표이미지 위치를 찾을 수 없습니다 - 수동으로 설정해주세요")
            return

        # 이미지 중앙 클릭 (실제 마우스 이벤트)
        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await asyncio.sleep(2)

        # '대표' 버튼 찾기 - 여러 셀렉터로 시도, 뷰포트 내 버튼만
        repr_rect = await page.evaluate("""() => {
            // 셀렉터 우선순위: 정확한 클래스 → 텍스트 기반
            const selectors = [
                'button.se-set-rep-image-button',
                'button[class*="rep-image"]',
            ];
            for (const sel of selectors) {
                const buttons = document.querySelectorAll(sel);
                for (const btn of buttons) {
                    const r = btn.getBoundingClientRect();
                    if (r.width > 0 && r.y > 0 && r.y < window.innerHeight) {
                        return {x: r.x, y: r.y, w: r.width, h: r.height};
                    }
                }
            }
            // 텍스트 기반 폴백: '대표' 텍스트가 포함된 버튼
            const allBtns = document.querySelectorAll('button');
            for (const btn of allBtns) {
                if (btn.textContent.includes('대표') && !btn.classList.contains('se-is-selected')) {
                    const r = btn.getBoundingClientRect();
                    if (r.width > 0 && r.y > 0 && r.y < window.innerHeight) {
                        return {x: r.x, y: r.y, w: r.width, h: r.height};
                    }
                }
            }
            return null;
        }""")

        if repr_rect:
            await page.mouse.click(
                repr_rect["x"] + repr_rect["w"] / 2,
                repr_rect["y"] + repr_rect["h"] / 2,
            )
            await asyncio.sleep(1)
            print(f"  🖼️ 대표이미지 설정 완료: {Path(thumbnail).name}")
        else:
            # 재시도: 이미지를 한번 더 클릭해보기 (첫 클릭이 선택 해제였을 수 있음)
            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await asyncio.sleep(2)

            repr_rect = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.includes('대표') && !btn.classList.contains('se-is-selected')) {
                        const r = btn.getBoundingClientRect();
                        if (r.width > 0 && r.y > 0 && r.y < window.innerHeight) {
                            return {x: r.x, y: r.y, w: r.width, h: r.height};
                        }
                    }
                }
                return null;
            }""")

            if repr_rect:
                await page.mouse.click(
                    repr_rect["x"] + repr_rect["w"] / 2,
                    repr_rect["y"] + repr_rect["h"] / 2,
                )
                await asyncio.sleep(1)
                print(f"  🖼️ 대표이미지 설정 완료 (재시도): {Path(thumbnail).name}")
            else:
                print(f"  ℹ️ 대표 버튼을 찾을 수 없습니다 - 수동으로 설정해주세요 (이미지 {img_index + 1}번째)")

        # 이미지 선택 해제
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

    except Exception as e:
        print(f"  ℹ️ 대표이미지 설정 중 오류 - 수동으로 설정해주세요: {e}")


async def save_draft(page) -> bool:
    """임시저장."""
    # 네이버 에디터 상단의 "저장" 버튼
    draft_btn = page.locator("button:has-text('저장')")
    if await draft_btn.count() == 0:
        draft_btn = page.locator("button:has-text('임시저장')")
    if await draft_btn.count() == 0:
        draft_btn = page.locator("button.se-toolbar-button-save")

    if await draft_btn.count() > 0:
        await draft_btn.first.click()
        await asyncio.sleep(3)
        print("  💾 임시저장 완료")
        return True

    print("  [경고] 임시저장 버튼을 찾을 수 없습니다.", file=sys.stderr)
    return False


async def publish(page) -> bool:
    """발행."""
    pub_btn = page.locator("button:has-text('발행')")
    if await pub_btn.count() == 0:
        pub_btn = page.locator("button.publish_btn__ok")

    if await pub_btn.count() > 0:
        await pub_btn.first.click()
        await asyncio.sleep(2)

        # 발행 확인 다이얼로그
        confirm_btn = page.locator("button:has-text('발행')")
        if await confirm_btn.count() > 1:
            await confirm_btn.last.click()
            await asyncio.sleep(3)

        print("  📤 발행 완료!")
        return True

    print("  [경고] 발행 버튼을 찾을 수 없습니다.", file=sys.stderr)
    return False


async def upload_post(
    title: str,
    content: str = "",
    category: str = "",
    tags: list[str] | None = None,
    images: list[str] | None = None,
    blocks: list[dict] | None = None,
    thumbnail: str = "",
    place: str = "",
    do_publish: bool = False,
    headless: bool = False,
) -> bool:
    """블로그 글 업로드 메인 함수.

    Args:
        title: 글 제목
        content: 본문 내용 (blocks가 없을 때 사용)
        category: 카테고리 이름
        tags: 태그 리스트
        images: 이미지 파일 경로 리스트 (blocks가 없을 때 사용)
        blocks: 텍스트/이미지 교차 블록 리스트 (있으면 content/images 무시)
        thumbnail: 대표이미지 경로 (본문 내 이미지 중 선택)
        place: 장소 이름 (네이버 지도 와이드형 위젯 삽입)
        do_publish: True면 발행, False면 임시저장 (기본)
        headless: 헤드리스 모드

    Returns:
        성공 여부
    """
    tags = tags or []
    images = images or []

    async with async_playwright() as p:
        context, page = await ensure_login(p, headless=headless)

        try:
            print(f"\n📝 글 업로드 시작: {title}")

            # 1. 에디터 열기
            print("  에디터 열기...")
            await open_editor(page)

            # 2. 제목 입력
            print("  제목 입력...")
            await set_title(page, title)

            # 3. 장소(네이버 지도) 삽입 - 본문 맨 앞에
            if place:
                print("  장소 삽입...")
                # 본문 영역 클릭하여 커서 이동
                body_area = page.locator("p.se-text-paragraph")
                if await body_area.count() == 0:
                    body_area = page.locator("span.se-placeholder")
                if await body_area.count() > 0:
                    await body_area.first.click()
                    await asyncio.sleep(0.5)
                await insert_place_widget(page, place)

            # 4. 본문 + 이미지 입력
            if blocks:
                print("  본문+이미지 교차 입력...")
                await set_content_with_images(page, blocks)
            else:
                print("  본문 입력...")
                await set_content(page, content)
                if images:
                    print("  이미지 업로드...")
                    await upload_images(page, images)

            # 5. 카테고리 설정
            if category:
                await set_category(page, category)

            # 6. 대표이미지 설정
            if thumbnail and blocks:
                await set_thumbnail(page, thumbnail, blocks)

            # 7. 태그 입력 (발행 모드에서만 시도 - 임시저장 시 태그 패널 접근 불가)
            if tags and do_publish:
                await set_tags(page, tags)
            elif tags:
                print("  ℹ️ 임시저장 모드 - 태그는 발행 시 또는 수동으로 추가해주세요")

            # 8. 저장/발행
            if do_publish:
                success = await publish(page)
            else:
                success = await save_draft(page)

            if success:
                action = "발행" if do_publish else "임시저장"
                print(f"\n✅ {action} 완료: {title}")

            return success

        except Exception as e:
            print(f"\n[오류] 업로드 실패: {e}", file=sys.stderr)
            try:
                screenshot_path = PROJECT_ROOT / "output" / "error_screenshot.png"
                await page.screenshot(path=str(screenshot_path), timeout=5000)
                print(f"  스크린샷 저장: {screenshot_path}", file=sys.stderr)
            except Exception:
                pass
            return False

        finally:
            await context.close()


async def test_upload():
    """테스트 모드: 에디터 접근 + 셀렉터 확인."""
    print("🧪 테스트 모드: 에디터 접근 확인\n")

    async with async_playwright() as p:
        from scripts.utils.naver_auth import create_browser_context
        context, page = await create_browser_context(p, headless=False)

        try:
            # 자동 로그인
            print("  로그인 시도...")
            await page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await page.evaluate(f'document.getElementById("id").value = "{NAVER_ID}"')
            await asyncio.sleep(0.3)
            await page.evaluate(f'document.getElementById("pw").value = "{NAVER_PW}"')
            await asyncio.sleep(0.3)
            login_btn = page.locator("#log\\.login")
            if await login_btn.count() == 0:
                login_btn = page.locator("button.btn_login")
            await login_btn.first.click()
            await asyncio.sleep(5)
            print(f"  로그인 후 URL: {page.url}")

            # 에디터 이동
            await page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=EDITOR_LOAD_TIMEOUT)
            await asyncio.sleep(5)
            print(f"  에디터 URL: {page.url}")

            # 셀렉터 확인
            checks = {
                "에디터 컴포넌트": "div.se-component",
                "제목 영역": "div.se-title-text",
                "contenteditable": "div[contenteditable]",
                "블로그 에디터": ".blog_editor",
            }
            all_ok = True
            for name, sel in checks.items():
                count = await page.locator(sel).count()
                if count > 0:
                    print(f"  ✅ {name} ({sel}): {count}개")
                else:
                    print(f"  ❌ {name} ({sel}): 없음")
                    all_ok = False

            if all_ok:
                print("\n✅ 테스트 통과 - 업로드 준비 완료")
            else:
                print("\n⚠️  일부 셀렉터를 찾지 못했습니다")

        finally:
            await context.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="네이버 블로그 업로드")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (에디터 접근 확인)")
    parser.add_argument("--title", default="테스트 포스트", help="글 제목")
    parser.add_argument("--content", default="테스트 내용입니다.", help="본문 내용")
    parser.add_argument("--category", default="", help="카테고리")
    parser.add_argument("--tags", nargs="*", default=[], help="태그 리스트")
    parser.add_argument("--images", nargs="*", default=[], help="이미지 경로 리스트")
    parser.add_argument("--publish", action="store_true", help="발행 (기본: 임시저장)")
    parser.add_argument("--file", default=None, help="JSON 파일에서 글 데이터 로드")
    args = parser.parse_args()

    if args.test:
        asyncio.run(test_upload())
        return

    # JSON 파일에서 로드
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        title = data.get("title", args.title)
        content = data.get("content", args.content)
        category = data.get("category", args.category)
        tags = data.get("tags", args.tags)
        images = data.get("images", args.images)
        blocks = data.get("blocks", None)
        thumbnail = data.get("thumbnail", "")
        place = data.get("place", "")
    else:
        title = args.title
        content = args.content
        category = args.category
        tags = args.tags
        images = args.images
        blocks = None
        thumbnail = ""
        place = ""

    success = asyncio.run(upload_post(
        title=title,
        content=content,
        category=category,
        tags=tags,
        images=images,
        blocks=blocks,
        thumbnail=thumbnail,
        place=place,
        do_publish=args.publish,
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
