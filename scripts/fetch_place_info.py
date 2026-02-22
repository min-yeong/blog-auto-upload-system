#!/usr/bin/env python3
"""네이버 지도 URL에서 식당 정보를 크롤링하는 스크립트.

Usage:
    python3 scripts/fetch_place_info.py "https://naver.me/5FEZv8xJ"
    python3 scripts/fetch_place_info.py "https://naver.me/5FEZv8xJ" --json
    python3 scripts/fetch_place_info.py "https://naver.me/5FEZv8xJ" --dump   # DOM 디버깅
"""

import asyncio
import argparse
import json
import re
import sys
from pathlib import Path

import requests
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── URL 처리 ──────────────────────────────────────────────────────────────


def resolve_place_id(url: str) -> str:
    """URL에서 네이버 플레이스 ID를 추출한다.

    naver.me 단축 URL은 HTTP 리다이렉트를 추적하여 최종 URL에서 ID를 꺼낸다.
    """
    url = url.strip()

    if "naver.me/" in url:
        resp = requests.head(
            url,
            allow_redirects=True,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible)"},
        )
        url = resp.url

    for pattern in [
        r"place\.naver\.com/\w+/(\d+)",
        r"map\.naver\.com.*?/place/(\d+)",
        r"entry/place/(\d+)",
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)

    raise ValueError(f"place ID를 추출할 수 없습니다: {url}")


# ── 브라우저 ──────────────────────────────────────────────────────────────


