# 🚀 주식 브리핑 사이트

매일 오전 8시(KST), 출근 전에 확인할 수 있는 자동 생성 주식 브리핑 사이트입니다.

> 현재 **1단계(랜딩 페이지)** 진행 중입니다. 자동 브리핑 기능은 단계별로 추가될 예정입니다.

## 프로젝트 소개

이 프로젝트는 다음을 자동화하는 것을 목표로 합니다.

1. 매일 정해진 시각에 주식 시장 데이터 수집
2. Claude(Anthropic API)를 활용한 한국어 브리핑 생성
3. 깔끔한 HTML 페이지로 변환
4. GitHub Pages를 통한 무료 배포

매일 아침 한 페이지만 보면 그날 시장의 핵심을 파악할 수 있도록 만드는 것이 목표입니다.

## 기술 스택

- **언어**: Python 3.11+
- **데이터 수집**: yfinance 등 (예정)
- **브리핑 생성**: Anthropic API (Claude)
- **자동 실행**: GitHub Actions (cron)
- **배포**: GitHub Pages
- **프론트엔드**: 정적 HTML / CSS (다크 모드 친화)

## 로드맵

| 단계 | 내용 | 상태 |
|------|------|------|
| 1 | 정적 랜딩 페이지 + GitHub Pages 배포 | 🔄 진행 중 |
| 2 | 주식 데이터 수집 스크립트 작성 | ⏳ 예정 |
| 3 | Anthropic API로 브리핑 텍스트 생성 | ⏳ 예정 |
| 4 | HTML 템플릿에 브리핑 주입 → 페이지 자동 생성 | ⏳ 예정 |
| 5 | GitHub Actions cron으로 매일 오전 8시(KST) 자동 실행 | ⏳ 예정 |
| 6 | 디자인 개선, 과거 브리핑 아카이브, 종목 커스터마이즈 | ⏳ 예정 |

## 로컬에서 보기

현재는 정적 HTML 파일 하나입니다. 브라우저로 `index.html`을 직접 열면 됩니다.

```bash
# Windows (Git Bash)
start index.html
```

## 설치 방법

이 저장소를 처음 클론한 경우, 다음 순서대로 환경을 준비하세요.

### 사전 요구 사항
- Python 3.11 이상
- Anthropic API 키 ([console.anthropic.com](https://console.anthropic.com/) 에서 발급)

### 1. 저장소 클론

```bash
git clone https://github.com/Minnieping/stock-briefing.git
cd stock-briefing
```

### 2. 가상환경 생성 (선택, 권장)

가상환경을 사용하면 시스템 Python 과 의존성이 충돌하지 않습니다.

```bash
# 가상환경 생성
python -m venv .venv

# 활성화
source .venv/Scripts/activate    # Windows (Git Bash)
# .venv\Scripts\activate         # Windows (cmd / PowerShell)
# source .venv/bin/activate      # macOS / Linux
```

활성화에 성공하면 프롬프트 앞에 `(.venv)` 가 붙습니다.

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`.env.example` 을 복사해 `.env` 를 만들고 API 키를 채워 넣습니다.

```bash
cp .env.example .env
```

생성된 `.env` 파일을 열어 다음 줄을 수정하세요:

```
ANTHROPIC_API_KEY=sk-ant-api03-...실제_키_값...
```

> ⚠️ `.env` 는 `.gitignore` 에 포함되어 있어 절대 GitHub 에 올라가지 않습니다.
> API 키를 직접 코드나 커밋 메시지에 적지 마세요.

### 5. API 연결 테스트

설치가 끝났는지 확인하기 위해 간단한 테스트 스크립트를 실행합니다.

```bash
python test_api.py
```

성공하면 Claude 가 한국어로 자기소개를 출력합니다. 인증/네트워크 문제가 있으면 한국어로 원인을 알려줍니다.

## 환경 변수

추후 단계에서 다음 환경 변수가 필요해집니다. 실제 키는 `.env` 파일이나 GitHub Secrets로만 관리하며, 절대 저장소에 커밋하지 않습니다.

| 이름 | 용도 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API 호출용 |

## 라이선스

개인 프로젝트 — 별도 라이선스를 명시하기 전까지는 모든 권리는 작성자에게 있습니다.
