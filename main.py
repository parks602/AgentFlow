"""
market-simulation 메인 실행 파일
사용법:
  python main.py --corp 삼성전자 --ticker 005930 --date 2024-01-15
"""
import argparse
import json
from llm.client import LLMClient
from agents.memory.agent_memory import AgentMemory
from agents.agent_factory import create_agents
from data.collector.dart_collector import DartCollector
from data.collector.news_collector import NewsCollector
from data.collector.price_collector import build_market_context
from data.seed_parser import SeedParser
from simulation.engine import SimulationEngine
from evaluation.validator import SimulationValidator


def run_simulation(corp_name: str, ticker: str, issue_date: str):
    print(f"\n{'='*60}")
    print(f" Market Simulation: {corp_name} ({ticker}) / {issue_date}")
    print(f"{'='*60}\n")

    # ── 1. LLM & 메모리 초기화 ─────────────────────────────
    llm = LLMClient()
    memory = AgentMemory()

    # ── 2. 데이터 수집 ─────────────────────────────────────
    print("[1/4] 데이터 수집 중...")

    dart = DartCollector()
    news = NewsCollector()

    disclosures = dart.get_recent_major_disclosures(corp_name, issue_date)
    news_articles = news.get_news_by_keyword(corp_name, issue_date, days=3)
    news_text = news.format_for_seed(news_articles)
    market_ctx = build_market_context(corp_name, issue_date, ticker=ticker)

    # ── 3. 씨드 파싱 ───────────────────────────────────────
    print("\n[2/4] 씨드 파싱 중...")
    parser = SeedParser(llm)
    seed = parser.parse(corp_name, disclosures, news_text, market_ctx, raw_articles=news_articles)
    print(f"  → {seed.get('summary', '')[:80]}...")

    # ── 4. 에이전트 생성 ───────────────────────────────────
    print(f"\n[3/4] 에이전트 {NUM_AGENTS_PER_TYPE * 4}명 생성 중...")
    agents = (
        create_retail_agents(llm, memory, NUM_AGENTS_PER_TYPE)
        + create_institutional_agents(llm, memory, NUM_AGENTS_PER_TYPE)
        + create_day_trader_agents(llm, memory, NUM_AGENTS_PER_TYPE)
        + create_value_investor_agents(llm, memory, NUM_AGENTS_PER_TYPE)
    )

    # ── 5. 시뮬레이션 실행 ────────────────────────────────
    print(f"\n[4/4] 시뮬레이션 실행 중...")
    engine = SimulationEngine(agents)
    sim_result = engine.run(seed)

    # ── 6. 검증 ───────────────────────────────────────────
    print(f"\n[검증] 실제 주가와 비교 중...")
    validator = SimulationValidator()
    validation = validator.validate(sim_result, ticker, issue_date, market_ctx)

    # ── 7. 결과 출력 ──────────────────────────────────────
    print(f"\n{'='*60}")
    print(" 최종 결과")
    print(f"{'='*60}")
    result = sim_result["result"]
    print(f"  예측: {result['prediction']} ({result['strength']})")
    print(f"  매수 압력: {result['buy_pressure']:.1f}%")
    print(f"  매도 압력: {result['sell_pressure']:.1f}%")

    if "evaluations" in validation:
        print(f"\n  실제 주가 비교:")
        for period, ev in validation["evaluations"].items():
            period_label = {"1d": "1일 후", "5d": "1주 후", "20d": "1달 후"}.get(period, period)
            correct_mark = "✓" if ev["is_correct"] else "✗"
            print(f"    {period_label}: 실제 {ev['actual_direction']} "
                  f"({ev['actual_change_pct']:+.1f}%) {correct_mark}")
        print(f"\n  정확도: {validation['accuracy_pct']:.0f}% "
              f"({validation['correct_count']}/{validation['total_periods']})")

    # 결과 저장
    output = {
        "corp_name": corp_name,
        "ticker": ticker,
        "issue_date": issue_date,
        "seed": seed,
        "result": result,
        "validation": validation,
    }
    output_path = f"result_{ticker}_{issue_date}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  결과 저장: {output_path}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market Simulation")
    parser.add_argument("--corp", required=True, help="기업명 (예: 삼성전자)")
    parser.add_argument("--ticker", required=True, help="종목코드 (예: 005930)")
    parser.add_argument("--date", required=True, help="이슈 날짜 (예: 2024-01-15)")
    args = parser.parse_args()

    run_simulation(args.corp, args.ticker, args.date)