"""브리핑 HTML 페이지 렌더러 — 마크다운 + 시세 → 단일 index.html.

흐름:
    1) data/briefing_*.md 중 가장 최근 파일 자동 선택
    2) 같은 날짜의 data/market_*.json 짝 찾기
    3) 마크다운 → HTML 변환 + 시세 표/카드 생성
    4) 루트의 index.html 덮어쓰기

실행:
    python briefing/html_renderer.py
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from string import Template

import markdown as md_lib

# 상위 폴더의 config.py 를 import 가능하게 함
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import MODEL_BRIEFING  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"
INDEX_HTML = PROJECT_ROOT / "index.html"

# 한글 요일 — datetime.weekday() 0=월요일
KOREAN_WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


# ---------------------------------------------------------------------------
# 입력 파일 찾기
# ---------------------------------------------------------------------------


def find_latest_briefing() -> Path:
    """data/briefing_*.md 중 파일명 정렬상 가장 최근 파일."""
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"데이터 폴더가 없습니다: {DATA_DIR}")

    files = sorted(DATA_DIR.glob("briefing_*.md"))
    if not files:
        raise FileNotFoundError(
            "생성된 브리핑이 없습니다.\n"
            "먼저 'python briefing/generator.py' 를 실행해 주세요."
        )
    return files[-1]


def find_matching_market(briefing_path: Path) -> Path:
    """브리핑 파일과 같은 날짜의 market_*.json 짝을 반환.

    briefing_20260429.md → market_20260429.json
    """
    # "briefing" 접두어 뒤 부분 추출 — "20260429"
    date_tag = briefing_path.stem.split("_", 1)[1]
    market_path = DATA_DIR / f"market_{date_tag}.json"
    if not market_path.exists():
        raise FileNotFoundError(
            f"같은 날짜의 시세 데이터가 없습니다: {market_path.name}\n"
            f"'python collectors/korean_market.py' 를 다시 실행하거나 짝이 맞는 파일이 있는지 확인하세요."
        )
    return market_path


# ---------------------------------------------------------------------------
# 포매팅 헬퍼
# ---------------------------------------------------------------------------


def format_korean_date(iso_date: str) -> str:
    """`2026-04-29` → `2026년 4월 29일 수요일`."""
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    weekday = KOREAN_WEEKDAYS[dt.weekday()]
    return f"{dt.year}년 {dt.month}월 {dt.day}일 {weekday}"


def format_collected_at(iso: str) -> str:
    """ISO 8601 타임스탬프 → `2026-04-29 11:43:34 KST` 형식.

    파싱 실패 시 원본을 그대로 돌려준다 (사용자 입력 안전망).
    """
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M:%S") + " KST"
    except (ValueError, TypeError):
        return iso or "알 수 없음"


def change_class(pct: float | None) -> str:
    """등락률 부호에 따른 CSS 클래스 — 한국 관행 (양수=빨강 up, 음수=파랑 down)."""
    if pct is None:
        return "flat"
    if pct > 0:
        return "up"
    if pct < 0:
        return "down"
    return "flat"


def change_text(pct: float | None) -> str:
    """`+1.24%` / `-0.79%` / `—` 형식."""
    if pct is None:
        return "—"
    sign = "+" if pct > 0 else ""  # 음수는 자체적으로 '-'
    return f"{sign}{pct:.2f}%"


# ---------------------------------------------------------------------------
# 부분 HTML 렌더링
# ---------------------------------------------------------------------------


def render_index_card(idx: dict) -> str:
    """지수 카드 한 개 (KOSPI / KOSDAQ)."""
    name = html.escape(idx.get("name", ""))
    close = idx.get("close")
    pct = idx.get("change_pct")
    cls = change_class(pct)

    close_str = f"{close:,.2f}" if close is not None else "—"
    pct_str = change_text(pct)

    return (
        f'<div class="index-card">'
        f'<div class="index-name">{name}</div>'
        f'<div class="index-value">{close_str}</div>'
        f'<div class="index-change {cls}">{pct_str}</div>'
        f'</div>'
    )


def render_stock_row(s: dict) -> str:
    """종목 표 행 한 개. error 키가 있으면 별도 처리."""
    name = html.escape(s.get("name", ""))

    if s.get("error"):
        err = html.escape(str(s.get("error", "데이터 없음")))
        return (
            f'<tr class="row-error">'
            f'<td class="td-name">{name}</td>'
            f'<td colspan="4" class="td-error">— {err}</td>'
            f'</tr>'
        )

    close = s.get("close")
    pct = s.get("change_pct")
    volume = s.get("volume")
    ratio = s.get("volume_ratio")
    cls = change_class(pct)

    close_str = f"{close:,}원" if close is not None else "—"
    pct_str = change_text(pct)
    volume_str = f"{volume:,}" if volume is not None else "—"
    ratio_str = f"{ratio:.2f}x" if ratio is not None else "—"

    return (
        f'<tr>'
        f'<td class="td-name">{name}</td>'
        f'<td class="td-num">{close_str}</td>'
        f'<td class="td-num {cls}">{pct_str}</td>'
        f'<td class="td-num">{volume_str}</td>'
        f'<td class="td-num">{ratio_str}</td>'
        f'</tr>'
    )


def strip_top_h1(md_text: str) -> str:
    """첫 번째 H1 라인 제거 — 페이지 헤더와 중복되지 않게.

    H1 이 없으면 원본 그대로 반환.
    """
    lines = md_text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue  # 선행 빈 줄 건너뛰기
        if stripped.startswith("# "):
            return "\n".join(lines[:i] + lines[i + 1:]).lstrip()
        return md_text  # 첫 비어있지 않은 줄이 H1 아님 → 원본 유지
    return md_text


# ---------------------------------------------------------------------------
# 전체 HTML 조립
# ---------------------------------------------------------------------------


def render_html(briefing_md: str, market: dict) -> str:
    """모든 부분을 합쳐 완성된 단일 HTML 문서를 반환."""
    briefing_md_clean = strip_top_h1(briefing_md)
    briefing_html = md_lib.markdown(briefing_md_clean, extensions=[])

    date_kr = format_korean_date(market["data_date"])
    indices_html = "\n      ".join(
        render_index_card(idx) for idx in market.get("indices", [])
    )
    stocks_html = "\n          ".join(
        render_stock_row(s) for s in market.get("stocks", [])
    )
    collected_at = format_collected_at(market.get("collected_at", ""))

    return TEMPLATE.substitute(
        date_kr=html.escape(date_kr),
        indices_html=indices_html,
        stocks_html=stocks_html,
        briefing_html=briefing_html,
        collected_at=html.escape(collected_at),
        model=html.escape(MODEL_BRIEFING),
    )


# 단일 자체완결 HTML 템플릿 (string.Template — `$placeholder` 문법 사용해 CSS `{}` 와 충돌 없음)
TEMPLATE = Template("""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="매일 오전 8시 자동 생성되는 한국어 주식 브리핑" />
  <meta name="color-scheme" content="dark light" />
  <title>오전 8시 브리핑 — $date_kr</title>
  <style>
    /* 색상 토큰 — 다크 모드 우선, 라이트 모드는 prefers-color-scheme 로 자동 전환 */
    :root {
      --bg: #0b0f17;
      --bg-elev: #131927;
      --bg-elev-2: #1a2030;
      --border: #1f2a3d;
      --border-soft: #161e2c;
      --text: #e6edf7;
      --text-muted: #8b97ad;
      --text-subtle: #6b7588;
      --accent: #5b9dff;
      --accent-soft: rgba(91, 157, 255, 0.12);

      /* 한국 주식 관행 — 양수는 빨강, 음수는 파랑 */
      --up: #ff6b6b;
      --down: #5b9dff;
      --flat: #8b97ad;

      --shadow: 0 20px 60px rgba(0, 0, 0, 0.45);
    }

    @media (prefers-color-scheme: light) {
      :root {
        --bg: #f6f8fc;
        --bg-elev: #ffffff;
        --bg-elev-2: #f0f4f9;
        --border: #e3e8f0;
        --border-soft: #eef1f5;
        --text: #1a2233;
        --text-muted: #5a6478;
        --text-subtle: #7c8595;
        --accent: #2563eb;
        --accent-soft: rgba(37, 99, 235, 0.1);
        --up: #dc2626;
        --down: #2563eb;
        --flat: #5a6478;
        --shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
      }
    }

    * { box-sizing: border-box; }

    html, body {
      margin: 0;
      padding: 0;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                   "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic",
                   Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      font-size: 16px;
      min-height: 100vh;
      /* 은은한 배경 그라디언트 — 기존 랜딩 페이지 분위기 계승 */
      background-image:
        radial-gradient(circle at 15% 20%, var(--accent-soft), transparent 45%),
        radial-gradient(circle at 85% 80%, var(--accent-soft), transparent 40%);
      background-attachment: fixed;
    }

    main {
      max-width: 720px;
      margin: 0 auto;
      padding: 2rem 1.25rem 4rem;
    }

    /* ===== Header ===== */
    .page-header {
      margin-bottom: 1.75rem;
    }

    .page-header h1 {
      font-size: 1.75rem;
      font-weight: 700;
      margin: 0 0 0.4rem;
      letter-spacing: -0.01em;
    }

    .page-header .date {
      margin: 0;
      color: var(--text-muted);
      font-size: 1rem;
    }

    /* ===== 시장 지수 카드 ===== */
    .indices {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }

    .index-card {
      background: var(--bg-elev);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.25rem;
    }

    .index-name {
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 0.4rem;
      font-weight: 500;
    }

    .index-value {
      font-size: 1.5rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      margin-bottom: 0.25rem;
      letter-spacing: -0.01em;
    }

    .index-change {
      font-size: 0.95rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }

    /* ===== 종목 표 ===== */
    .stocks, .briefing {
      background: var(--bg-elev);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.25rem;
      margin-bottom: 1.5rem;
    }

    .briefing { padding: 1.5rem; }

    .section-title {
      font-size: 1rem;
      font-weight: 600;
      margin: 0 0 0.85rem;
      color: var(--text);
    }

    .table-wrap {
      overflow-x: auto;
      margin: 0 -0.25rem;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-variant-numeric: tabular-nums;
      font-size: 0.95rem;
    }

    th {
      text-align: left;
      font-size: 0.78rem;
      color: var(--text-muted);
      padding: 0.5rem 0.6rem 0.65rem;
      border-bottom: 1px solid var(--border);
      font-weight: 500;
      white-space: nowrap;
    }

    th.th-num, td.td-num { text-align: right; }
    th.th-name, td.td-name { text-align: left; }

    td {
      padding: 0.7rem 0.6rem;
      border-bottom: 1px solid var(--border-soft);
      white-space: nowrap;
    }

    tbody tr:last-child td {
      border-bottom: none;
    }

    .td-name { font-weight: 500; }

    .td-error {
      color: var(--text-subtle);
      font-style: italic;
    }

    /* ===== 등락률 색상 (한국 관행) ===== */
    .up { color: var(--up); }
    .down { color: var(--down); }
    .flat { color: var(--flat); }

    /* ===== 브리핑 본문 ===== */
    .briefing h1 {
      /* strip_top_h1 으로 제거되었어야 하지만 안전장치 */
      display: none;
    }

    .briefing h2 {
      font-size: 0.95rem;
      margin: 1.5rem 0 0.6rem;
      color: var(--accent);
      font-weight: 600;
      letter-spacing: -0.01em;
    }

    .briefing h2:first-child {
      margin-top: 0;
    }

    .briefing p {
      margin: 0 0 0.85rem;
      line-height: 1.7;
    }

    .briefing p:last-child {
      margin-bottom: 0;
    }

    .briefing strong {
      color: var(--text);
      font-weight: 600;
    }

    .briefing ul {
      padding-left: 1.25rem;
      margin: 0.5rem 0 0.85rem;
    }

    .briefing li {
      margin-bottom: 0.55rem;
      line-height: 1.65;
    }

    .briefing li:last-child {
      margin-bottom: 0;
    }

    .briefing a {
      color: var(--accent);
      text-decoration: none;
    }

    .briefing a:hover {
      text-decoration: underline;
    }

    /* ===== 푸터 ===== */
    .page-footer {
      margin-top: 2.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border-soft);
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    .page-footer .meta {
      margin: 0 0 0.85rem;
    }

    .page-footer code {
      background: var(--bg-elev);
      padding: 0.1em 0.4em;
      border-radius: 4px;
      font-size: 0.85em;
      border: 1px solid var(--border-soft);
      font-family: "SF Mono", Menlo, Consolas, monospace;
    }

    .disclaimer {
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.85rem 1rem;
      margin: 0;
      font-size: 0.8rem;
      color: var(--text-subtle);
      line-height: 1.65;
    }

    @media (prefers-color-scheme: light) {
      .disclaimer {
        background: rgba(15, 23, 42, 0.02);
      }
    }

    /* ===== 모바일 ===== */
    @media (max-width: 480px) {
      main {
        padding: 1.5rem 1rem 3rem;
      }

      .page-header h1 {
        font-size: 1.5rem;
      }

      .indices {
        gap: 0.6rem;
      }

      .index-card {
        padding: 1rem;
      }

      .index-value {
        font-size: 1.3rem;
      }

      .stocks, .briefing {
        padding: 1rem;
      }

      .briefing { padding: 1.25rem; }

      table {
        font-size: 0.85rem;
      }

      th, td {
        padding: 0.55rem 0.4rem;
      }

      th {
        font-size: 0.72rem;
      }
    }
  </style>
