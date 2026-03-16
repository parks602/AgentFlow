"""
연속 시뮬레이션 — 날짜 범위를 지정해 매일 시뮬레이션 실행
전날 결과가 다음날 초기 시장 심리에 영향을 줌

사용법:
  python run_continuous.py --corp SK하이닉스 --ticker 000660 --start 2026-03-06 --end 2026-03-12
  python run_continuous.py --corp SK하이닉스 --ticker 000660 --days 7   # 오늘부터 7일 전
"""
import argparse
import json
import time
from datetime import datetime, timedelta

from llm.client import LLMClient
from agents.memory.agent_memory import AgentMemory
from agents.agent_factory import create_agents
from data.collector.dart_collector import DartCollector
from data.collector.news_collector import NewsCollector
from data.collector.price_collector import build_market_context_range
from data.seed_parser import SeedParser
from simulation.engine import SimulationEngine
from evaluation.validator import SimulationValidator


def build_carry_over_context(prev_result: dict | None) -> str:
    """전날 결과를 다음날 초기 시장 심리 텍스트로 변환"""
    if not prev_result:
        return ""

    r    = prev_result.get("result", {})
    seed = prev_result.get("seed", {})
    date = prev_result.get("issue_date", "")

    buy_p  = r.get("buy_pressure", 0)
    sell_p = r.get("sell_pressure", 0)
    pred   = r.get("prediction", "보합")

    sentiment_desc = (
        "매우 강한 매수 심리" if buy_p > 60
        else "강한 매수 심리" if buy_p > 40
        else "강한 매도 심리" if sell_p > 40
        else "관망 분위기"
    )

    return (
        f"[전일({date}) 시장 심리 이월]\n"
        f"  어제 예측: {pred} | 매수압력: {buy_p:.1f}% | 매도압력: {sell_p:.1f}%\n"
        f"  분위기: {sentiment_desc}\n"
        f"  어제 이슈: {seed.get('issue_type','기타')} — {seed.get('summary','')[:80]}"
    )


def run_one_day(
    corp_name: str,
    ticker: str,
    date: str,
    llm: LLMClient,
    memory: AgentMemory,
    agents: list,
    prev_result: dict | None = None,
    # 사전 수집 데이터 (범위 수집 시 전달, None이면 단일 날짜 수집)
    disc_range:  dict | None = None,
    news_range:  dict | None = None,
    price_range: dict | None = None,
) -> dict:
    print(f"\n{'='*60}")
    print(f"  [{date}] {corp_name} 시뮬레이션")
    print(f"{'='*60}")

    news_collector = NewsCollector()

    # 1. 데이터 로드 — 반드시 사전 수집 데이터 사용 (개별 API 호출 없음)
    print("[1/3] 데이터 준비...")
    disclosures   = disc_range.get(date, [])  if disc_range  is not None else []
    news_articles = news_range.get(date, [])  if news_range  is not None else []
    market_ctx    = price_range.get(date, {}) if price_range is not None else {}

    if not disclosures:
        print(f"  [Info] {date} 공시 없음")
    if not news_articles:
        print(f"  [Info] {date} 뉴스 없음 (-1~-7일 범위)")
    if not market_ctx:
        print(f"  [경고] {date} 주가 데이터 없음 — 스킵")
        return {"corp_name": corp_name, "ticker": ticker, "issue_date": date,
                "error": "주가 데이터 없음"}

    news_text = news_collector.format_for_seed(news_articles)

    # 2. 씨드 파싱 — 전날 이월 컨텍스트 포함
    print("[2/3] 씨드 파싱...")
    carry_over = build_carry_over_context(prev_result)
    parser = SeedParser(llm)
    seed   = parser.parse(corp_name, disclosures, news_text, market_ctx, raw_articles=news_articles)

    # 전날 심리를 seed의 key_points에 주입
    if carry_over:
        seed.setdefault("key_points", [])
        seed["key_points"].append(carry_over)
    seed["market_context"] = market_ctx

    print(f"  → {seed.get('summary','')[:80]}...")

    # 3. 시뮬레이션 (에이전트 메모리는 날짜 걸쳐 누적됨)
    print("[3/3] 시뮬레이션...")
    engine = SimulationEngine(agents)
    sim_result = engine.run(seed)

    # 4. 검증
    validator  = SimulationValidator()
    validation = validator.validate(sim_result, ticker, date, market_ctx)

    output = {
        "corp_name":  corp_name,
        "ticker":     ticker,
        "issue_date": date,
        "seed":       seed,
        "result":     sim_result["result"],
        "validation": validation,
    }

    # 일별 결과 저장
    path = f"result_{ticker}_{date}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"  → 저장: {path}")

    return output


