"""네이버 로그인 + 세션 관리 (Playwright persistent context)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / "config" / ".env")

BROWSER_STATE_DIR = PROJECT_ROOT / "cache" / "browser_state"
BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)

NAVER_ID = os.getenv("NAVER_ID", "")
NAVER_PW = os.getenv("NAVER_PW", "")
BLOG_ID = os.getenv("BLOG_ID", "")

LOGIN_URL = "https://nid.naver.com/nidlogin.login"
BLOG_HOME = f"https://blog.naver.com/{BLOG_ID}"


async def create_browser_context(playwright, headless: bool = False):
    """Playwright persistent context 생성 (세션 유지).

    Args:
        playwright: Playwright 인스턴스
        headless: 헤드리스 모드 여부 (기본: False - 로그인 확인용)

    Returns:
        (context, page) 튜플
    """
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        stealth_async = None

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_STATE_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
    )

    page = context.pages[0] if context.pages else await context.new_page()

    if stealth_async:
        await stealth_async(page)

    return context, page


async def is_logged_in(page) -> bool:
    """현재 페이지에서 네이버 로그인 상태 확인."""
    import asyncio
    try:
        await page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 방법 1: 로그인 버튼이 있으면 미로그인
        login_selectors = [
            "a.MyView-module__link_login___HpHMW",
            "a[href*='nidlogin']",
            "a.link_login",
            "a:has-text('로그인')",
        ]
        for sel in login_selectors:
            el = await page.query_selector(sel)
            if el:
                return False

        # 방법 2: 블로그에 직접 접근해서 확인 (가장 확실)
        await page.goto(f"https://blog.naver.com/{BLOG_ID}/postwrite", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        # 에디터 페이지에 도달했으면 로그인됨
        if "postwrite" in page.url:
            await page.go_back()
            return True
        # 로그인 페이지로 리다이렉트 됐으면 미로그인
        if "nidlogin" in page.url:
            return False

        return True
    except Exception:
        return False


async def login_naver(page, manual: bool = True) -> bool:
    """네이버 로그인 수행.

    Args:
        page: Playwright 페이지
        manual: True면 수동 로그인 대기 (봇 감지 우회에 가장 안전)

    Returns:
        로그인 성공 여부
    """
    if not NAVER_ID:
        print("[오류] NAVER_ID가 설정되지 않았습니다.", file=sys.stderr)
        return False

    await page.goto(LOGIN_URL, wait_until="domcontentloaded")

    if manual:
        print("\n🔐 네이버 로그인 페이지가 열렸습니다.")
        print("  브라우저에서 직접 로그인해주세요.")
        print("  로그인 완료 후 Enter를 눌러주세요...")

        # 로그인 완료 대기 (최대 5분)
        try:
            await page.wait_for_url("**/naver.com/**", timeout=300000)
            print("  ✅ 로그인 감지됨!")
        except Exception:
            # URL 변경 감지 실패 시 수동 확인
            input("  [Enter를 눌러 계속...]")

        return await _verify_login(page)
    else:
        # 자동 로그인 (봇 감지 위험 있음)
        return await _auto_login(page)


async def _auto_login(page) -> bool:
    """자동 로그인 시도 (JS evaluate 방식)."""
    import asyncio

    try:
        await asyncio.sleep(2)

        # JS로 직접 값 설정 (봇 감지 최소화)
        await page.evaluate(f'document.getElementById("id").value = "{NAVER_ID}"')
        await asyncio.sleep(0.3)
        await page.evaluate(f'document.getElementById("pw").value = "{NAVER_PW}"')
        await asyncio.sleep(0.3)

        # 로그인 버튼 클릭
        login_btn = page.locator("#log\\.login")
        if await login_btn.count() == 0:
            login_btn = page.locator("button.btn_login")
        await login_btn.first.click()
        await asyncio.sleep(5)

        # 캡차 또는 2차 인증 확인
        if "captcha" in page.url or "2step" in page.url:
            print("\n⚠️  캡차 또는 2차 인증이 필요합니다. 브라우저에서 완료해주세요.")
            # 최대 2분 대기
            await page.wait_for_url("**/naver.com/**", timeout=120000)

        return await _verify_login(page)

    except Exception as e:
        print(f"[오류] 자동 로그인 실패: {e}", file=sys.stderr)
        return False


async def _verify_login(page) -> bool:
    """로그인 상태 최종 확인."""
    try:
        await page.goto(BLOG_HOME, wait_until="domcontentloaded", timeout=10000)
        # 블로그 관리/글쓰기 버튼 존재 확인
        write_btn = await page.query_selector("a[href*='PostWriteForm']")
        if write_btn:
            print("  ✅ 블로그 접근 확인 완료")
            return True

        # 대안: 페이지 제목으로 확인
        title = await page.title()
        if BLOG_ID in title or "블로그" in title:
            return True

        return False
    except Exception:
        return False


async def ensure_login(playwright, headless: bool = False):
    """로그인 보장: 세션이 유효하면 재사용, 아니면 로그인.

    Returns:
        (context, page) 튜플
    """
    context, page = await create_browser_context(playwright, headless=headless)

    if await is_logged_in(page):
        print("✅ 기존 세션으로 로그인됨")
        return context, page

    print("🔑 새로 로그인이 필요합니다.")
    success = await login_naver(page, manual=False)

    if not success:
        print("[오류] 로그인에 실패했습니다.", file=sys.stderr)
        await context.close()
        sys.exit(1)

    return context, page
