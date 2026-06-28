#!/usr/bin/env python3
"""Validate OpenClaw-specific blog draft contract before upload."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_RESTAURANT_ANSWERS = [
    "place",
    "ordered_menu",
    "visit_reason",
    "waiting",
    "vibe",
    "taste_by_menu",
    "best_menu",
    "value",
    "revisit",
]

REQUIRED_CAFE_ANSWERS = [
    "place",
    "ordered_menu",
    "visit_reason",
    "vibe",
    "taste",
    "visual",
    "value",
    "revisit",
]

ALLOWED_PLACE_SOURCES = {"user", "web", "naver_map", "mixed"}
ALLOWED_PHOTO_ROLES = {
    "sign",
    "exterior",
    "interior",
    "menu",
    "food_overview",
    "food_detail",
    "drink",
    "dessert",
    "receipt",
    "other",
}
ALLOWED_ORIENTATIONS = {"landscape", "portrait", "square"}
ALLOWED_ACTIONS = {"keep", "rotate", "stitch", "exclude"}
THUMBNAIL_ALLOWED_ROLES = {"food_overview", "sign", "exterior"}
THUMBNAIL_NEVER_ROLES = {
    "menu",
    "receipt",
    "interior",
    "food_detail",
    "drink",
    "dessert",
    "other",
}
LOCATION_SUFFIXES = ("동", "구", "시", "군", "읍", "면", "리")
FORBIDDEN_META_PHRASES = [
    "요청하신",
    "가이드에 맞춰",
    "포스팅 가이드",
    "이번 포스팅",
    "자연스럽게 담아",
    "본문에는",
    "제목과 본문",
]


def fail(message: str) -> None:
    raise SystemExit(f"[FAIL] {message}")


def nonempty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def required_answers_for(category: str) -> list[str]:
    if "카페" in category or "디저트" in category:
        return REQUIRED_CAFE_ANSWERS
    return REQUIRED_RESTAURANT_ANSWERS


def split_terms(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return [term for term in re.split(r"[\s,()/|·]+", value.strip()) if len(term) > 1]


def location_terms(value: str) -> list[str]:
    return [term for term in split_terms(value) if term.endswith(LOCATION_SUFFIXES)]


def text_payload(data: dict) -> str:
    parts = [
        str(data.get("title") or ""),
        str(data.get("content") or ""),
        str(data.get("place") or ""),
    ]
    for block in data.get("blocks", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("content") or ""))
    return "\n".join(parts)


def resolve_post_path(post_path: Path, raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        path = post_path.parent / path
    return str(path.resolve())


def validate_contract(data: dict, post_path: Path) -> list[str]:
    errors: list[str] = []
    contract = data.get("draft_contract")
    if not isinstance(contract, dict):
        return ["draft_contract missing"]

    category = data.get("category", "")
    user_answers = contract.get("user_answers")
    if not isinstance(user_answers, dict):
        errors.append("draft_contract.user_answers missing")
    else:
        missing_answers = [
            key for key in required_answers_for(category)
            if not nonempty(user_answers.get(key))
        ]
        if missing_answers:
            errors.append(f"required user answers missing: {', '.join(missing_answers)}")

    place_info = contract.get("place_info")
    if not isinstance(place_info, dict):
        errors.append("draft_contract.place_info missing")
    else:
        source = place_info.get("source")
        if source not in ALLOWED_PLACE_SOURCES:
            errors.append(f"place_info.source must be one of {sorted(ALLOWED_PLACE_SOURCES)}")
        if not nonempty(place_info.get("source_detail")):
            errors.append("place_info.source_detail missing")
        facts = place_info.get("facts")
        if not isinstance(facts, dict):
            errors.append("place_info.facts missing")
        else:
            for key in ["name", "address", "hours"]:
                if not nonempty(facts.get(key)):
                    errors.append(f"place_info.facts.{key} missing; write '확인 필요' only after asking/searching")
            if isinstance(user_answers, dict):
                user_place = str(user_answers.get("place") or "")
                address = str(facts.get("address") or "")
                user_location_terms = location_terms(user_place)
                if (
                    user_location_terms
                    and address
                    and address != "확인 필요"
                    and not any(term in address for term in user_location_terms)
                ):
                    errors.append(
                        "place_info.facts.address does not match user place hint: "
                        f"user_place='{user_place}', address='{address}'"
                    )
                top_level_place = str(data.get("place") or "")
                if user_location_terms and not any(term in top_level_place for term in user_location_terms):
                    errors.append(
                        "top-level place must include the user's area hint for Naver place widget "
                        f"(missing one of: {', '.join(user_location_terms)})"
                    )

    body_text = text_payload(data)
    for phrase in FORBIDDEN_META_PHRASES:
        if phrase in body_text:
            errors.append(f"meta/instruction phrase must not appear in blog text: {phrase}")

    image_blocks = [b for b in data.get("blocks", []) if b.get("type") == "image"]
    image_paths = [
        resolve_post_path(post_path, p)
        for block in image_blocks
        for p in block.get("paths", [])
    ]
    photo_plan = contract.get("photo_plan")
    plan_by_path: dict[str, dict] = {}
    if not isinstance(photo_plan, list) or not photo_plan:
        errors.append("draft_contract.photo_plan missing")
    else:
        planned_paths = set()
        for i, item in enumerate(photo_plan):
            if not isinstance(item, dict):
                errors.append(f"photo_plan[{i}] must be an object")
                continue
            path = item.get("path")
            if not nonempty(path):
                errors.append(f"photo_plan[{i}].path missing")
            else:
                resolved = resolve_post_path(post_path, path)
                planned_paths.add(resolved)
                plan_by_path[resolved] = item
                if not Path(resolved).exists():
                    errors.append(f"photo_plan[{i}].path file not found: {resolved}")
            if item.get("role") not in ALLOWED_PHOTO_ROLES:
                errors.append(f"photo_plan[{i}].role invalid")
            if item.get("orientation") not in ALLOWED_ORIENTATIONS:
                errors.append(f"photo_plan[{i}].orientation invalid")
            if item.get("action") not in ALLOWED_ACTIONS:
                errors.append(f"photo_plan[{i}].action invalid")
            if item.get("action") == "rotate" and item.get("rotate_degrees") not in {90, 180, 270}:
                errors.append(f"photo_plan[{i}].rotate_degrees must be 90/180/270")
            if not nonempty(item.get("caption_intent")):
                errors.append(f"photo_plan[{i}].caption_intent missing")

        missing_from_plan = sorted(set(image_paths) - planned_paths)
        if missing_from_plan:
            errors.append(f"image block paths missing from photo_plan: {len(missing_from_plan)}")

    thumbnail = data.get("thumbnail")
    thumbnail_decision = contract.get("thumbnail_decision")
    if not isinstance(thumbnail_decision, dict):
        errors.append("draft_contract.thumbnail_decision missing")
    else:
        chosen = thumbnail_decision.get("path")
        chosen_resolved = ""
        if thumbnail and chosen:
            chosen_resolved = resolve_post_path(post_path, chosen)
            thumbnail_resolved = resolve_post_path(post_path, thumbnail)
            if chosen_resolved != thumbnail_resolved:
                errors.append("thumbnail_decision.path does not match top-level thumbnail")
        thumbnail_role = thumbnail_decision.get("role")
        if thumbnail_role not in THUMBNAIL_ALLOWED_ROLES:
            errors.append("thumbnail_decision.role must be food_overview, sign, or exterior")
        if not nonempty(thumbnail_decision.get("reason")):
            errors.append("thumbnail_decision.reason missing")
        if chosen_resolved and chosen_resolved in plan_by_path:
            planned_role = plan_by_path[chosen_resolved].get("role")
            if planned_role != thumbnail_role:
                errors.append(
                    "thumbnail_decision.role does not match photo_plan role for selected image"
                )
            if planned_role in THUMBNAIL_NEVER_ROLES:
                errors.append(f"thumbnail must not use {planned_role} image")

        if isinstance(photo_plan, list):
            usable_items = [
                item for item in photo_plan
                if isinstance(item, dict) and item.get("action") != "exclude"
            ]
            food_overview_paths = {
                resolve_post_path(post_path, item.get("path"))
                for item in usable_items
                if item.get("role") == "food_overview" and nonempty(item.get("path"))
            }
            fallback_paths = {
                resolve_post_path(post_path, item.get("path"))
                for item in usable_items
                if item.get("role") in {"sign", "exterior"} and nonempty(item.get("path"))
            }
            if food_overview_paths and chosen_resolved and chosen_resolved not in food_overview_paths:
                errors.append("thumbnail must use food_overview when any usable food_overview image exists")
            if not food_overview_paths and fallback_paths and chosen_resolved and chosen_resolved not in fallback_paths:
                errors.append("thumbnail must use sign/exterior when no food_overview exists")

    subjective_claims = contract.get("subjective_claims")
    if not isinstance(subjective_claims, list) or not subjective_claims:
        errors.append("draft_contract.subjective_claims missing")
    else:
        for i, item in enumerate(subjective_claims):
            if not isinstance(item, dict) or not nonempty(item.get("claim")) or not nonempty(item.get("source_answer_key")):
                errors.append(f"subjective_claims[{i}] must include claim and source_answer_key")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate OpenClaw blog post contract")
    parser.add_argument("post_json")
    args = parser.parse_args()

    post_path = Path(args.post_json)
    if not post_path.exists():
        fail(f"post json not found: {post_path}")

    data = json.loads(post_path.read_text(encoding="utf-8"))
    errors = validate_contract(data, post_path.resolve())
    if errors:
        print("\nOpenClaw draft contract validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("OpenClaw draft contract validation passed.")


if __name__ == "__main__":
    main()
