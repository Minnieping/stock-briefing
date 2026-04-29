"""시장 브리핑 생성기 — 수집된 JSON 데이터를 Claude 에 넘겨 한국어 브리핑 작성.

흐름:
    1) data/market_*.json 중 가장 최근 파일 자동 선택
    2) Claude API (Sonnet 4.6) 에 데이터 전달, 한국어 브리핑 요청
    3) 결과를 data/briefing_YYYYMMDD.md 로 저장
    4) 콘솔에 미리보기 + 토큰 사용량 출력

실행:
    python briefing/generator.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# `python briefing/generator.py` 실행 시 상위 폴더의 config.py 를 import 가능하게 함
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import MODEL_BRIEFING  # noqa: E402  (sys.path 조작 후 import)

DATA_DIR = PROJECT_ROOT / "data"

# Claude 의 응답 길이는 시스템 프롬프트의 "800자 이내" 제약을 따르게 하지만,
# 마크다운 헤더 / 토큰 변환 오버헤드를 감안해 max_tokens 는 여유 있게 잡는다
MAX_OUTPUT_TOKENS = 2000


# 시스템 프롬프트 — 톤 / 형식 / 금지사항 명시
SYSTEM_PROMPT = """\
당신은 한국 주식 시장 데이터를 분석해 매일 아침 8시에 발행되는 간결한 시장 브리핑을 작성하는 전문가입니다.

[작성 규칙]
- 한국어 신문 시황 기사 톤으로 자연스럽게
- **본문은 반드시 800자(마크다운 헤더 제외, 공백 포함) 이내로 작성. 800자를 넘기지 말 것.**
- **종목별 코멘트는 1~2문장으로 압축**
- 단순한 숫자 나열은 피하고, "왜 그런지" / "무엇이 의미 있는지" 해석을 더할 것
- "~으로 보입니다", "~로 해석됩니다", "~할 가능성이 있습니다" 같은 신중한 표현 사용
- 단정적인 매수/매도/투자 추천은 절대 하지 말 것
- 거래량비율(volume_ratio)이 1.5 이상이거나 0.5 이하면 특이 신호로 언급해도 좋음

[거래량 해석 주의사항 — 매우 중요]
- data_date 가 오늘 날짜이면서 모든 종목의 volume_ratio 가 1.0 미만이면, 장중 누적 데이터일 가능성이 높음.
- 이 경우 "거래량이 적다" / "관망 장세" / "거래가 위축" 같은 단정적 표현은 사용하지 말 것.
- 대신 "장중 누적 시점이라 전일 마감과 직접 비교 어려움" / "장 마감 후 데이터로 재확인 필요" 같은 안전한 표현 사용.
- 거래량비율을 굳이 본문에서 언급할 필요 없으면 생략해도 좋음.

[형식 — 마크다운, 다음 순서를 그대로 따를 것]

# 시장 브리핑 (YYYY-MM-DD)

## 시장 한 줄 요약
(전체 분위기를 한 문장으로)

## 지수 동향
(KOSPI, KOSDAQ — 종가와 등락률 + 짧은 해석. 합쳐서 2~3문장 이내)

## 주요 종목 코멘트
(제공된 종목 각각: 종가/등락률 + 짧은 해석. 종목당 1~2문장으로 엄격히 제한)

## 주목할 점
(선택 항목. 정말 의미 있는 패턴이 있을 때만 한 줄로. 특이 사항 없으면 섹션 자체 생략)

[입력 데이터 형식]
JSON. data_date 는 거래 기준일, indices 는 시장 지수 배열, stocks 는 종목 배열.
change_pct 는 % 단위, volume_ratio 는 전일 거래량 대비 배수(1.5 = +50%, 0.5 = 절반).
error 키가 있는 종목은 데이터 수집에 실패한 경우 — 코멘트 시 해당 종목은 "데이터 없음"으로 짧게 처리.
"""


def count_body_chars(text: str) -> int:
    """마크다운 헤더(`#` 으로 시작하는 라인)를 제외한 본문 글자 수.

    공백 / 줄바꿈 모두 포함. 시스템 프롬프트의 "800자 한도" 와 동일한 기준으로 측정.
    """
    body = "\n".join(
        line for line in text.split("\n") if not line.lstrip().startswith("#")
    ).strip()
    return len(body)


# ---------------------------------------------------------------------------
# 데이터 입력
# ---------------------------------------------------------------------------


def find_latest_market_file() -> Path:
    """data/market_*.json 중 파일명 정렬 기준 가장 최근 파일 반환.

    파일명이 market_YYYYMMDD.json 형식이라 사전순 정렬 = 시간순 정렬.
    """
    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"데이터 폴더가 없습니다: {DATA_DIR}\n"
            f"먼저 'python collectors/korean_market.py' 를 실행해 데이터를 수집하세요."
        )

    files = sorted(DATA_DIR.glob("market_*.json"))
    if not files:
        raise FileNotFoundError(
            "수집된 시장 데이터가 없습니다.\n"
            "먼저 'python collectors/korean_market.py' 를 실행해 데이터를 수집하세요."
        )
    return files[-1]


def load_market_data(path: Path) -> dict:
    """JSON 파일을 dict 로 읽고 필수 키 존재 여부를 검증한다."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)  # 형식 오류 시 JSONDecodeError 가 호출자로 흘러간다

    required = ("data_date", "indices", "stocks")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"입력 JSON 에 필수 키 누락: {missing}")

    return data


