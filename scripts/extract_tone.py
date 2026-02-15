#!/usr/bin/env python3
"""톤 프로파일 추출: 크롤링된 글에서 어투/스타일 분석 → tone_profile.json 생성.

Stage A: Python 통계 분석 (토큰 0)
  - 평균 문장 길이, 자주 쓰는 어미, 이모지 사용 빈도, 단락 구조 등
Stage B: 대표 발췌문 3~5개만 출력 → Claude가 분석 (~5,000 토큰, 1회)
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache" / "crawled_posts"
TONE_FILE = PROJECT_ROOT / "cache" / "tone_profile.json"

# 한국어 어미 패턴
ENDING_PATTERNS = {
    "해요체": re.compile(r"(?:해요|예요|이에요|했어요|돼요|네요|세요|할게요|줄게요|볼게요)\s*[.!?~]*\s*$"),
    "합쇼체": re.compile(r"(?:합니다|됩니다|있습니다|했습니다|겠습니다)\s*[.!?~]*\s*$"),
    "반말체": re.compile(r"(?:했어|했다|이야|인데|거든|잖아|같아|좋아|맛있어)\s*[.!?~]*\s*$"),
    "명사형": re.compile(r"(?:것|거|중|듯|편|점|곳)\s*[.!?~]*\s*$"),
    "감탄형": re.compile(r"[!]{1,3}\s*$"),
}

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U0001f900-\U0001f9FF"
    "\U0001fa00-\U0001fa6F"
    "\U0001fa70-\U0001faFF"
    "]+",
    flags=re.UNICODE,
)

SPECIAL_CHARS = re.compile(r"[ㅋㅎㅠㅜ]{2,}")


def load_crawled_posts() -> list[dict]:
    """캐시에서 크롤링된 포스트 로드."""
    if not CACHE_DIR.exists():
        print("[오류] 크롤링된 데이터가 없습니다. 먼저 crawl_blog.py를 실행하세요.", file=sys.stderr)
        sys.exit(1)

    posts = []
    for f in sorted(CACHE_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if data.get("content") and data.get("char_count", 0) > 100:
            posts.append(data)

    if not posts:
        print("[오류] 유효한 포스트가 없습니다.", file=sys.stderr)
        sys.exit(1)

    return posts


def analyze_statistics(posts: list[dict]) -> dict:
    """Stage A: Python 통계 분석 (토큰 0).

    Returns:
        통계 분석 결과 딕셔너리
    """
    all_sentences = []
    ending_counts = Counter()
    emoji_count = 0
    special_char_count = 0
    total_chars = 0
    paragraph_lengths = []

    for post in posts:
        content = post["content"]
        total_chars += len(content)

        # 문장 분리
        sentences = re.split(r"[.!?]\s+|\n+", content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        all_sentences.extend(sentences)

        # 어미 분석
        for sent in sentences:
            for style, pattern in ENDING_PATTERNS.items():
                if pattern.search(sent):
                    ending_counts[style] += 1
                    break

        # 이모지/특수문자 분석
        emoji_count += len(EMOJI_PATTERN.findall(content))
        special_char_count += len(SPECIAL_CHARS.findall(content))

        # 단락 분석
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        paragraph_lengths.extend([len(p) for p in paragraphs])

    # 결과 집계
    total_endings = sum(ending_counts.values()) or 1
    sentence_lengths = [len(s) for s in all_sentences]

    stats = {
        "post_count": len(posts),
        "avg_post_length": round(total_chars / len(posts)),
        "avg_sentence_length": round(sum(sentence_lengths) / max(len(sentence_lengths), 1), 1),
        "avg_paragraph_length": round(sum(paragraph_lengths) / max(len(paragraph_lengths), 1), 1),
        "ending_distribution": {
            style: round(count / total_endings * 100, 1)
            for style, count in ending_counts.most_common()
        },
        "primary_style": ending_counts.most_common(1)[0][0] if ending_counts else "혼합",
        "emoji_per_post": round(emoji_count / len(posts), 1),
        "special_chars_per_post": round(special_char_count / len(posts), 1),
        "uses_emoji": emoji_count > len(posts) * 0.5,
        "uses_special_chars": special_char_count > len(posts),
    }

    return stats


def select_representative_excerpts(posts: list[dict], count: int = 5) -> list[dict]:
    """Stage B 준비: 대표 발췌문 선택.

    가장 다양한 스타일을 보여주는 글에서 핵심 부분 추출.
    """
    # 글 길이 순으로 정렬 (중간 길이 글이 가장 대표적)
    sorted_posts = sorted(posts, key=lambda p: p["char_count"])
    n = len(sorted_posts)

    # 다양한 위치에서 선택: 짧은 글 1개, 중간 2개, 긴 글 1개, 최신 1개
    indices = set()
    if n >= 5:
        indices.update([0, n // 3, n // 2, 2 * n // 3, n - 1])
    else:
        indices = set(range(n))

    selected = []
    for idx in sorted(indices):
        post = sorted_posts[idx]
        content = post["content"]

        # 글의 도입부 + 중간부 발췌 (각 200자)
        intro = content[:200].strip()
        mid_start = len(content) // 2
        middle = content[mid_start:mid_start + 200].strip()

        selected.append({
            "title": post.get("title", ""),
            "category": post.get("categoryName", ""),
            "excerpt_intro": intro,
            "excerpt_middle": middle,
            "char_count": post["char_count"],
        })

    return selected[:count]


def build_tone_profile(stats: dict, excerpts: list[dict]) -> dict:
    """톤 프로파일 JSON 구조 생성.

    이 결과는 Claude에게 전달되어 최종 분석이 수행됨.
    Stage B 분석 결과를 포함할 자리를 마련.
    """
    profile = {
        "_meta": {
            "version": "1.0",
            "description": "블로그 어투 프로파일 - Claude 글 생성 시 참조",
            "post_count_analyzed": stats["post_count"],
        },
        "statistics": stats,
        "representative_excerpts": excerpts,
        "style_guide": {
            "primary_ending": stats["primary_style"],
            "ending_distribution": stats["ending_distribution"],
            "avg_length": stats["avg_post_length"],
            "emoji_usage": "사용" if stats["uses_emoji"] else "미사용",
            "special_chars": "사용" if stats["uses_special_chars"] else "미사용",
            "instruction": (
                f"이 블로그는 주로 '{stats['primary_style']}'를 사용합니다. "
                f"평균 글 길이는 약 {stats['avg_post_length']}자이며, "
                f"문장당 평균 {stats['avg_sentence_length']}자입니다. "
                f"이모지는 {'자주 사용' if stats['uses_emoji'] else '거의 미사용'}합니다."
            ),
        },
        "claude_analysis": None,  # /blog-crawl 커맨드에서 Claude가 채워줌
    }

    return profile


def extract_tone(force: bool = False) -> dict:
    """메인 함수: 크롤링 데이터에서 톤 프로파일 추출.

    Args:
        force: True면 기존 캐시 무시하고 재생성

    Returns:
        톤 프로파일 딕셔너리
    """
    # 캐시 확인
    if TONE_FILE.exists() and not force:
        print(f"ℹ️  기존 tone_profile.json 사용 중. 재생성하려면 --force 옵션 사용.")
        with open(TONE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # Stage A: 통계 분석
    print("📊 Stage A: 통계 분석 중...")
    posts = load_crawled_posts()
    stats = analyze_statistics(posts)
    print(f"  → {stats['post_count']}개 글 분석 완료")
    print(f"  → 주요 어투: {stats['primary_style']}")
    print(f"  → 평균 글 길이: {stats['avg_post_length']}자")

    # Stage B 준비: 대표 발췌문 선택
    print("\n📝 Stage B 준비: 대표 발췌문 선택 중...")
    excerpts = select_representative_excerpts(posts)
    print(f"  → {len(excerpts)}개 발췌문 선택됨")

    # 프로파일 생성
    profile = build_tone_profile(stats, excerpts)

    # 저장
    with open(TONE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    print(f"\n✅ tone_profile.json 생성 완료 ({TONE_FILE})")
    print("  → /blog-crawl 커맨드로 Claude 분석을 추가하면 더 정확한 어투 재현이 가능합니다.")

    return profile


def main():
    import argparse

    parser = argparse.ArgumentParser(description="블로그 톤 프로파일 추출")
    parser.add_argument("--force", action="store_true", help="기존 캐시 무시하고 재생성")
    parser.add_argument("--stats-only", action="store_true", help="통계만 출력 (저장 안 함)")
    args = parser.parse_args()

    if args.stats_only:
        posts = load_crawled_posts()
        stats = analyze_statistics(posts)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    extract_tone(args.force)


if __name__ == "__main__":
    main()
