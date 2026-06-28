---
name: naver-blog-upload
description: "Create Korean Naver Blog drafts from chat-uploaded photos and Q&A, then upload them with the local Playwright uploader."
allowed-tools:
  - bash
  - read
  - write
  - edit
user-invocable: true
---

# Naver Blog Upload

Use when the user asks to make/upload a Naver blog post from photos in an OpenClaw chat.
The core rule is evidence first: do not invent place facts, photo meaning, taste, mood, value, or revisit intent.

## Scope

- Target repo: `/Users/min-yeong/Desktop/project/blog-auto-upload-system`
- Default action: Naver Blog temporary draft only.
- Never publish unless the user explicitly asks for public publishing after preview.
- Keep `.claude/`, `config/.env`, `cache/browser_state/`, and Naver credentials out of chat output.

## Workflow

1. Create a session folder under `openclaw_sessions/YYYYMMDD-HHMMSS/`.
2. Save or copy chat-uploaded images into `openclaw_sessions/<session>/images/`.
3. Inventory images before drafting:
   ```bash
   python3 skills/naver-blog-upload/scripts/analyze_images.py openclaw_sessions/<session>
   ```
   Use this to know each image path, width, height, and orientation. Visually inspect images from chat or local files before assigning roles.
4. Gather facts and user experience before drafting.
   - Restaurant: place, ordered menu, visit reason, waiting, vibe, taste by menu, best menu, value, revisit, and map URL or address.
   - Cafe/dessert: place, ordered menu, visit reason, vibe, taste, visual, value, revisit, and map URL or address.
   - Travel: destination, companions, schedule, places, best moment, weather, tips, revisit.
   - If required user experience is missing, ask follow-up questions. Do not fill taste/vibe/value/revisit from imagination.
   - If place facts are missing, ask the user first. If still missing and web/search/map lookup is available, look it up and keep source details. If neither works, write `확인 필요` instead of inventing facts.
   - For Naver place-widget insertion, never rely on store name alone when the name is common. If the user gives a neighborhood/district/street hint such as `쌍문동`, `도봉구`, or `쌍리단길`, the selected place candidate must match that area. If search/map results point to a different area, stop and ask for the Naver Map URL instead of guessing.
   - Set top-level `place` to a disambiguated query such as `매향 쌍문동` or `매향 도봉구`, not just `매향`, unless the user gave a Naver Map URL or an exact unique place.
5. Build a photo plan before writing.
   - Classify every usable image role: `sign`, `exterior`, `interior`, `menu`, `food_overview`, `food_detail`, `drink`, `dessert`, `receipt`, `other`.
   - Check orientation from `analyze_images.py` and visual content. If the image looks sideways, rotate before upload or mark `action: rotate`.
   - Do not stitch unrelated portrait/landscape images just because there are two photos. Stitch only when the pair belongs together and the composition remains natural.
   - Thumbnail priority is strict: `food_overview` showing the overall food/table first. If no good food overview exists, use `sign` or `exterior`. Never use `menu`, `receipt`, `interior`, `food_detail`, `drink`, `dessert`, or `other` as the thumbnail unless the user explicitly chooses it.
   - If any usable `food_overview` exists in `photo_plan`, the thumbnail must be one of those images. If no `food_overview` exists but `sign`/`exterior` exists, the thumbnail must be `sign` or `exterior`.
6. Generate `post.json` in the existing `output/latest_post.json` format plus the required `draft_contract` metadata described below.
7. Run both validations:
   ```bash
   cd /Users/min-yeong/Desktop/project/blog-auto-upload-system
   source venv/bin/activate
   python3 scripts/validate_post.py openclaw_sessions/<session>/post.json
   python3 skills/naver-blog-upload/scripts/validate_contract.py openclaw_sessions/<session>/post.json
   ```
8. Show title, category, tags, image count, place-info source, thumbnail reason, photo plan summary, and a short preview. Ask before upload.
9. If confirmed, upload as draft:
   ```bash
   cd /Users/min-yeong/Desktop/project/blog-auto-upload-system
   source venv/bin/activate
   python3 scripts/upload_naver.py --file openclaw_sessions/<session>/post.json
   ```
10. If upload succeeds, delete the project session folder:
   ```bash
   python3 skills/naver-blog-upload/scripts/cleanup_session.py openclaw_sessions/<session>
   ```

## Safety Rules

- Ask before running `scripts/upload_naver.py`.
- Ask again before adding `--publish`.
- Ask missing subjective questions before drafting. Required subjective fields cannot be inferred from photos or place data.
- Do not claim "맛있다", "깔끔하다", "재방문 의사", "가성비 좋다", "웨이팅 없음", or similar unless the user said it or a cited source supports the factual part.
- Do not write fake opening hours, address, phone, menu, or parking info. Use user answer, web/map lookup, or `확인 필요`.
- Do not copy task instructions, prompt wording, or review-guide wording into the blog body. Phrases like "요청하신", "가이드에 맞춰", "이번 포스팅", "자연스럽게 담아봤다", or descriptions of how the post was written are meta text and must not appear in `title`, `content`, or text blocks.
- If browser shows captcha or 2FA, tell the user to complete it on the Mac.
- If upload fails, report the error and mention `output/error_screenshot.png` if it exists.
- Delete `openclaw_sessions/<session>` only after successful upload or explicit user confirmation.
- Do not run arbitrary shell commands outside this repo for this workflow.

## Post JSON Notes

- Use absolute image paths from the session folder.
- Use `thumbnail` as one of the image paths included in `blocks`.
- Put text and image blocks alternately.
- Include at least two `separator` blocks.
- Use 8-12 tags.
- Keep tone aligned with `cache/tone_profile.json` if available.
- Use `{"type":"image","paths":[...],"stitch":false}` when images should stay separate. The uploader honors `stitch:false`.
- Add `draft_contract` at the top level. It is validation metadata and is ignored by the uploader.

Required `draft_contract` shape:

```json
{
  "draft_contract": {
    "user_answers": {
      "place": "...",
      "ordered_menu": "...",
      "visit_reason": "...",
      "waiting": "...",
      "vibe": "...",
      "taste_by_menu": "...",
      "best_menu": "...",
      "value": "...",
      "revisit": "..."
    },
    "place_info": {
      "source": "user | web | naver_map | mixed",
      "source_detail": "user answer, search URL, or map URL",
      "facts": {
        "name": "...",
        "address": "...",
        "hours": "..."
      }
    },
    "photo_plan": [
      {
        "path": "/abs/path.jpg",
        "role": "food_overview",
        "orientation": "landscape",
        "action": "keep",
        "caption_intent": "why this photo appears here"
      }
    ],
    "thumbnail_decision": {
      "path": "/abs/path.jpg",
      "role": "food_overview",
      "reason": "overall food/table photo; if unavailable, explain sign/exterior fallback"
    },
    "subjective_claims": [
      {
        "claim": "본문에 들어간 느낌/맛/재방문 문장",
        "source_answer_key": "taste_by_menu"
      }
    ]
  }
}
```

If any required field is missing, stop and ask the user. Do not draft around the missing field.

## Storage and Cleanup

- OpenClaw/Telegram may stage inbound media in OpenClaw's own media/session store under `~/.openclaw` while processing chat attachments.
- This skill should copy only the images needed for a blog post into repo-local `openclaw_sessions/<session>/images/`.
- `openclaw_sessions/` is ignored by Git.
- After successful upload, remove the repo-local session folder with `cleanup_session.py`.
- Do not delete OpenClaw's global `~/.openclaw` state from this skill; use OpenClaw maintenance commands separately.
