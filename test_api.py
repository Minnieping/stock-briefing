"""Anthropic Claude API 연결 테스트 스크립트.

.env 파일의 ANTHROPIC_API_KEY 를 읽어 Claude 에 한국어로 인사를 건네고
응답을 출력한다. 본격적인 데이터 수집 / 브리핑 생성 전에 인증 / 네트워크 /
SDK 환경이 정상인지 가볍게 확인하는 용도.

실행:
    python test_api.py
"""

import os
import sys

import anthropic
from dotenv import load_dotenv

# 비용/속도 모두 가벼운 테스트 용도이므로 Sonnet 사용
MODEL = "claude-sonnet-4-6"
USER_PROMPT = "안녕! 너 누구야?"


def load_api_key() -> str:
    """.env 에서 API 키를 읽고, 비어 있거나 누락되면 즉시 종료한다."""
    # override=True: 셸 환경에 묵은 값이 있어도 .env 의 최신 값을 우선
    load_dotenv(override=True)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("[오류] ANTHROPIC_API_KEY 가 설정되어 있지 않습니다.")
        print("       .env 파일을 열어 ANTHROPIC_API_KEY=... 형태로 키를 채워 주세요.")
        sys.exit(1)

    # 형식 가벼운 검증 — Anthropic 키는 'sk-ant-' 로 시작
    if not api_key.startswith("sk-ant-"):
        print("[경고] API 키 형식이 예상과 다릅니다 (sk-ant- 로 시작해야 함).")
        print("       그대로 진행하지만 인증 오류가 날 수 있습니다.\n")

    return api_key


def ask_claude(api_key: str, prompt: str) -> str:
    """Claude 에 질문을 보내고 응답 텍스트만 합쳐서 반환한다."""
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    # content 는 블록 리스트 — text 타입만 골라 이어 붙임
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(parts).strip()


def main() -> None:
    api_key = load_api_key()

    print("=" * 50)
    print(f" Claude API 연결 테스트 (model: {MODEL})")
    print("=" * 50)
    print(f"\n[질문] {USER_PROMPT}\n")

    try:
        answer = ask_claude(api_key, USER_PROMPT)
    except anthropic.AuthenticationError:
        # 401: 키 자체가 거부됨
        print("[오류] API 키 인증 실패 (401).")
        print("       키가 만료/취소되었거나 오타가 없는지 확인하세요.")
        sys.exit(2)
    except anthropic.PermissionDeniedError:
        # 403: 키는 유효하지만 이 모델/리소스 사용 권한 없음
        print(f"[오류] 권한 부족 (403). 현재 키로 '{MODEL}' 모델에 접근할 수 없습니다.")
        sys.exit(2)
    except anthropic.NotFoundError:
        # 404: 잘못된 모델 ID 등
        print(f"[오류] 모델을 찾을 수 없습니다 (404): {MODEL}")
        sys.exit(2)
    except anthropic.RateLimitError:
        # 429: 분당/일당 한도 초과
        print("[오류] 요청 한도 초과 (429). 잠시 후 다시 시도해 주세요.")
        sys.exit(3)
    except anthropic.APIConnectionError as e:
        # 네트워크 자체가 실패 — 프록시/방화벽/오프라인 등
        print(f"[오류] 네트워크 연결 실패: {e}")
        sys.exit(4)
    except anthropic.APIStatusError as e:
        # 그 외 API 측 5xx / 알 수 없는 상태
        print(f"[오류] API 응답 오류 (status {e.status_code}): {e.message}")
        sys.exit(5)

    print("[응답]")
    print(answer)
    print("\n" + "=" * 50)
    print(" 테스트 성공 — Anthropic API 가 정상 동작합니다.")
    print("=" * 50)


if __name__ == "__main__":
    main()
