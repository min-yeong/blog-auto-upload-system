# 네이버 블로그 자동 업로드 시스템

Claude Code 커맨드 하나로 네이버 블로그 글을 자동 생성하고 업로드하는 시스템.

## 사용법 (3줄 요약)

```
1. 사진을 바탕화면에 저장
2. Claude Code에서 /blog-post "주제" 실행
3. 질문에 답하면 자동으로 글 생성 + 업로드
```

---

## 전체 워크플로우

### Step 1: 사진 준비
블로그에 올릴 사진을 **바탕화면(~/Desktop)** 에 저장해두세요.
- 카카오톡에서 보낸 사진, 스크린샷 등 아무거나 OK
- HEIC 파일도 자동 변환됨
- 최근 48시간 내 파일만 스캔됨

### Step 2: 커맨드 실행
```
/blog-post "김화칼국수 대전 맛집 리뷰"
```

### Step 3: 질문에 답하기
카테고리에 따라 다른 질문이 나옵니다.

**맛집일지 예시:**
```
1차) 식당 이름, 위치, 먹은 메뉴
2차) 방문 계기, 웨이팅 여부, 가게 분위기
3차) 각 메뉴 맛 상세, 제일 맛있던 메뉴
4차) 가성비, 재방문 의사, 참고 정보
```

짧게 답해도 됩니다:
```
Q: 비빔칼국수 맛은 어땠어?
A: 양념이 맛있었어 특히 매콤새콤한 게 좋았음
```

### Step 4: 미리보기 확인
글이 생성되면 미리보기가 나옵니다.
- 수정하고 싶으면 "여기 좀 바꿔줘" 하면 됨
- OK면 "업로드해줘" 하면 됨

### Step 5: 자동 업로드
- 기본: **임시저장(비공개)** 으로 업로드
- 네이버 블로그에서 직접 확인 후 발행 가능
- 태그는 수동으로 추가 필요 (자동 입력 미지원)

---

## Claude Code 커맨드

| 커맨드 | 설명 | 언제 쓰나 |
|--------|------|-----------|
| `/blog-post "주제"` | 글 작성 + 업로드 | **매번** |
| `/blog-setup` | 초기 설정 | **최초 1회** |
| `/blog-crawl` | 어투 재학습 | 글 스타일 바뀌었을 때 |

---

## 초기 설정 (최초 1회)

### 1. 의존성 설치
```bash
cd ~/Desktop/민영/project/blog-auto-upload-system
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

### 2. 환경 변수
`config/.env` 파일 편집:
```
NAVER_ID=네이버아이디
NAVER_PW=네이버비밀번호
BLOG_ID=블로그아이디
```
> `BLOG_ID`는 `blog.naver.com/여기부분`

### 3. 어투 학습
```
/blog-setup
```
기존 블로그 글을 크롤링해서 어투 프로파일을 자동 생성합니다.

---

## 카테고리별 질문 구조

### 맛집일지
| 단계 | 질문 내용 |
|------|-----------|
| 1차 (기본) | 식당 이름, 위치, 메뉴 |
| 2차 (경험) | 방문 계기, 웨이팅, 분위기 |
| 3차 (맛) | 메뉴별 맛 상세, 베스트 메뉴 |
| 4차 (마무리) | 가성비, 재방문, 참고 정보 |

### 카페일지
| 단계 | 질문 내용 |
|------|-----------|
| 1차 (기본) | 카페 이름, 위치, 메뉴 |
| 2차 (경험) | 방문 계기, 분위기, 작업 적합성 |
| 3차 (메뉴) | 맛, 비주얼, 가격 대비 양 |
| 4차 (마무리) | 재방문, 추천 포인트 |

### 여행일지
| 단계 | 질문 내용 |
|------|-----------|
| 1차 (기본) | 여행지, 동행, 일정 |
| 2차 (경험) | 방문 장소, 베스트 장소, 날씨 |
| 3차 (상세) | 장소별 활동, 분위기 |
| 4차 (마무리) | 재방문, 여행 팁 |

---

## 글 생성 특징

- **어투**: 기존 블로그 글 분석 기반 (반말체 87.5%, 해요체 12.5%)
- **분량**: 2000자 이상
- **이미지 배치**: 텍스트 사이사이에 자동 배치 (마지막에 몰아넣지 않음)
- **SEO**: 제목에 `[가게명 지역]` 형식, 태그 8~12개 자동 생성
- **정보 보충**: 영업시간/주차/가격 등은 웹 검색으로 자동 보충

---

## 파일 구조

```
blog-auto-upload-system/
├── scripts/
│   ├── crawl_blog.py          # 블로그 글 크롤링
│   ├── extract_tone.py        # 어투 분석
│   ├── scan_images.py         # 바탕화면 이미지 스캔
│   ├── upload_naver.py        # 네이버 업로드 (Playwright)
│   └── utils/
│       ├── naver_auth.py      # 로그인/세션 관리
│       └── image_utils.py     # HEIC→JPEG, 리사이즈
├── cache/
│   ├── tone_profile.json      # 어투 프로파일
│   ├── crawled_posts/         # 크롤링 데이터
│   └── browser_state/         # 로그인 세션
├── templates/
│   └── blog_prompt.md         # 글 생성 프롬프트
├── config/
│   ├── .env                   # 자격증명
│   └── categories.json        # 카테고리 목록
├── output/                    # 생성된 글 JSON 백업
├── venv/                      # Python 가상환경
├── requirements.txt
└── .gitignore
```

## 개별 스크립트 테스트

```bash
source venv/bin/activate

# 바탕화면 이미지 스캔
python3 scripts/scan_images.py

# 블로그 크롤링
python3 scripts/crawl_blog.py --count 5

# 톤 프로파일 추출
python3 scripts/extract_tone.py --force

# 업로드 테스트 (셀렉터 확인만)
python3 scripts/upload_naver.py --test

# JSON 파일로 업로드
python3 scripts/upload_naver.py --file output/latest_post.json

# 발행 모드 (비공개 아닌 공개)
python3 scripts/upload_naver.py --file output/latest_post.json --publish
```

## 알려진 제한사항

- **태그 자동 입력 미지원**: 네이버 에디터 태그 입력 셀렉터가 불안정. 업로드 후 수동 추가 필요
- **캡차 대응**: 자동 로그인 시 캡차가 나오면 브라우저에서 직접 해결 필요
- **이미지 순서**: 파일명 기준 정렬. 원하는 순서가 있으면 파일명 조정 필요

## 보안

- `.env`: `chmod 600` (소유자만 접근)
- 자격증명은 Python이 직접 로드 (Claude 컨텍스트에 노출 안 됨)
- 기본 업로드: **임시저장** (실수 방지)
- `.gitignore`에 `.env`, `browser_state/`, `crawled_posts/` 포함
