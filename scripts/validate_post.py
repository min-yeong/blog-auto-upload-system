#!/usr/bin/env python3
"""블로그 포스트 JSON 검증 스크립트.

생성된 latest_post.json이 템플릿 규칙을 준수하는지 검증.

사용법:
    python3 scripts/validate_post.py output/latest_post.json
"""

import json
import sys
from pathlib import Path


def validate_post(data: dict) -> list[dict]:
    """포스트 데이터를 검증하고 결과 리스트를 반환.

    Returns:
        list of {"rule": str, "pass": bool, "detail": str}
    """
    results = []
    blocks = data.get("blocks", [])

    # 1. 필수 필드 확인
    required_fields = ["title", "category", "tags", "thumbnail", "place"]
    missing = [f for f in required_fields if not data.get(f)]
    results.append({
        "rule": "필수 필드",
        "pass": len(missing) == 0,
        "detail": f"누락: {', '.join(missing)}" if missing else "title, category, tags, thumbnail, place 모두 존재",
    })

    # 2. 글자수 (텍스트 블록 합산 1200자 이상)
    text_blocks = [b for b in blocks if b.get("type") == "text"]
    total_chars = sum(len(b.get("content", "")) for b in text_blocks)
    results.append({
        "rule": "글자수 (≥1200자)",
        "pass": total_chars >= 1200,
        "detail": f"현재 {total_chars}자" + ("" if total_chars >= 1200 else f" → {1200 - total_chars}자 부족"),
    })

    # 3. 구분선 (separator 블록 최소 2개)
    sep_count = sum(1 for b in blocks if b.get("type") == "separator")
    results.append({
        "rule": "구분선 (≥2개)",
        "pass": sep_count >= 2,
        "detail": f"현재 {sep_count}개" + ("" if sep_count >= 2 else " → 영업정보 뒤 + 최종평가 앞에 필요"),
    })

    # 4. 가게이름 (첫 번째 텍스트 블록이 짧은 텍스트 - 인용구로 렌더링됨)
    has_short_name = False
    if text_blocks:
        first_text = text_blocks[0].get("content", "")
        has_short_name = len(first_text) <= 30 and "\n" not in first_text
    results.append({
        "rule": "가게이름 (≤30자, 1줄)",
        "pass": has_short_name,
        "detail": f"'{text_blocks[0].get('content', '')[:20]}' ({len(text_blocks[0].get('content', ''))}자)" if text_blocks else "텍스트 블록 없음",
    })

    # 5. 영업정보 (두 번째 텍스트 블록에 "영업시간" 키워드)
    has_business_info = False
    if len(text_blocks) >= 2:
        second_text = text_blocks[1].get("content", "")
        has_business_info = "영업시간" in second_text or "영업" in second_text
    results.append({
        "rule": "영업정보",
        "pass": has_business_info,
        "detail": "두 번째 텍스트 블록에 영업시간 포함" if has_business_info else "두 번째 텍스트 블록에 '영업시간' 키워드 없음",
    })

    # 5. 최종평가 (마지막 텍스트 블록에 재방문/총평 관련 내용)
    has_final_review = False
    if text_blocks:
        last_text = text_blocks[-1].get("content", "")
        review_keywords = ["재방문", "총평", "가성비", "다시 가", "또 가"]
        has_final_review = any(kw in last_text for kw in review_keywords)
    results.append({
        "rule": "최종평가",
        "pass": has_final_review,
        "detail": "마지막 텍스트 블록에 재방문/총평 내용 포함" if has_final_review else "마지막 텍스트 블록에 재방문/총평 관련 키워드 없음",
    })

    # 6. 줄바꿈 (텍스트 블록 내 각 줄 평균 50자 이하)
    all_lines = []
    for b in text_blocks:
        lines = [l for l in b.get("content", "").split("\n") if l.strip()]
        all_lines.extend(lines)
    avg_line_len = sum(len(l) for l in all_lines) / max(len(all_lines), 1)
    results.append({
        "rule": "줄바꿈 (평균 ≤50자/줄)",
        "pass": avg_line_len <= 50,
        "detail": f"평균 {avg_line_len:.1f}자/줄" + ("" if avg_line_len <= 50 else " → 한 줄에 한 문장씩 나눠주세요"),
    })

    # 7. 태그 (8개 이상)
    tags = data.get("tags", [])
    results.append({
        "rule": "태그 (≥8개)",
        "pass": len(tags) >= 8,
        "detail": f"현재 {len(tags)}개" + ("" if len(tags) >= 8 else f" → {8 - len(tags)}개 추가 필요"),
    })

    # 8. 블록 순서 (text → text → separator → ... → separator → text)
    block_types = [b.get("type") for b in blocks]
    order_ok = _check_block_order(block_types)
    results.append({
        "rule": "블록 순서",
        "pass": order_ok,
        "detail": "text→text→separator→(본문)→separator→text 패턴 준수" if order_ok else f"현재 순서: {' → '.join(block_types)}",
    })

    return results


def _check_block_order(types: list[str]) -> bool:
    """블록 순서 패턴 검증.

    기대 패턴: text, text, separator, ...(text/image), separator, text
    """
    if len(types) < 5:
        return False

    # 첫 두 블록이 text
    if types[0] != "text" or types[1] != "text":
        return False

    # separator 위치 찾기
    sep_indices = [i for i, t in enumerate(types) if t == "separator"]
    if len(sep_indices) < 2:
        return False

    first_sep = sep_indices[0]
    last_sep = sep_indices[-1]

    # 첫 번째 separator가 두 번째 text 뒤에 위치
    if first_sep < 2:
        return False

    # 마지막 separator 뒤에 text 블록이 있어야 함
    if last_sep >= len(types) - 1:
        return False
    if types[last_sep + 1] != "text":
        return False

    # 마지막 블록이 text
    if types[-1] != "text":
        return False

    return True


def print_results(results: list[dict]) -> bool:
    """검증 결과를 출력하고 전체 통과 여부를 반환."""
    all_pass = True
    print("\n" + "=" * 50)
    print("  블로그 포스트 검증 결과")
    print("=" * 50)

    for r in results:
        icon = "PASS" if r["pass"] else "FAIL"
        marker = "  " if r["pass"] else "  "
        print(f"{marker}[{icon}] {r['rule']}: {r['detail']}")
        if not r["pass"]:
            all_pass = False

    print("=" * 50)
    if all_pass:
        print("  모든 검증 통과!")
    else:
        failed = [r["rule"] for r in results if not r["pass"]]
        print(f"  {len(failed)}개 항목 미달: {', '.join(failed)}")
    print("=" * 50 + "\n")

    return all_pass


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 scripts/validate_post.py <json_path>")
        print("예시: python3 scripts/validate_post.py output/latest_post.json")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"파일을 찾을 수 없습니다: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = validate_post(data)
    all_pass = print_results(results)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