</head>
<body>
  <main>
    <header class="page-header">
      <h1>📈 오전 8시 브리핑</h1>
      <p class="date">$date_kr</p>
    </header>

    <section class="indices" aria-label="시장 지수">
      $indices_html
    </section>

    <section class="stocks" aria-label="관심 종목">
      <h2 class="section-title">관심 종목</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="th-name">종목명</th>
              <th class="th-num">종가</th>
              <th class="th-num">등락률</th>
              <th class="th-num">거래량</th>
              <th class="th-num">거래량비율</th>
            </tr>
          </thead>
          <tbody>
          $stocks_html
          </tbody>
        </table>
      </div>
    </section>

    <section class="briefing" aria-label="시장 브리핑">
      $briefing_html
    </section>

    <footer class="page-footer">
      <p class="meta">
        데이터 수집: $collected_at<br />
        생성 모델: <code>$model</code>
      </p>
      <p class="disclaimer">
        ⚠ 본 브리핑은 투자 자문이 아닙니다. 모든 투자 결정과 그 결과에 대한 책임은 본인에게 있습니다.
        데이터는 FinanceDataReader / KRX 공개 정보 기준이며 오류나 누락 가능성이 있습니다.
      </p>
    </footer>
  </main>
</body>
</html>
""")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print(" HTML 페이지 렌더링")
    print("=" * 60)

    # 1. 입력 파일 찾기
    try:
        briefing_path = find_latest_briefing()
        market_path = find_matching_market(briefing_path)
    except FileNotFoundError as e:
        print(f"\n[오류] {e}")
        sys.exit(1)

    print(
        f"\n[입력] {briefing_path.relative_to(PROJECT_ROOT)} "
        f"({briefing_path.stat().st_size:,} bytes)"
    )
    print(
        f"[입력] {market_path.relative_to(PROJECT_ROOT)} "
        f"({market_path.stat().st_size:,} bytes)"
    )

    # 2. 데이터 로드
    briefing_md = briefing_path.read_text(encoding="utf-8")

    try:
        market = json.loads(market_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"\n[오류] JSON 파싱 실패: {e}")
        sys.exit(1)

    # 3. 렌더링
    try:
        html_text = render_html(briefing_md, market)
    except KeyError as e:
        print(f"\n[오류] 시세 데이터 필수 키 누락: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[오류] 렌더링 실패: {e}")
        sys.exit(2)

    # 4. 저장 (덮어쓰기)
    INDEX_HTML.write_text(html_text, encoding="utf-8")
    print(f"\n[저장] index.html ({INDEX_HTML.stat().st_size:,} bytes)")

    print()
    print("=" * 60)
    print(f" 브라우저에서 확인:")
    print(f"   {INDEX_HTML}")
    print("=" * 60)


if __name__ == "__main__":
    main()
