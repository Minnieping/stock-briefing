"""삼성전자(005930) 최근 거래일 시세 가져오기 — 첫 데이터 수집 테스트.

FinanceDataReader 가 KRX 데이터를 정상적으로 가져오는지,
그리고 우리가 원하는 형태(종가/등락률/거래량)로 추출 가능한지 확인하는 용도.

실행:
    python collectors/test_stock.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

import FinanceDataReader as fdr
import pandas as pd

# 테스트 대상 — 추후 종목 리스트로 확장 예정
STOCK_CODE = "005930"
STOCK_NAME = "삼성전자"


def fetch_latest_quote(code: str) -> pd.Series:
    """주어진 종목 코드의 가장 최근 거래일 시세를 한 행(Series) 으로 반환한다.

    주말/공휴일 대비해 최근 14일치 범위로 요청한 뒤 마지막 행만 사용한다.
    데이터가 비어 있으면 (= 잘못된 종목 코드 가능성) ValueError 를 발생시킨다.
    """
    today = datetime.now().date()
    start = today - timedelta(days=14)

    # FDR.DataReader 는 내부적으로 KRX 등에 HTTP 요청을 보낸다.
    # 네트워크 오류는 호출자가 처리하도록 그대로 흘려 보낸다.
    df = fdr.DataReader(code, start=start.isoformat(), end=today.isoformat())

    if df is None or df.empty:
        raise ValueError(f"종목 코드 '{code}' 에 해당하는 데이터를 찾을 수 없습니다.")

    return df.iloc[-1]  # 가장 최근 거래일 한 행


def format_quote(name: str, code: str, row: pd.Series) -> str:
    """시세 한 행을 사람이 읽기 좋은 다중 라인 문자열로 정리한다."""
    close = int(row["Close"])           # 종가 (정수원)
    volume = int(row["Volume"])         # 거래량 (정수)
    # FDR 의 'Change' 는 소수 형태 등락률 (0.0124 = +1.24%)
    change_pct = float(row["Change"]) * 100
    sign = "+" if change_pct >= 0 else ""  # 음수는 자체적으로 '-' 가 붙음

    return (
        f"종목: {name} ({code})\n"
        f"전일 종가: {close:,}원\n"
        f"등락률: {sign}{change_pct:.2f}%\n"
        f"거래량: {volume:,}"
    )


def main() -> None:
    # Windows 기본 콘솔(cp949)에서 한글이 깨지는 것을 방지 — stdout 을 UTF-8 로 강제
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        row = fetch_latest_quote(STOCK_CODE)
    except ValueError as e:
        # 빈 데이터 등 입력 단계 오류
        print(f"[오류] {e}")
        sys.exit(1)
    except (ConnectionError, TimeoutError, OSError) as e:
        # 네트워크 자체가 실패한 경우 — requests/urllib 계열도 OSError 하위
        print(f"[오류] 네트워크 연결 실패: {e}")
        print("       인터넷 연결을 확인하고 다시 시도해 주세요.")
        sys.exit(2)
    except Exception as e:
        # 그 외 (예: KRX 사이트 구조 변경 등) — 일단 메시지만 노출하고 종료
        print(f"[오류] 예상치 못한 오류가 발생했습니다: {e}")
        sys.exit(3)

    print(format_quote(STOCK_NAME, STOCK_CODE, row))


if __name__ == "__main__":
    main()
