# 블로그 업로드 사용 가이드

## OpenClaw 로컬 상주 방식

OpenClaw를 이 맥에 설치해두고, 채팅앱에서 사진과 답변을 받아 네이버 블로그 임시저장까지 처리하는 방식.

### 현재 설치 상태 확인

```bash
openclaw gateway status
openclaw skills info naver-blog-upload
openclaw models status
```

정상 기준:

- Gateway: `Runtime: running`
- Skill: `naver-blog-upload ✓ Ready`
- Model auth: `status=usable`

### 채팅앱 연결

OpenClaw 채널 연결은 사용할 앱에 따라 다름.

```bash
# 지원 채널 확인
openclaw channels list --all

# Telegram 예시: BotFather에서 받은 bot token 필요
openclaw channels add --channel telegram --token <BOT_TOKEN>

# WhatsApp 예시: QR/login 흐름
openclaw channels login --channel whatsapp
```

채널 연결 후 채팅에서 이렇게 요청:

```text
네이버 블로그 글 만들어줘. 사진 올릴게.
```

또는 skill을 직접 지칭:

```text
naver-blog-upload 써서 이 사진들로 블로그 임시저장해줘
```

### OpenClaw 작업 흐름

1. 채팅앱에 사진 업로드
2. OpenClaw가 카테고리와 필요한 질문을 확인
3. 답변을 바탕으로 `openclaw_sessions/<세션>/post.json` 생성
4. `scripts/validate_post.py`로 검증
5. 업로드 전 사용자 확인
6. `scripts/upload_naver.py --file ...` 실행
7. 네이버 블로그에 임시저장

### 주의

- 기본은 임시저장.
- 공개 발행은 채팅에서 명시적으로 요청했을 때만.
- 캡차/2차 인증은 맥에 뜬 브라우저에서 직접 처리.
- `config/.env`, `cache/browser_state/`, 네이버 세션 정보는 채팅에 출력하지 않음.

---

## 매번 하는 것

### 1. 사진 바탕화면에 저장
카카오톡/갤러리에서 사진을 **바탕화면**에 저장

### 2. Claude Code 열고 커맨드 실행
```
/blog-post "식당이름 지역 리뷰"
```

### 3. 질문에 답하기
카테고리 선택 후 4단계 질문이 나옴
- 짧게 답해도 OK
- 모르는 건 "몰라" 하면 웹검색으로 보충됨

### 4. 미리보기 확인
- 수정: "여기 바꿔줘" / "좀 더 길게" / "이 부분 빼줘"
- 확인: "업로드해줘"

### 5. 네이버에서 확인
- 임시저장(비공개)으로 올라감
- 태그는 직접 추가해야 됨
- 확인 후 발행 버튼 누르면 끝

---

## 가끔 하는 것

| 상황 | 하는 것 |
|------|---------|
| 글 스타일 바꿨을 때 | `/blog-crawl` |
| 비밀번호 변경 | `config/.env` 수정 |
| 로그인 풀렸을 때 | 자동 재로그인됨 (캡차 나오면 브라우저에서 직접) |

---

## 팁

- 사진은 **올리기 전에** 바탕화면에 저장 (48시간 이내 파일만 스캔)
- 사진 많을수록 글이 풍성해짐 (외관/내부/메뉴판/음식/디테일)
- 맛 표현은 구체적으로 답할수록 좋음 ("맛있었어" < "양념이 매콤새콤했어")
- 발행하고 싶으면 "발행으로 올려줘" 라고 하면 됨
