#!/usr/bin/env python3
"""네이버 블로그 업로드: Playwright로 SmartEditor ONE 자동화.

기본 모드: 임시저장 (안전)
옵션: --publish로 발행

네이버 블로그 에디터는 iframe 없이 직접 페이지에 렌더링됨.
주요 셀렉터: div.se-title-text, div.se-component.se-text, div[contenteditable]
"""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.utils.naver_auth import ensure_login, BLOG_ID, NAVER_ID, NAVER_PW
from scripts.utils.image_utils import stitch_images_horizontally, mosaic_faces_in_paths

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


async def set_font_size(page, size: int = 11) -> None:
    """에디터 글씨크기 설정 (본문 영역 클릭 후 호출).

    네이버 SmartEditor ONE 텍스트 프로퍼티 툴바의 글씨크기 드롭다운을 열어 원하는 크기를 선택.
    본문 클릭 후에만 텍스트 프로퍼티 툴바가 나타남.
    """
    # 글씨크기 드롭다운 버튼 찾기 (본문 클릭 후 나타나는 텍스트 프로퍼티 툴바)
    font_btn = page.locator("button.se-font-size-code-toolbar-button")
    if await font_btn.count() == 0:
        font_btn = page.locator("button[data-name='font-size']")
    if await font_btn.count() == 0:
        font_btn = page.locator("button.se-toolbar-button-fontSize")

    if await font_btn.count() == 0:
        print("  [경고] 글씨크기 버튼을 찾을 수 없습니다", file=sys.stderr)
        return

    try:
        await font_btn.first.click()
        await asyncio.sleep(1.5)

        # 드롭다운에서 원하는 크기 선택
        # Playwright locator로 직접 클릭 시도
        size_option = page.locator(f"li:has-text('{size}')").first
        try:
            await size_option.click(timeout=3000)
            result = {"clicked": True}
        except Exception:
            # JS 폴백: 모든 visible li 요소에서 텍스트 매칭
            result = await page.evaluate("""(targetSize) => {
                const allLi = document.querySelectorAll('li');
                const found = [];
                for (const li of allLi) {
                    const r = li.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && r.height < 50) {
                        const text = li.textContent.trim();
                        if (text === String(targetSize)) {
                            li.click();
                            return {clicked: true, text: text};
                        }
                        if (/^\\d+$/.test(text)) {
                            found.push(text);
                        }
                    }
                }
                return {clicked: false, available: found};
            }""", size)

        if result.get("clicked"):
            await asyncio.sleep(0.5)
            print(f"  🔤 글씨크기 {size} 설정 완료")
        else:
            available = result.get("available", [])
            print(f"  [경고] 글씨크기 {size} 옵션 없음 (사용 가능: {available})", file=sys.stderr)
            await page.keyboard.press("Escape")
    except Exception as e:
        print(f"  [경고] 글씨크기 설정 실패: {e}", file=sys.stderr)
        await page.keyboard.press("Escape")


async def _insert_separator(page) -> None:
    """에디터에 구분선(수평선) 삽입.

    네이버 SmartEditor ONE 상단 도큐먼트 툴바의 구분선 버튼을 클릭하여 삽입.
    셀렉터: button.se-insert-horizontal-line-default-toolbar-button
    스타일 선택 드롭다운: 옆의 se-document-toolbar-select-option-button
    """
    # 구분선 기본 버튼 (상단 도큐먼트 툴바)
    sep_btn = page.locator("button.se-insert-horizontal-line-default-toolbar-button")
    if await sep_btn.count() == 0:
        sep_btn = page.locator("li.se-toolbar-item-insert-horizontal-line button.se-document-toolbar-icon-select-button")
    if await sep_btn.count() == 0:
        sep_btn = page.locator("button[data-name='horizontalRule']")

    if await sep_btn.count() == 0:
        print("  [경고] 구분선 버튼을 찾을 수 없습니다", file=sys.stderr)
        return

    try:
        await sep_btn.first.click()
        await asyncio.sleep(1)

        # 구분선 스타일 선택 팝업이 나타날 수 있음 → 첫 번째 스타일 선택
        style_item = page.locator("div.se-popup-content button, div.se-select-option button")
        if await style_item.count() > 0:
            await style_item.first.click()
            await asyncio.sleep(0.5)

        print("  ── 구분선 삽입 완료")
    except Exception as e:
        print(f"  [경고] 구분선 삽입 실패: {e}", file=sys.stderr)
        await page.keyboard.press("Escape")


