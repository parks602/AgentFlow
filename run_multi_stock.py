"""
10개 종목 배치 실행 → DB 저장
사용법:
  python run_multi_stock.py                                       # 전체 종목, 최근 5일
  python run_multi_stock.py --days 5                             # 최근 5일
  python run_multi_stock.py --start 2024-01-10 --end 2024-01-20  # 날짜 범위 지정
  python run_multi_stock.py --tickers 000660 005930              # 특정 종목만
  python run_multi_stock.py --tickers 000660 --start 2024-01-10 --end 2024-01-20
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
from data.collector.price_collector import build_market_context, build_market_context_range
from data.seed_parser import SeedParser
from simulation.engine import SimulationEngine
from evaluation.validator import SimulationValidator
from db.store import save_run, get_summary_stats


def get_trading_dates(start: str, end: str) -> list[str]:
    dates, cur = [], datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while cur <= end_dt:
        if cur.weekday() < 5:
            dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return dates


def build_carry_over(prev: dict | None) -> str:
    if not prev:
        return ""
    r = prev.get("result", {})
    return (
        f"[전일({prev.get('issue_date','')}) 이월] "
        f"예측:{r.get('prediction','?')} | "
        f"매수:{r.get('buy_pressure',0):.0f}% | 매도:{r.get('sell_pressure',0):.0f}%\n"
        f"요약: {prev.get('seed',{}).get('summary','')[:80]}"
    )


def run_stock(corp: str, ticker: str, sector: str, dates: list[str],
              llm: LLMClient, memory: AgentMemory, agents: list) -> list[dict]:
    """단일 종목 연속 시뮬레이션 — 데이터 사전 일괄 수집 후 날짜 루프"""
    print(f"\n{'━'*60}")
    print(f"  {corp} ({ticker}) | {sector} | {len(dates)}일")
    print(f"{'━'*60}")

    dart      = DartCollector()
    news      = NewsCollector()
    validator = SimulationValidator()

    start_date = dates[0]
    end_date   = dates[-1]

    # ── 사전 일괄 수집 (API 호출 최소화) ─────────────────────
    print(f"  [사전 수집] {start_date} ~ {end_date}")
    disc_range  = dart.get_disclosures_range(corp, start_date, end_date)
    news_range  = news.get_news_range(corp, start_date, end_date)
    price_range = build_market_context_range(corp, start_date, end_date, ticker=ticker)
    print(f"  [사전 수집 완료] 공시={sum(len(v) for v in disc_range.values())}건 "
          f"/ 뉴스={sum(len(v) for v in news_range.values())}건 "
          f"/ 주가={len(price_range)}일치")

    # ── 날짜별 시뮬레이션 루프 ───────────────────────────────
    daily_results, prev = [], None

    for date in dates:
        print(f"\n  [{date}]")
        try:
            disclosures   = disc_range.get(date, [])
            news_articles = news_range.get(date, [])
            news_text     = news.format_for_seed(news_articles)
            market_ctx    = price_range.get(date, {})

            if not market_ctx:
                print(f"  [경고] {date} 주가 데이터 없음 — 스킵")
                continue

            parser = SeedParser(llm)
            seed   = parser.parse(corp, disclosures, news_text, market_ctx, raw_articles=news_articles)
            carry  = build_carry_over(prev)
            if carry:
                seed.setdefault("key_points", []).append(carry)
            seed["market_context"] = market_ctx

            engine     = SimulationEngine(agents)
            sim_result = engine.run(seed)
            validation = validator.validate(sim_result, ticker, date, market_ctx)

            result = {
                "corp_name":  corp,
                "ticker":     ticker,
                "issue_date": date,
                "seed":       seed,
                "result":     sim_result["result"],
                "validation": validation,
                "final_decisions": sim_result.get("final_decisions", []),
            }
            daily_results.append(result)
            prev = result

        except Exception as e:
            print(f"  [ERROR] {date}: {e}")
            import traceback; traceback.print_exc()
            daily_results.append({"corp_name": corp, "ticker": ticker,
                                   "issue_date": date, "error": str(e)})

    return daily_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",    type=int, default=5, help="최근 며칠 (기본 5, --start/--end 없을 때)")
    parser.add_argument("--start",   type=str, default=None, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end",     type=str, default=None, help="종료일 YYYY-MM-DD")
    parser.add_argument("--tickers", nargs="+", help="특정 종목코드만 (예: 000660 005930)")
    parser.add_argument("--delay",   type=float, default=2.0, help="종목 간 대기(초)")
    args = parser.parse_args()

    # 날짜 범위 — --start/--end 우선, 없으면 --days 기반
    today = datetime.now().strftime("%Y-%m-%d")
    if args.start and args.end:
        dates = get_trading_dates(args.start, args.end)
    elif args.start:
        dates = get_trading_dates(args.start, today)
    else:
        start_date = (datetime.now() - timedelta(days=args.days + 3)).strftime("%Y-%m-%d")
        dates = get_trading_dates(start_date, today)[-args.days:]
    print(f"\n[배치] 날짜: {dates[0]} ~ {dates[-1]} ({len(dates)}일)")

    # 종목 로드
    with open("stocks_config.json", encoding="utf-8") as f:
        stocks = json.load(f)
    if args.tickers:
        stocks = [s for s in stocks if s["ticker"] in args.tickers]
    print(f"[배치] 종목: {len(stocks)}개\n")

    # 공유 LLM / 에이전트 초기화
    llm    = LLMClient()
    memory = AgentMemory()
    agents = create_agents(llm, memory)

    # 종목별 실행 → DB 저장
    all_run_ids = []
    for i, stock in enumerate(stocks):
        # ✅ 종목 전환 시 에이전트 메모리 초기화 — 종목 간 교차 오염 방지
        memory.clear_all_agent_history()

        daily = run_stock(
            corp=stock["corp"], ticker=stock["ticker"], sector=stock["sector"],
            dates=dates, llm=llm, memory=memory, agents=agents,
        )
        run_id = save_run(daily, stock["corp"], stock["ticker"], stock["sector"])
        all_run_ids.append(run_id)

        if i < len(stocks) - 1:
            print(f"\n[대기] {args.delay}초...")
            time.sleep(args.delay)

    # 최종 요약
    stats = get_summary_stats()
    print(f"\n{'='*60}")
    print(" 전체 배치 완료")
    print(f"{'='*60}")
    print(f"  총 run: {stats.get('total_runs')}개")
    print(f"  종목 수: {stats.get('total_tickers')}개")
    print(f"  평균 1일 정확도: {stats.get('avg_accuracy')}%")