# ---------------------------------------------------------------------------
# Claude 호출
# ---------------------------------------------------------------------------


def generate_briefing(client: anthropic.Anthropic, data: dict):
    """Claude 에 데이터를 넘기고 (브리핑 텍스트, usage) 튜플을 반환한다."""
    # JSON 을 코드 블록으로 감싸 user 메시지에 넣어 모델이 구조를 명확히 파악하게 함
    user_message = (
        "다음은 오늘 작성할 한국 시장 데이터입니다. "
        "시스템 프롬프트의 형식과 규칙을 그대로 따라 시장 브리핑을 작성해 주세요.\n\n"
        f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"
    )

    response = client.messages.create(
        model=MODEL_BRIEFING,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # response.content 는 블록 리스트 — text 타입만 골라 합친다
    text = "\n".join(b.text for b in response.content if b.type == "text").strip()
    return text, response.usage


# ---------------------------------------------------------------------------
# 출력 / 저장
# ---------------------------------------------------------------------------


def save_briefing(text: str, data_date: str | None) -> Path:
    """data/briefing_YYYYMMDD.md 형태로 저장 후 경로 반환."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if data_date:
        date_tag = data_date.replace("-", "")
    else:
        # 입력에 data_date 가 없으면 실행일을 사용 — 정보 손실 최소화
        date_tag = datetime.now().strftime("%Y%m%d")

    path = DATA_DIR / f"briefing_{date_tag}.md"
    # 마지막 줄바꿈 보장 — 일부 도구(POSIX) 가 EOF 직전 개행 없으면 경고
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def _check_api_key() -> str:
    """.env 로드 후 API 키 존재 여부 검증, 없으면 종료."""
    load_dotenv(override=True)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("[오류] ANTHROPIC_API_KEY 가 설정되어 있지 않습니다.")
        print("       .env 파일을 열어 ANTHROPIC_API_KEY=... 형태로 키를 채워 주세요.")
        sys.exit(1)
    return api_key


def main() -> None:
    # Windows 기본 콘솔(cp949)에서 한글 깨지는 것을 방지
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    api_key = _check_api_key()

    print("=" * 60)
    print(" 시장 브리핑 생성")
    print("=" * 60)

    # 1. 가장 최근 시장 데이터 파일 찾기
    try:
        market_file = find_latest_market_file()
    except FileNotFoundError as e:
        print(f"[오류] {e}")
        sys.exit(1)

    # 2. JSON 로드 / 검증
    try:
        data = load_market_data(market_file)
    except json.JSONDecodeError as e:
        print(f"[오류] JSON 파싱 실패: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"[오류] 데이터 형식 오류: {e}")
        sys.exit(1)

    print(f"\n[입력]   {market_file.relative_to(PROJECT_ROOT)} ({market_file.stat().st_size:,} bytes)")
    print(f"[모델]   {MODEL_BRIEFING}")
    print(f"[데이터 기준일] {data.get('data_date') or '알 수 없음'}")
    print(f"[수집 시각]   {data.get('collected_at', '알 수 없음')}")
    print()
    print("(Claude API 호출 중...)")

    # 3. Claude API 호출 (typed exception 으로 분기)
    client = anthropic.Anthropic(api_key=api_key)

    try:
        briefing, usage = generate_briefing(client, data)
    except anthropic.AuthenticationError:
        print("[오류] API 키 인증 실패 (401). 키가 만료/취소되었는지 확인하세요.")
        sys.exit(2)
    except anthropic.PermissionDeniedError:
        print(f"[오류] 권한 부족 (403). 현재 키로 '{MODEL_BRIEFING}' 모델에 접근할 수 없습니다.")
        sys.exit(2)
    except anthropic.RateLimitError:
        print("[오류] 요청 한도 초과 (429). 잠시 후 다시 시도해 주세요.")
        sys.exit(3)
    except anthropic.APIConnectionError as e:
        print(f"[오류] 네트워크 연결 실패: {e}")
        sys.exit(4)
    except anthropic.APIStatusError as e:
        print(f"[오류] API 응답 오류 (status {e.status_code}): {e.message}")
        sys.exit(5)

    # 4. 결과 저장
    saved_path = save_briefing(briefing, data.get("data_date"))

    print(f"\n[저장] {saved_path.relative_to(PROJECT_ROOT)} ({saved_path.stat().st_size:,} bytes)")

    # 5. 미리보기
    print()
    print("=" * 60)
    print(" 미리보기")
    print("=" * 60)
    print(briefing)
    print("=" * 60)

    # 6. 글자 수 — 800자 한도 검증
    body_chars = count_body_chars(briefing)
    over = body_chars > 800
    status = "⚠ 초과" if over else "✓ 한도 내"
    print(
        f"[글자수] 본문 {body_chars}자 (헤더 제외, 공백 포함) | 800자 한도: {status}"
    )

    # 7. 토큰 사용량 — 비용 가늠용 (Sonnet 4.6: $3/1M 입력, $15/1M 출력)
    in_cost = usage.input_tokens / 1_000_000 * 3.0
    out_cost = usage.output_tokens / 1_000_000 * 15.0
    total_cost = in_cost + out_cost
    print(
        f"[완료] 입력 {usage.input_tokens:,} 토큰 / 출력 {usage.output_tokens:,} 토큰 "
        f"| 추정 비용 ${total_cost:.5f} (입력 ${in_cost:.5f} + 출력 ${out_cost:.5f})"
    )


if __name__ == "__main__":
    main()