async def _insert_quotation_block(page, text: str) -> None:
    """인용구(좌측 세로 바) 블록 삽입 후 텍스트 입력.

    1. 인용구 드롭다운에서 '버티컬 라인' 스타일 선택 (좌표 기반 클릭)
    2. 텍스트 입력 후 인용구 밖으로 커서 이동
    """
    import pyperclip

    # 인용구 기본 버튼 (상단 도큐먼트 툴바)
    quote_btn = page.locator("button.se-insert-quotation-default-toolbar-button")
    if await quote_btn.count() == 0:
        quote_btn = page.locator("li.se-toolbar-item-insert-quotation button.se-document-toolbar-icon-select-button")
    if await quote_btn.count() == 0:
        quote_btn = page.locator("li.se-toolbar-item-insert-quotation button")

    if await quote_btn.count() == 0:
        print("  [경고] 인용구 버튼을 찾을 수 없습니다 - 일반 텍스트로 대체", file=sys.stderr)
        await _type_text_block(page, text)
        return

    try:
        # 드롭다운 버튼으로 스타일 선택 팝업 열기
        dropdown_btn = page.locator("li.se-toolbar-item-insert-quotation button.se-document-toolbar-select-option-button")
        if await dropdown_btn.count() > 0:
            await dropdown_btn.first.click()
            await asyncio.sleep(1.5)

            # 드롭다운 버튼 좌표 기준으로 "버티컬 라인" (2번째 옵션) 위치 클릭
            # 팝업 구조: 따옴표(1번) → 버티컬 라인(2번) → 말풍선(3번) ...
            # 각 옵션 높이 약 50px, 2번째 옵션은 버튼 아래 ~90px 위치
            dd_box = await dropdown_btn.first.bounding_box()
            if dd_box:
                target_x = dd_box["x"] + 50  # 팝업 중앙쯤
                target_y = dd_box["y"] + dd_box["height"] + 90  # 2번째 옵션 위치
                await page.mouse.click(target_x, target_y)
                await asyncio.sleep(1)
                print(f"  인용구 스타일: 버티컬 라인 클릭 (좌표: {target_x:.0f}, {target_y:.0f})")
            else:
                # 좌표 못 가져오면 기본 버튼 폴백
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                await quote_btn.first.click()
                await asyncio.sleep(1.5)
                style_item = page.locator("div.se-popup-content button:visible")
                if await style_item.count() > 0:
                    await style_item.first.click()
                    await asyncio.sleep(0.5)
        else:
            # 드롭다운 없으면 기본 버튼으로 삽입
            await quote_btn.first.click()
            await asyncio.sleep(1.5)
            style_item = page.locator("div.se-popup-content button:visible")
            if await style_item.count() > 0:
                await style_item.first.click()
                await asyncio.sleep(0.5)

        # 인용구 블록 안에 텍스트 입력
        pyperclip.copy(text)
        await page.keyboard.press("Meta+v")
        await asyncio.sleep(0.5)

        # 인용구 밖으로 커서 이동: 인용구 다음 텍스트 컴포넌트 클릭
        moved = await page.evaluate("""() => {
            const quotations = document.querySelectorAll('div.se-component.se-quotation');
            if (quotations.length === 0) return false;
            const quotation = quotations[quotations.length - 1];
            let next = quotation.nextElementSibling;
            while (next) {
                const p = next.querySelector('p.se-text-paragraph');
                if (p) {
                    p.click();
                    return true;
                }
                next = next.nextElementSibling;
            }
            return false;
        }""")

        if not moved:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.3)

        await asyncio.sleep(0.5)
        print(f"  📌 인용구 삽입 완료: {text}")
    except Exception as e:
        print(f"  [경고] 인용구 삽입 실패: {e} - 일반 텍스트로 대체", file=sys.stderr)
        await _type_text_block(page, text)


async def _type_text_block(page, text: str) -> None:
    """텍스트 블록 입력 (커서 위치에)."""
    import pyperclip

    paragraphs = text.split("\n")
    for i, para in enumerate(paragraphs):
        if para.strip():
            pyperclip.copy(para.strip())
            await page.keyboard.press("Meta+v")
            await asyncio.sleep(0.3)  # 붙여넣기 완료 대기
        if i < len(paragraphs) - 1:
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.2)  # Enter로 새 단락 생성 대기
    await asyncio.sleep(ACTION_DELAY / 1000)


async def _type_bullet_list(page, text: str) -> None:
    """텍스트를 bullet(•) 형식으로 입력.

    각 줄 앞에 • 문자를 붙여 입력.
    """
    import pyperclip

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        pyperclip.copy(f"• {line}")
        await page.keyboard.press("Meta+v")
        await asyncio.sleep(0.3)
        if i < len(lines) - 1:
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.2)

    await asyncio.sleep(ACTION_DELAY / 1000)
    await page.keyboard.press("Enter")
    await asyncio.sleep(0.2)
    print("  📋 영업정보 입력 완료")


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


