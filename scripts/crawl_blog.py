#!/usr/bin/env python3
"""네이버 블로그 크롤러: m.blog.naver.com 모바일 URL로 기존 글 수집."""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 프로젝트 경로 설정
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "config" / ".env")

BLOG_ID = os.getenv("BLOG_ID", "")
CACHE_DIR = PROJECT_ROOT / "cache" / "crawled_posts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": f"https://m.blog.naver.com/{BLOG_ID}",
}

# 요청 간 딜레이 (초)
REQUEST_DELAY = 1.5


def get_post_list(blog_id: str, count: int = 20) -> list[dict]:
    """블로그의 최근 포스트 목록을 가져옴.

    네이버 블로그 API를 사용하여 포스트 목록 조회.
    """
    posts = []
    page = 1
    per_page = 10

    while len(posts) < count:
        url = (
            f"https://m.blog.naver.com/api/blogs/{blog_id}/post-list"
            f"?categoryNo=0&itemCount={per_page}&page={page}"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[경고] 포스트 목록 가져오기 실패 (page={page}): {e}", file=sys.stderr)
            break

        items = data.get("result", {}).get("items", [])
        if not items:
            break

        for item in items:
            posts.append({
                "logNo": item.get("logNo"),
                "title": item.get("titleWithInspectMessage", item.get("title", "")),
                "categoryName": item.get("categoryName", ""),
                "addDate": item.get("addDate", ""),
            })

        if len(items) < per_page:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return posts[:count]


def crawl_post(blog_id: str, log_no: str) -> dict | None:
    """개별 포스트의 본문 내용을 크롤링."""
    url = f"https://m.blog.naver.com/{blog_id}/{log_no}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[경고] 포스트 크롤링 실패 (logNo={log_no}): {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # 모바일 본문 영역 추출
    content_area = (
        soup.select_one("div.se-main-container")  # SmartEditor ONE
        or soup.select_one("div.__viewer_container")  # 구버전
        or soup.select_one("div#postViewArea")  # 레거시
    )

    if not content_area:
        # JSON 데이터에서 본문 추출 시도
        return _extract_from_json(resp.text, blog_id, log_no)

    # 텍스트 추출 (이미지 캡션 포함)
    paragraphs = []
    for el in content_area.find_all(["p", "span", "div"], recursive=True):
        text = el.get_text(strip=True)
        if text and len(text) > 1:
            paragraphs.append(text)

    # 중복 제거 (부모-자식 관계에서 발생)
    seen = set()
    unique_paragraphs = []
    for p in paragraphs:
        if p not in seen:
            seen.add(p)
            unique_paragraphs.append(p)

    content = "\n".join(unique_paragraphs)

    # 제목 추출
    title_el = soup.select_one("div.se-title-text") or soup.select_one("h3.se_textarea")
    title = title_el.get_text(strip=True) if title_el else ""

    # 태그 추출
    tags = []
    tag_area = soup.select("a.tag") or soup.select("span.ell")
    for tag in tag_area:
        t = tag.get_text(strip=True).lstrip("#")
        if t:
            tags.append(t)

    return {
        "blog_id": blog_id,
        "log_no": log_no,
        "title": title,
        "content": content,
        "tags": tags,
        "url": url,
        "char_count": len(content),
    }


def _extract_from_json(html: str, blog_id: str, log_no: str) -> dict | None:
    """페이지 내 JSON 데이터에서 본문 추출 (SSR 데이터)."""
    # __NEXT_DATA__ 또는 window.__APOLLO_STATE__ 에서 추출
    match = re.search(r'<script[^>]*>window\.__APOLLO_STATE__\s*=\s*({.*?})\s*;?\s*</script>', html, re.DOTALL)
    if not match:
        match = re.search(r'"postView":\s*(\{.*?\})\s*[,}]', html, re.DOTALL)

    if not match:
        print(f"[경고] 본문 추출 실패 (logNo={log_no}): HTML 구조 불일치", file=sys.stderr)
        return None

    try:
        raw = match.group(1)
        # HTML 태그 제거하고 텍스트만 추출
        content = re.sub(r'<[^>]+>', '\n', raw)
        content = re.sub(r'\\n', '\n', content)
        content = re.sub(r'\\u[0-9a-fA-F]{4}', '', content)
        content = re.sub(r'\s+', ' ', content).strip()

        return {
            "blog_id": blog_id,
            "log_no": log_no,
            "title": "",
            "content": content[:5000],  # 안전 제한
            "tags": [],
            "url": f"https://m.blog.naver.com/{blog_id}/{log_no}",
            "char_count": len(content[:5000]),
        }
    except Exception:
        return None


def crawl_blog(blog_id: str | None = None, count: int = 20) -> list[dict]:
    """블로그의 최근 글들을 크롤링하고 캐시에 저장.

    Args:
        blog_id: 네이버 블로그 ID (None이면 .env에서 로드)
        count: 수집할 글 수 (기본 20)

    Returns:
        크롤링된 포스트 데이터 리스트
    """
    bid = blog_id or BLOG_ID
    if not bid:
        print("[오류] BLOG_ID가 설정되지 않았습니다. config/.env를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    print(f"📝 {bid} 블로그에서 최근 {count}개 글 수집 중...")

    # 1. 포스트 목록 가져오기
    post_list = get_post_list(bid, count)
    if not post_list:
        print("[오류] 포스트 목록을 가져올 수 없습니다.", file=sys.stderr)
        return []

    print(f"  → {len(post_list)}개 포스트 발견")

    # 2. 각 포스트 크롤링
    crawled = []
    for i, post_meta in enumerate(post_list, 1):
        log_no = str(post_meta["logNo"])
        cache_file = CACHE_DIR / f"{log_no}.json"

        # 캐시 확인
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            crawled.append(data)
            print(f"  [{i}/{len(post_list)}] 캐시 사용: {post_meta['title'][:30]}")
            continue

        print(f"  [{i}/{len(post_list)}] 크롤링: {post_meta['title'][:30]}...")
        post_data = crawl_post(bid, log_no)

        if post_data:
            # 메타 정보 병합
            post_data["title"] = post_data["title"] or post_meta["title"]
            post_data["categoryName"] = post_meta.get("categoryName", "")
            post_data["addDate"] = post_meta.get("addDate", "")

            # 캐시 저장
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(post_data, f, ensure_ascii=False, indent=2)

            crawled.append(post_data)
        else:
            print(f"  [건너뜀] {post_meta['title'][:30]}")

        time.sleep(REQUEST_DELAY)

    # 요약 저장
    summary = {
        "blog_id": bid,
        "total_crawled": len(crawled),
        "posts": [{"logNo": p["log_no"], "title": p["title"], "chars": p["char_count"]} for p in crawled],
    }
    with open(CACHE_DIR / "_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 크롤링 완료: {len(crawled)}개 글 ({sum(p['char_count'] for p in crawled):,}자)")
    return crawled


def main():
    import argparse

    parser = argparse.ArgumentParser(description="네이버 블로그 크롤러")
    parser.add_argument("--blog-id", default=None, help="블로그 ID (기본: .env의 BLOG_ID)")
    parser.add_argument("--count", type=int, default=20, help="수집할 글 수 (기본: 20)")
    parser.add_argument("--clear-cache", action="store_true", help="캐시 초기화 후 재수집")
    args = parser.parse_args()

    if args.clear_cache:
        import shutil
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)
            CACHE_DIR.mkdir(parents=True)
            print("캐시가 초기화되었습니다.")

    crawl_blog(args.blog_id, args.count)


if __name__ == "__main__":
    main()
