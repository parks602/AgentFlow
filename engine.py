from agents.base_agent import BaseAgent
from simulation.interaction import InteractionEngine
from simulation.aggregator import ResultAggregator
from config.settings import INTERACTION_ROUNDS
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid
import time


class SimulationEngine:
    """
    Time Engine - 장 시작 전 / 장 중 / 장 마감 3단계 시뮬레이션
    에이전트 결정을 멀티스레드로 병렬 실행
    """

    def __init__(self, agents: list[BaseAgent], max_workers: int = 8):
        self.agents = agents
        self.interaction = InteractionEngine(agents)
        self.aggregator = ResultAggregator()
        self.simulation_id = str(uuid.uuid4())[:8]
        self.max_workers = max_workers

    def run(self, seed: dict) -> dict:
        market_context = self._build_market_context(seed)
        all_decisions = []

        print(f"\n{'='*50}")
        print(f"[Engine] 시뮬레이션 시작 (ID: {self.simulation_id})")
        print(f"[Engine] 기업: {seed.get('corp_name')} / 이슈: {seed.get('issue_type')}")
        print(f"[Engine] 에이전트: {len(self.agents)}명 / 병렬: {self.max_workers}스레드")
        print(f"{'='*50}")

        # ── 1단계: 장 시작 전 ───────────────────────────────
        print("\n[장 시작 전] 공시 최초 반응")
        t0 = time.time()
        round1 = self._run_round_parallel(
            round_num=1,
            market_context=market_context,
            social_context="",
        )
        all_decisions.extend(round1)
        print(f"  → {time.time()-t0:.1f}초 소요")

        # ── 2단계: 장 중 (상호작용) ──────────────────────────
        prev_round = round1
        for r in range(2, INTERACTION_ROUNDS + 1):
            print(f"\n[장 중 - 라운드 {r}] 주변 반응 반영")
            social_ctx = self.interaction.build_social_context(prev_round)
            t0 = time.time()
            round_r = self._run_round_parallel(
                round_num=r,
                market_context=market_context,
                social_context=social_ctx,
            )
            all_decisions.extend(round_r)
            prev_round = round_r
            print(f"  → {time.time()-t0:.1f}초 소요")

        # ── 3단계: 장 마감 ────────────────────────────────────
        # 마지막 라운드를 final로 사용하되,
        # 집계는 마지막 라운드만 반영 (군중 반응 최종 수렴 결과가 가장 신뢰도 높음)
        print("\n[장 마감] 최종 집계")
        final_round = prev_round
        result = self.aggregator.aggregate(final_round, self.agents)

        print(f"[Engine] 예측 결과: {result['prediction']} "
              f"(매수압력: {result['buy_pressure']:.1f}% / 매도압력: {result['sell_pressure']:.1f}% / "
              f"순압력: {result['net_pressure']:+.1f}% / 불일치: {result['disagreement']:.2f})")

        return {
            "simulation_id":   self.simulation_id,
            "seed":            seed,
            "all_decisions":   all_decisions,    # 전 라운드 전체 이력
            "final_decisions": final_round,      # 집계에 사용된 마지막 라운드
            "result":          result,
        }

    def _run_round_parallel(
        self, round_num: int, market_context: str, social_context: str
    ) -> list[dict]:
        """멀티스레드로 에이전트 결정 병렬 실행"""
        results = [None] * len(self.agents)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    agent.decide,
                    self.simulation_id, round_num, market_context, social_context
                ): i
                for i, agent in enumerate(self.agents)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    d = future.result()
                    # agent_id, persona_type 보장
                    agent = self.agents[idx]
                    results[idx] = {
                        "agent_id":    agent.agent_id,
                        "persona_type": agent.persona.get("type", "retail"),
                        **d,
                    }
                except Exception as e:
                    agent = self.agents[idx]
                    print(f"  [경고] {agent.agent_id} 결정 실패: {e}")
                    results[idx] = {
                        "agent_id":    agent.agent_id,
                        "persona_type": agent.persona.get("type", "retail"),
                        "action": "관망", "reason": "오류", "confidence": 0.1,
                    }

        return [r for r in results if r]

    def _build_market_context(self, seed: dict) -> str:
        price_info = ""
        ctx = seed.get("market_context", {})
        if ctx:
            price_info = (
                f"\n현재가: {ctx.get('current_price', 0):,.0f}원 | "
                f"5일 등락: {ctx.get('price_change_5d_pct', 0):+.1f}% | "
                f"추세: {ctx.get('trend', '정보없음')}"
            )

        # 공시/뉴스 수집 여부 명시
        disc_cnt  = seed.get("raw_disclosure_count", 0)
        news_cnt  = len(seed.get("raw_articles", []))
        data_note = ""
        if disc_cnt == 0 and news_cnt == 0:
            data_note = "\n\n⚠️ 오늘은 수집된 공시와 뉴스가 없습니다. 주가 데이터와 최근 시장 흐름만으로 판단하세요."
        elif disc_cnt == 0:
            data_note = f"\n\n※ 공시 없음. 뉴스 {news_cnt}건 기반 분석."
        elif news_cnt == 0:
            data_note = f"\n\n※ 뉴스 없음. 공시 {disc_cnt}건 기반 분석."

        # key_points에서 이월 컨텍스트 제외
        key_points = [
            p for p in seed.get("key_points", [])
            if isinstance(p, str) and not p.startswith("[전일")
        ]
        kp_text = "\n".join([f"  • {p}" for p in key_points]) if key_points else "  • 특이 포인트 없음"

        # 감성/영향도를 한국어로 변환 (LLM이 더 직관적으로 읽도록)
        sentiment_kr = {"positive": "긍정적", "negative": "부정적", "neutral": "중립적"}.get(
            seed.get("sentiment", "neutral"), "중립적"
        )
        impact_kr = {"high": "높음", "medium": "보통", "low": "낮음"}.get(
            seed.get("impact_level", "medium"), "보통"
        )

        return (
            f"기업명: {seed.get('corp_name', '미상')} | 이슈 유형: {seed.get('issue_type', '미상')}"
            f"{price_info}"
            f"{data_note}\n\n"
            f"[오늘의 시장 상황 요약]\n"
            f"→ {seed.get('summary', '')}\n"
            f"(시장 분위기: {sentiment_kr} / 이슈 영향도: {impact_kr})\n\n"
            f"[주요 포인트]\n{kp_text}"
        )