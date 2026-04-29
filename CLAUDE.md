# 주식 브리핑 사이트 (stock-briefing)

## 프로젝트 목표

매일 오전 8시에 자동으로 주식 시장 데이터를 수집하고, Anthropic API로 브리핑을 생성한 뒤, HTML 페이지로 만들어 GitHub Pages에 자동 배포하는 시스템을 구축한다.

- **사용자 가치**: 출근 전(오전 8시)에 그날 알아야 할 주식 시장 핵심 내용을 한 페이지로 확인
- **운영 비용**: GitHub Actions + GitHub Pages 무료 한도 내에서 운영
- **언어**: 모든 사용자 대면 콘텐츠는 한국어

## 기술 스택

| 영역 | 사용 기술 |
|------|----------|
| 데이터 수집 | Python (yfinance, pandas, requests 등) |
| 브리핑 생성 | Anthropic API (Claude) |
| 정적 페이지 | HTML / CSS (다크 모드 친화) |
| 자동 실행 | GitHub Actions (cron 스케줄) |
| 배포 | GitHub Pages |
| 시간대 | Asia/Seoul (KST) — cron은 UTC 기준이므로 변환 주의 |

## 코딩 규칙

### 주석 / 문자열
- **모든 주석은 한국어로 작성**한다. (코드 식별자는 영어)
- 사용자에게 보이는 텍스트(HTML, 로그 메시지 등)는 한국어를 우선한다.
- 주석은 "왜(why)" 위주로 적는다. 코드만 읽어도 알 수 있는 "무엇(what)"은 적지 않는다.

### 비밀 정보 / 환경 변수
- **API 키, 토큰 등은 절대 코드에 하드코딩하지 않는다.** 환경 변수로만 주입한다.
  - 로컬 개발: `.env` 파일 (반드시 `.gitignore`에 포함)
  - GitHub Actions: Repository Secrets 사용
- 환경 변수 이름 규칙: `ANTHROPIC_API_KEY`, `STOCK_API_KEY` 등 대문자 + 언더스코어
- `.env.example` 파일로 필요한 환경 변수 목록만 공유한다.

### Python 코드
- Python 3.11+ 기준
- 의존성은 `requirements.txt`로 관리
- 함수/변수명은 snake_case, 클래스명은 PascalCase
- 외부 API 호출은 실패할 수 있으므로 명확한 예외 처리와 재시도를 둔다 (단, 내부 함수에는 불필요한 방어 코드를 넣지 않는다)

### 파일 구조 (예정)
```
stock-briefing/
├── .github/workflows/   # GitHub Actions 워크플로우
├── scripts/             # 데이터 수집 / 페이지 생성 Python 스크립트
├── templates/           # HTML 템플릿
├── docs/                # GitHub Pages 배포 대상 (생성된 HTML)
├── index.html           # 임시 랜딩 페이지 (자동 생성 전까지)
├── requirements.txt
├── .env.example
└── README.md
```

### Git / 커밋
- 커밋 메시지는 한국어로 간결하게. 예: `랜딩 페이지 추가`, `데이터 수집 스크립트 작성`
- 자동 생성된 HTML은 별도 브랜치 또는 `docs/` 폴더로 분리해 메인 히스토리를 더럽히지 않는다 (추후 결정)

## 로드맵 (단계별)

1. **1단계 (오늘)**: 정적 랜딩 페이지 + GitHub Pages 배포
2. **2단계**: 주식 데이터 수집 스크립트 (yfinance 등)
3. **3단계**: Anthropic API로 브리핑 텍스트 생성
4. **4단계**: HTML 템플릿에 브리핑 주입 → 페이지 생성
5. **5단계**: GitHub Actions cron으로 매일 오전 8시(KST) 자동 실행
6. **6단계**: 디자인 개선, 과거 브리핑 아카이브, 종목 커스터마이즈 등

## 작업 시 주의사항

- 사용자에게 실행 명령(예: `git push`)을 알려줄 때는 Windows + bash 환경 기준으로 안내한다.
- GitHub Pages는 기본적으로 `main` 브랜치의 루트 또는 `/docs` 폴더에서 서빙된다. 어느 쪽을 쓸지 명시한다.
- cron은 UTC라 한국 오전 8시는 UTC 23:00 (전날). 시간 변환을 항상 명시한다.