def print_final_summary(daily_results: list[dict], output_path: str):
    print(f"\n{'='*60}")
    print(" 연속 시뮬레이션 최종 요약")
    print(f"{'='*60}")
    print(f"  {'날짜':<12} {'예측':<6} {'매수%':>6} {'매도%':>6} {'1일실제':>8} {'정확(1d)':>8}")
    print(f"  {'-'*55}")

    validator   = SimulationValidator()
    validations = []

    for r in daily_results:
        if "error" in r:
            print(f"  {r.get('issue_date','?'):<12} ERROR")
            continue
        res  = r["result"]
        val  = r.get("validation", {})
        ev1d = val.get("evaluations", {}).get("1d", {})

        actual_str  = f"{ev1d.get('actual_change_pct', 0):+.1f}%" if ev1d else "  N/A"
        correct_str = "✓" if ev1d.get("is_correct") else "✗" if ev1d else "-"

        print(f"  {r['issue_date']:<12} {res['prediction']:<6} "
              f"{res['buy_pressure']:>5.1f}% {res['sell_pressure']:>5.1f}% "
              f"{actual_str:>8} {correct_str:>8}")

        if "evaluations" in val:
            validations.append(val)

    if validations:
        summary = SimulationValidator.summarize_cases(validations)
        print(f"\n  전체 평균 정확도: {summary.get('avg_accuracy_pct', 0):.1f}%")
        pa = summary.get("period_accuracy", {})
        print(f"  1일: {pa.get('1d',0):.0f}% / 5일: {pa.get('5d',0):.0f}% / 20일: {pa.get('20d',0):.0f}%")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"daily_results": daily_results}, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  전체 결과 저장: {output_path}")


def get_trading_dates(start: str, end: str) -> list[str]:
    """토/일 제외 영업일 목록"""
    dates = []
    cur = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while cur <= end_dt:
        if cur.weekday() < 5:
            dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return dates


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentFlow 연속 시뮬레이션")
    parser.add_argument("--corp",   required=True, help="기업명 (예: SK하이닉스)")
    parser.add_argument("--ticker", required=True, help="종목코드 (예: 000660)")
    parser.add_argument("--start",  help="시작일 YYYY-MM-DD")
    parser.add_argument("--end",    help="종료일 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--days",   type=int, help="오늘 기준 며칠 전부터 (--start 대신)")
    parser.add_argument("--delay",  type=float, default=1.0, help="날짜 간 대기 시간(초)")
    args = parser.parse_args()

    # 날짜 범위 결정
    today = datetime.now().strftime("%Y-%m-%d")
    end_date   = args.end or today
    if args.days:
        start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    elif args.start:
        start_date = args.start
    else:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    dates = get_trading_dates(start_date, end_date)
    print(f"\n[연속 시뮬레이션] {args.corp} / {start_date} ~ {end_date} ({len(dates)}일)")

    # 공유 객체 초기화 (에이전트 메모리는 날짜 걸쳐 누적)
    llm    = LLMClient()
    memory = AgentMemory()
    agents = create_agents(llm, memory)

    # ── 사전 일괄 수집 (API 호출 최소화) ────────────────────
    print(f"\n[사전 수집] 전체 범위 데이터 일괄 수집 중...")
    dart_collector = DartCollector()
    news_collector = NewsCollector()

    disc_range  = dart_collector.get_disclosures_range(args.corp, start_date, end_date)
    news_range  = news_collector.get_news_range(args.corp, start_date, end_date)
    price_range = build_market_context_range(args.corp, start_date, end_date, ticker=args.ticker)
    print(f"[사전 수집 완료] 공시={sum(len(v) for v in disc_range.values())}건 "
          f"/ 뉴스={sum(len(v) for v in news_range.values())}건 "
          f"/ 주가={len(price_range)}일치\n")

    daily_results = []
    prev_result   = None

    for i, date in enumerate(dates):
        result = run_one_day(
            corp_name=args.corp,
            ticker=args.ticker,
            date=date,
            llm=llm,
            memory=memory,
            agents=agents,
            prev_result=prev_result,
            disc_range=disc_range,
            news_range=news_range,
            price_range=price_range,
        )
        daily_results.append(result)
        prev_result = result

        if i < len(dates) - 1:
            time.sleep(args.delay)

    output_path = f"continuous_{args.ticker}_{start_date}_{end_date}.json"
    print_final_summary(daily_results, output_path)