async def _create_browser(pw, headless: bool = True):
    """모바일 에뮬레이션 브라우저를 생성한다."""
    browser = await pw.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = await browser.new_context(
        viewport={"width": 430, "height": 932},
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    return browser, ctx


# ── 데이터 추출 ───────────────────────────────────────────────────────────


_EXTRACT_JS = """() => {
    const info = {
        name: '', address: '', phone: '',
        hours: '', hours_detail: '', closed_days: '',
        parking: '', menu: []
    };

    /* ── 이름 ── */
    const og = document.querySelector('meta[property="og:title"]');
    if (og) info.name = og.content.replace(/\\s*[:\\|·].*$/, '').trim();
    if (!info.name) {
        const h = document.querySelector('h1, h2');
        if (h) info.name = h.textContent.trim();
    }

    const lines = document.body.innerText
        .split('\\n').map(s => s.trim()).filter(Boolean);

    /* ── 주소: "주소" 라벨 다음 줄에서 추출 ── */
    for (let i = 0; i < lines.length; i++) {
        if (lines[i] === '주소' && i + 1 < lines.length) {
            let addr = lines[i + 1];
            addr = addr.replace(/(지도|내비게이션|거리뷰|복사)+$/, '').trim();
            const prefixes = [
                '서울','부산','대구','인천','광주','대전','울산','세종',
                '경기','강원','충북','충남','전북','전남','경북','경남','제주'
            ];
            if (prefixes.some(p => addr.startsWith(p))) info.address = addr;
            break;
        }
    }

    /* ── 전화번호: "전화번호" 라벨 다음 줄 ── */
    for (let i = 0; i < lines.length; i++) {
        if (/^전화번호/.test(lines[i])) {
            for (let j = i + 1; j < Math.min(i + 3, lines.length); j++) {
                const m = lines[j].match(/(0\\d{2,3})[\\-·.](\\d{3,4})[\\-·.](\\d{4})/);
                if (m) { info.phone = m[0]; break; }
            }
            break;
        }
    }
    if (!info.phone) {
        for (const l of lines) {
            const m = l.match(/(0\\d{2,3})[\\-·.](\\d{3,4})[\\-·.](\\d{4})/);
            if (m) { info.phone = m[0]; break; }
        }
    }

    /* ── 영업시간 ── */
    for (let i = 0; i < lines.length; i++) {
        if (!/^영업시간/.test(lines[i])) continue;
        const hourLines = [];
        const closedLines = [];
        for (let j = i + 1; j < Math.min(i + 50, lines.length); j++) {
            const n = lines[j];
            if (/접기|더보기|영업시간\\s*수정/.test(n)) continue;
            if (/^전화번호|^편의|^홈페이지|^안내$|^복사$/.test(n)) break;
            if (/휴무/.test(n)) {
                closedLines.push(n);
            } else if (/\\d{1,2}:\\d{2}/.test(n) ||
                       /^(매일|월|화|수|목|금|토|일|월요일|화요일|수요일|목요일|금요일|토요일|일요일|오늘)/.test(n)) {
                hourLines.push(n);
            }
        }
        if (hourLines.length) {
            const realHours = hourLines.filter(h => /\\d{1,2}:\\d{2}/.test(h));
            const statusLines = hourLines.filter(h => !/\\d{1,2}:\\d{2}/.test(h));
            if (realHours.length) {
                /* 중복 제거 후 대표 시간 + 부가 정보 */
                const unique = [...new Set(realHours)];
                info.hours = unique[0];
                if (unique.length > 1) info.hours_detail = unique.slice(1).join(' / ');
            } else if (statusLines.length) {
                info.hours = statusLines[0];
            }
        }
        /* 휴무: "매주" 또는 "정기휴무" 우선, "오늘 휴무" 후순위 */
        if (closedLines.length) {
            const permanent = closedLines.find(l => /매주|정기/.test(l));
            info.closed_days = permanent || closedLines[0];
        }
        break;
    }
    if (!info.closed_days) {
        for (const l of lines) {
            if (/매주.*휴무|휴무일/.test(l) && l.length < 50) {
                info.closed_days = l;
                break;
            }
        }
    }

    /* ── 주차 ── */
    for (const l of lines) {
        if (/주차/.test(l) && !/^주차$/.test(l) && l.length < 80) {
            info.parking = l.replace(/\\.{3}$/, '').replace(/내용 더보기$/, '').trim();
            break;
        }
    }

    /* ── 메뉴 ── */
    let menuZone = false;
    for (let i = 0; i < lines.length; i++) {
        if (/^메뉴\\d+$|^대표$|^대표\\s*메뉴|^인기메뉴/.test(lines[i])) {
            menuZone = true;
            continue;
        }
        if (!menuZone) continue;
        if (info.menu.length >= 15) break;
        if (/^리뷰|^방문자\\s*리뷰|^AI\\s*브리핑|^이용약관|^메뉴\\s*항목/.test(lines[i])) break;
        if (/^메뉴판|^메뉴\\s*더보기|^더보기/.test(lines[i])) continue;
        if (/^\\d[\\d,]*\\s*원$/.test(lines[i])) continue;
        if (/^사진$/.test(lines[i])) continue;

        const sameMatch = lines[i].match(/^(.+?)\\s+([\\d,]+)\\s*원$/);
        if (sameMatch) {
            info.menu.push({ name: sameMatch[1].trim(), price: sameMatch[2] + '원' });
            continue;
        }

        if (lines[i].length < 30 && !/^\\d/.test(lines[i])) {
            if (i + 1 < lines.length && /^[\\d,]+\\s*원$/.test(lines[i + 1])) {
                const price = lines[i + 1].match(/^([\\d,]+)\\s*원$/)[1];
                info.menu.push({ name: lines[i].trim(), price: price + '원' });
                i++;
                continue;
            }
            /* 메뉴이름 → 사진 → 가격 패턴 (사진이 중간에 끼는 경우) */
            if (i + 2 < lines.length && /^사진$/.test(lines[i + 1]) && /^[\\d,]+\\s*원$/.test(lines[i + 2])) {
                const price = lines[i + 2].match(/^([\\d,]+)\\s*원$/)[1];
                info.menu.push({ name: lines[i].trim(), price: price + '원' });
                i += 2;
                continue;
            }
        }
    }

    return info;
}"""


async def _expand_sections(page):
    """접힌 섹션(영업시간 펼쳐보기 등)을 펼친다.

    주의: 메뉴 더보기는 페이지 네비게이션이 발생하므로 클릭하지 않는다.
    """
    # JS로 직접 "펼쳐보기" 텍스트를 가진 버튼/링크를 찾아 클릭
    clicked = await page.evaluate("""() => {
        const allEls = document.querySelectorAll('button, a, span, [role="button"]');
        for (const el of allEls) {
            if (el.textContent.trim() === '펼쳐보기') {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    if clicked:
        print("  [INFO] 펼쳐보기 클릭 성공", file=__import__('sys').stderr)
        await page.wait_for_timeout(1500)
        return

    # 폴백: Playwright 셀렉터
    for selector in [
        'button:has-text("펼쳐보기")',
        'a:has-text("영업시간 더보기")',
        '[class*="bizHour"] button',
    ]:
        try:
            el = page.locator(selector).first
            if await el.count() > 0:
                await el.scroll_into_view_if_needed(timeout=2000)
                await page.wait_for_timeout(300)
                await el.click(timeout=2000)
                await page.wait_for_timeout(1500)
                break
        except Exception:
            pass


# ── 메인 크롤링 함수 ─────────────────────────────────────────────────────


async def fetch_place_info(
    url: str,
    headless: bool = True,
    dump: bool = False,
) -> dict:
    """네이버 지도 URL에서 식당 정보를 크롤링한다.

    모바일 홈 페이지에서 이름, 주소, 영업시간, 전화, 주차, 메뉴를 추출한다.

    Args:
        url: 네이버 지도 URL (naver.me 단축 URL 또는 place URL)
        headless: 브라우저 숨김 여부
        dump: True이면 페이지 텍스트를 stderr에 출력 (디버깅용)

    Returns:
        식당 정보 dict
    """
    place_id = resolve_place_id(url)
    place_url = f"https://m.place.naver.com/restaurant/{place_id}/home"

    async with async_playwright() as pw:
        browser, ctx = await _create_browser(pw, headless)
        page = await ctx.new_page()

        try:
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
            except ImportError:
                pass

            print(f"[INFO] {place_url} 접속 중...", file=sys.stderr)
            await page.goto(place_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # 접힌 섹션 펼치기 (영업시간 상세 등)
            await _expand_sections(page)

            if dump:
                text = await page.inner_text("body")
                print("=" * 60, file=sys.stderr)
                print("[DOM DUMP]", file=sys.stderr)
                print(text[:8000], file=sys.stderr)
                print("=" * 60, file=sys.stderr)

            data = await page.evaluate(_EXTRACT_JS)
            data["source_url"] = place_url
            return data

        finally:
            await browser.close()


# ── 블로그용 텍스트 ───────────────────────────────────────────────────────


def format_business_info(data: dict) -> str:
    """크롤링 결과를 블로그 영업정보 블록 텍스트로 변환한다.

    upload_naver.py의 bullet 리스트 형식에 맞게 줄 단위로 반환.
    """
    parts = []
    if data.get("address"):
        parts.append(f"위치 {data['address']}")
    if data.get("hours"):
        h = f"영업시간 {data['hours']}"
        if data.get("hours_detail"):
            h += f" ({data['hours_detail']})"
        parts.append(h)
    if data.get("closed_days"):
        parts.append(f"휴무 {data['closed_days']}")
    if data.get("phone"):
        parts.append(f"전화 {data['phone']}")
    if data.get("parking"):
        parts.append(f"주차 {data['parking']}")
    return "\n".join(parts)


# ── CLI ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="네이버 지도 URL에서 식당 정보를 크롤링합니다.",
    )
    parser.add_argument("url", help="네이버 지도 URL (naver.me 또는 place URL)")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="JSON 형식으로 출력"
    )
    parser.add_argument("--dump", action="store_true", help="페이지 텍스트 덤프 (디버깅)")
    parser.add_argument(
        "--no-headless", action="store_true", help="브라우저 표시 (디버깅)"
    )
    args = parser.parse_args()

    data = asyncio.run(
        fetch_place_info(
            args.url,
            headless=not args.no_headless,
            dump=args.dump,
        )
    )

    if args.as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'=' * 40}")
        print(f"  {data.get('name', '(이름 없음)')}")
        print(f"{'=' * 40}")
        if data.get("address"):
            print(f"  주소: {data['address']}")
        if data.get("phone"):
            print(f"  전화: {data['phone']}")
        if data.get("hours"):
            print(f"  영업시간: {data['hours']}")
        if data.get("hours_detail"):
            print(f"  상세: {data['hours_detail']}")
        if data.get("closed_days"):
            print(f"  휴무: {data['closed_days']}")
        if data.get("parking"):
            print(f"  주차: {data['parking']}")
        if data.get("menu"):
            print(f"\n  [ 메뉴 ]")
            for item in data["menu"]:
                print(f"  {item['name']:20s} {item['price']}")
        print(f"\n  출처: {data.get('source_url', '')}")
        print()


if __name__ == "__main__":
    main()