async def set_content_with_images(page, blocks: list[dict], place: str = "") -> None:
    """텍스트와 이미지를 교차 입력.

    blocks 형식:
      [
        {"type": "text", "content": "글 내용..."},
        {"type": "image", "paths": ["/path/to/img1.jpeg", ...]},
        {"type": "separator"},
        {"type": "text", "content": "다음 글 내용..."},
        ...
      ]

    place: 장소 이름 (맨 마지막에 네이버 지도 위젯 삽입)

    블록 처리 순서:
      1. 첫 번째 text → 인용구(버티컬 라인) 가게이름
      2. 두 번째 text → bullet(•) 영업정보
      3. separator → 구분선
      4. 나머지 text/image → 본문 교차
      5. separator → 구분선
      6. 마지막 text → 총평
      7. place → 네이버 지도 위젯 (맨 마지막)
    """
    # 본문 영역 클릭 (제목이 아닌 본문 영역을 정확히 클릭)
    # span.se-placeholder("본문을 입력하세요")는 본문에만 존재하므로 가장 안전
    placeholder = page.locator("span.se-placeholder")
    if await placeholder.count() > 0:
        await placeholder.first.click()
        print("  본문 placeholder 클릭")
    else:
        # placeholder가 없으면 본문 텍스트 컴포넌트의 단락 클릭
        body_paras = page.locator("div.se-component.se-text p.se-text-paragraph")
        if await body_paras.count() > 0:
            await body_paras.last.click()
            print("  본문 단락(last) 클릭")
        else:
            # 최후 폴백
            body_area = page.locator("p.se-text-paragraph").last
            await body_area.click()
            print("  단락(last) 폴백 클릭")
    await asyncio.sleep(ACTION_DELAY / 1000)

    text_block_index = 0
    separator_count = 0

    for block in blocks:
        if block["type"] == "text":
            if text_block_index == 0:
                # 첫 번째 텍스트: 인용구(좌측 세로 바) + 가게이름
                await _insert_quotation_block(page, block["content"])

            elif text_block_index == 1:
                # 두 번째 텍스트 (영업정보): 목록(bullet) 형식
                await _type_bullet_list(page, block["content"])

            else:
                # 나머지: 일반 텍스트
                await _type_text_block(page, block["content"])
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.3)

            text_block_index += 1
        elif block["type"] == "separator":
            await _insert_separator(page)
            separator_count += 1
            await asyncio.sleep(0.3)
        elif block["type"] == "image":
            paths = block.get("paths", [])
            valid_paths = [p for p in paths if Path(p).exists()]
            # 얼굴 모자이크 처리
            mosaic_dir = str(PROJECT_ROOT / "output" / "mosaic")
            valid_paths = mosaic_faces_in_paths(valid_paths, mosaic_dir)
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

    # 모든 블록 입력 후 글씨크기 설정 (블록 입력 중간에 하면 커서가 이동됨)
    await set_font_size(page, size=13)

    # 장소(네이버 지도) 위젯을 맨 마지막에 삽입
    if place:
        print("  장소 삽입 (맨 마지막)...")
        await insert_place_widget(page, place)


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

        # 방법: 각 이미지 컴포넌트 내부에 있는 se-set-rep-image-button을 직접 JS로 클릭
        # (DOM에는 존재하지만 display:none 상태 → 강제로 클릭 핸들러 트리거)
        result = await page.evaluate("""(idx) => {
            const comps = document.querySelectorAll('div.se-component.se-image');
            if (!comps[idx]) return {error: 'component not found', count: comps.length};

            const btn = comps[idx].querySelector('button.se-set-rep-image-button');
            if (!btn) return {error: 'rep button not found in component'};

            // 이미 대표로 설정된 경우 스킵
            if (btn.classList.contains('se-is-selected')) {
                return {already: true};
            }

            // 버튼 클릭 (hidden이어도 click 이벤트는 전달됨)
            btn.click();
            return {clicked: true, btnClass: btn.className};
        }""", img_index)

        if result.get("clicked"):
            await asyncio.sleep(1)
            print(f"  🖼️ 대표이미지 설정 완료: {Path(thumbnail).name}")
        elif result.get("already"):
            print(f"  🖼️ 이미 대표이미지로 설정되어 있음: {Path(thumbnail).name}")
        else:
            # 폴백: 이미지 직접 클릭 후 대표 버튼 찾기
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            await target_img.scroll_into_view_if_needed()
            await asyncio.sleep(1)

            box = await target_img.bounding_box()
            if box:
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
                    print(f"  🖼️ 대표이미지 설정 완료 (폴백): {Path(thumbnail).name}")
                else:
                    print(f"  ℹ️ 대표 버튼을 찾을 수 없습니다 - 수동으로 설정해주세요 (이미지 {img_index + 1}번째) | {result}")
            else:
                print(f"  ℹ️ 이미지 위치 못 찾음 - 수동으로 설정해주세요 | {result}")

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

            # 3. 본문 + 이미지 입력 (장소 위젯은 맨 마지막에 삽입)
            if blocks:
                print("  본문+이미지 교차 입력...")
                await set_content_with_images(page, blocks, place=place)
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
                "글씨크기 버튼": "button.se-font-size-code-toolbar-button",
                "글씨크기 버튼(data-name)": "button[data-name='font-size']",
                "구분선 버튼": "button.se-insert-horizontal-line-default-toolbar-button",
                "구분선 버튼(li)": "li.se-toolbar-item-insert-horizontal-line",
                "인용구 버튼": "button.se-insert-quotation-default-toolbar-button",
                "인용구 버튼(li)": "li.se-toolbar-item-insert-quotation",
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

            # 임시저장 팝업 닫기
            cancel_btn = page.locator("div.se-popup-alert-confirm button:has-text('취소')")
            if await cancel_btn.count() > 0:
                await cancel_btn.first.click()
                await asyncio.sleep(1)
                print("  이전 임시저장 무시 (새 글 작성)")

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
