"""한국 시장 데이터 수집기 — 관심 종목 + 코스피/코스닥 지수.

config.WATCHLIST 와 config.MARKET_INDICES 를 읽어 FinanceDataReader 로 시세를 가져온 뒤
- data/market_YYYYMMDD.json 에 구조화된 형태로 저장 (Claude API 입력용)
- 콘솔에 표 형태로 출력 (사람용)
한다.

실행:
    python collectors/korean_market.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd
from tabulate import tabulate

# `python collectors/korean_market.py` 처럼 직접 실행할 때 상위 폴더의 config.py 를 import 가능하게 함
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import MARKET_INDICES, WATCHLIST  # noqa: E402  (sys.path 조작 후 import)

# 한국 표준시 — collected_at 타임스탬프용 (고정 오프셋 +09:00)
KST = timezone(timedelta(hours=9))

# 데이터 조회 시 거슬러 올라가는 일수 — 주말/연휴 + 전일 거래량 비교용으로 넉넉히
LOOKBACK_DAYS = 14

# JSON 저장 위치 — 프로젝트 루트 기준
DATA_DIR = PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# 데이터 수집
# ---------------------------------------------------------------------------


def _fetch_recent(code: str) -> pd.DataFrame:
    """FinanceDataReader 로 최근 LOOKBACK_DAYS 일치 시세 DataFrame 을 받아온다."""
    today = datetime.now(KST).date()
    start = today - timedelta(days=LOOKBACK_DAYS)
    return fdr.DataReader(code, start=start.isoformat(), end=today.isoformat())


def fetch_stock(code: str, name: str) -> dict:
    """단일 종목의 최근 거래일 시세를 수집해 dict 로 반환.

    실패 시 (빈 데이터, 알 수 없는 코드 등) 모든 수치 필드를 None 으로 채우고 'error' 키를 단다.
    네트워크 자체가 죽은 경우는 호출자가 처리하도록 예외를 흘려보낸다.
    """
    try:
        df = _fetch_recent(code)
    except (ConnectionError, TimeoutError, OSError):
        # 네트워크 오류는 모든 종목에 영향 — 상위로 그대로 전파
        raise

    if df is None or df.empty:
        return {
            "code": code,
            "name": name,
            "close": None,
            "change_pct": None,
            "volume": None,
            "volume_ratio": None,
            "error": "데이터를 찾을 수 없음",
        }

    last = df.iloc[-1]

    # 전일 대비 거래량 비율 — 직전 거래일 행이 있을 때만 계산
    if len(df) >= 2:
        prev_volume = float(df.iloc[-2]["Volume"])
        volume_ratio = (
            round(float(last["Volume"]) / prev_volume, 2) if prev_volume > 0 else None
        )
    else:
        volume_ratio = None

    return {
        "code": code,
        "name": name,
        "close": int(last["Close"]),                     # 종가 (원)
        "change_pct": round(float(last["Change"]) * 100, 2),  # 등락률 (%, 소수 둘째 자리)
        "volume": int(last["Volume"]),                   # 거래량 (주)
        "volume_ratio": volume_ratio,                    # 전일 대비 거래량 배수 (1.23 = +23%)
    }


def fetch_index(code: str, name: str) -> dict:
    """단일 지수의 최근 거래일 종가/등락률 수집."""
    df = _fetch_recent(code)

    if df is None or df.empty:
        return {
            "code": code,
            "name": name,
            "close": None,
            "change_pct": None,
            "error": "데이터를 찾을 수 없음",
        }

    last = df.iloc[-1]
    return {
        "code": code,
        "name": name,
        "close": round(float(last["Close"]), 2),
        "change_pct": round(float(last["Change"]) * 100, 2),
    }


def collect_market_data() -> dict:
    """전체 시장 데이터를 수집해 JSON 직렬화 가능한 dict 로 반환."""
    indices = [fetch_index(code, name) for code, name in MARKET_INDICES]
    stocks = [fetch_stock(code, name) for code, name in WATCHLIST]

    # data_date 결정 — 첫 번째로 성공한 데이터 행의 날짜를 기준으로 잡는다
    data_date = _resolve_data_date(indices, stocks)

    return {
        "data_date": data_date.isoformat() if data_date else None,
        "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
        "indices": indices,
        "stocks": stocks,
    }


def _resolve_data_date(indices: list[dict], stocks: list[dict]) -> "datetime.date | None":
    """수집 결과 중 가장 최근 거래일을 다시 한 번 KRX 에 물어 확정한다.

    개별 fetch 함수는 row 만 dict 로 추려 반환하므로 인덱스(날짜)를 잃는다.
    가장 안정적인 KOSPI(KS11) 데이터의 마지막 인덱스를 기준일로 쓴다.
    실패하면 None.
    """
    try:
        df = _fetch_recent("KS11")
        if df is not None and not df.empty:
            return df.index[-1].date()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 출력 / 저장
# ---------------------------------------------------------------------------


def _format_pct(pct: float | None) -> str:
    """등락률을 부호 포함 '%' 문자열로 변환. None 이면 '—'."""
    if pct is None:
        return "—"
    sign = "+" if pct >= 0 else ""  # 음수는 자체적으로 '-' 가 붙음
    return f"{sign}{pct:.2f}%"


def print_table(data: dict) -> None:
    """콘솔에 시장 지수 + 종목 시세를 표 형태로 출력."""
    print()
    print("=" * 60)
    print(f" 한국 시장 데이터 (기준일: {data['data_date'] or '알 수 없음'})")
    print("=" * 60)

    # ---- 시장 지수 ----
    idx_rows = [
        [
            idx["name"],
            f"{idx['close']:,.2f}" if idx.get("close") is not None else "—",
            _format_pct(idx.get("change_pct")),
        ]
        for idx in data["indices"]
    ]
    print("\n[시장 지수]")
    print(
        tabulate(
            idx_rows,
            headers=["지수", "종가", "등락률"],
            tablefmt="simple",
            colalign=("left", "right", "right"),
        )
    )

    # ---- 관심 종목 ----
    stock_rows = []
    for s in data["stocks"]:
        if s.get("error"):
            stock_rows.append([s["name"], "—", "—", "—", "—"])
            continue
        stock_rows.append(
            [
                s["name"],
                f"{s['close']:,}원",
                _format_pct(s["change_pct"]),
                f"{s['volume']:,}",
                f"{s['volume_ratio']:.2f}x" if s["volume_ratio"] is not None else "—",
            ]
        )
    print("\n[관심 종목]")
    print(
        tabulate(
            stock_rows,
            headers=["종목명", "종가", "등락률", "거래량", "거래량비율"],
            tablefmt="simple",
            colalign=("left", "right", "right", "right", "right"),
        )
    )


def save_json(data: dict) -> Path:
    """`data/market_YYYYMMDD.json` 형식으로 저장하고 그 경로를 반환한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 파일명에는 데이터 기준일을 사용 — 같은 거래일에 여러 번 실행되면 덮어쓰기
    if data["data_date"]:
        date_tag = data["data_date"].replace("-", "")
    else:
        # 기준일을 못 구한 경우 실행일 기준으로 떨어뜨림
        date_tag = datetime.now(KST).strftime("%Y%m%d")

    path = DATA_DIR / f"market_{date_tag}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def main() -> None:
    # Windows 기본 콘솔(cp949)에서 한글이 깨지는 것을 방지
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        data = collect_market_data()
    except (ConnectionError, TimeoutError, OSError) as e:
        # 네트워크 자체가 실패 — FDR 호출이 모두 영향 받으므로 즉시 종료
        print(f"[오류] 네트워크 연결 실패: {e}")
        print("       인터넷 연결을 확인하고 다시 시도해 주세요.")
        sys.exit(2)
    except Exception as e:
        # 데이터 소스 측 변경 등 — 디버깅 용이하게 메시지 그대로 노출
        print(f"[오류] 예상치 못한 오류가 발생했습니다: {e}")
        sys.exit(3)

    print_table(data)

    saved_path = save_json(data)
    size = saved_path.stat().st_size
    print(f"\n[저장] {saved_path.relative_to(PROJECT_ROOT)} ({size:,} bytes)")


if __name__ == "__main__":
    main()
