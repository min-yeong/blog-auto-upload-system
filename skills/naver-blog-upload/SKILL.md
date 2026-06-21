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

## Scope

- Target repo: `/Users/min-yeong/Desktop/project/blog-auto-upload-system`
- Default action: Naver Blog temporary draft only.
- Never publish unless the user explicitly asks for public publishing after preview.
- Keep `.claude/`, `config/.env`, `cache/browser_state/`, and Naver credentials out of chat output.

## Workflow

1. Create a session folder under `openclaw_sessions/YYYYMMDD-HHMMSS/`.
2. Save or copy chat-uploaded images into `openclaw_sessions/<session>/images/`.
3. Ask category-specific questions in chat.
   - Restaurant: place, location, menu, visit reason, waiting, vibe, taste, best menu, value, revisit, map URL.
   - Cafe/dessert: cafe/place, location, menu, visit reason, vibe, taste, visual, value, revisit.
   - Travel: destination, companions, schedule, places, best moment, weather, tips, revisit.
4. Generate `post.json` in the existing `output/latest_post.json` format.
5. Run validation:
   ```bash
   cd /Users/min-yeong/Desktop/project/blog-auto-upload-system
   source venv/bin/activate
   python3 scripts/validate_post.py openclaw_sessions/<session>/post.json
   ```
6. Show title, category, tags, image count, and a short preview. Ask before upload.
7. If confirmed, upload as draft:
   ```bash
   cd /Users/min-yeong/Desktop/project/blog-auto-upload-system
   source venv/bin/activate
   python3 scripts/upload_naver.py --file openclaw_sessions/<session>/post.json
   ```
8. If upload succeeds, delete the project session folder:
   ```bash
   python3 skills/naver-blog-upload/scripts/cleanup_session.py openclaw_sessions/<session>
   ```

## Safety Rules

- Ask before running `scripts/upload_naver.py`.
- Ask again before adding `--publish`.
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

## Storage and Cleanup

- OpenClaw/Telegram may stage inbound media in OpenClaw's own media/session store under `~/.openclaw` while processing chat attachments.
- This skill should copy only the images needed for a blog post into repo-local `openclaw_sessions/<session>/images/`.
- `openclaw_sessions/` is ignored by Git.
- After successful upload, remove the repo-local session folder with `cleanup_session.py`.
- Do not delete OpenClaw's global `~/.openclaw` state from this skill; use OpenClaw maintenance commands separately.
