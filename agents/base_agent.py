import random
from llm.client import LLMClient
from agents.memory.agent_memory import AgentMemory


class BaseAgent:
    def __init__(self, agent_id: str, persona: dict, llm: LLMClient, memory: AgentMemory):
        self.agent_id = agent_id
        self.persona  = persona
        self.llm      = llm
        self.memory   = memory
        self.current_decision = None

        random.seed(agent_id)
        self._bias_val   = random.uniform(-0.25, 0.25)   # 넓힌 편향 범위
        self._attention  = random.sample(["가격", "거래량", "공시", "뉴스", "업황", "밸류에이션"], k=3)
        # 타입별 기본 성향: 매수/매도/관망 기준 확률 (프롬프트 강화 보조)
        self._base_tendency = {
            "retail":         random.choice(["매수편향", "매도편향", "중립"]),
            "day_trader":     random.choice(["매수편향", "매도편향"]),    # 단타는 방향성 강함
            "institutional":  "중립",                                     # 기관은 항상 중립
            "value_investor": random.choice(["매수편향", "중립"]),        # 가치투자자는 관망 많음
        }.get(persona.get("type", "retail"), "중립")
        random.seed()

    def decide(self, simulation_id: str, round_num: int, market_context: str, social_context: str = "") -> dict:
        past_decisions = self.memory.get_recent(self.agent_id, n=3)
        past_text = (
            "\n".join([f"- {p['action']} (확신도:{p.get('confidence',0):.1f}) — {p['reason']}" for p in past_decisions])
            if past_decisions else "첫 투자 결정"
        )

        # 직전 라운드 결정 (같은 시뮬레이션 내)
        prev_this_sim = [p for p in past_decisions if p.get("simulation_id") == simulation_id]
        if prev_this_sim:
            last = prev_this_sim[-1]
            prev_round_text = (
                f"나의 직전 라운드 결정: [{last['action']}] 확신도:{last.get('confidence',0):.1f} — {last['reason']}\n"
                f"→ 새로운 정보(군중 반응 등)를 반영해 이 결정을 유지할지, 바꿀지 판단하세요."
            )
        else:
            prev_round_text = "이번 시뮬레이션 첫 결정입니다."

        social_section = f"\n=== 시장 군중 반응 (직전 라운드) ===\n{social_context}" if social_context else ""

        attention_str = " / ".join(self._attention)
        user_prompt = f"""
=== 라운드 {round_num} — 오늘의 시장 정보 ===
{self._filter_context(market_context)}
{social_section}

=== 나의 직전 결정 ===
{prev_round_text}

=== 나의 과거 투자 이력 ===
{past_text}

=== 나의 주요 판단 기준 (이 요소들을 중심으로 분석할 것) ===
{attention_str}

{self._get_decision_constraint()}

반드시 JSON 객체만 출력:
{{"action": "매수 또는 매도 또는 관망", "reason": "결정 이유 50자 이내", "confidence": 0.0~1.0}}
"""
        result = self.llm.chat_json(
            system_prompt=self._get_system_prompt(),
            user_prompt=user_prompt,
        )

        if isinstance(result, dict) and "confidence" in result:
            result["confidence"] = max(0.1, min(1.0, float(result.get("confidence", 0.5)) + self._bias_val))

        self.current_decision = result
        self.memory.save(simulation_id, self.agent_id, round_num, result, market_context)

        print(f"  [{self.agent_id}] {result.get('action')} (확신도: {result.get('confidence', 0):.1f}) - {result.get('reason', '')[:40]}")
        return result

    def _get_system_prompt(self) -> str:
        p = self.persona
        return (
            f"당신은 {p.get('description', '')}입니다.\n"
            f"배경: {p.get('background', '')}\n"
            f"투자 성향: {p.get('risk_tolerance', '중간')}\n"
            f"판단 기준: {p.get('decision_criteria', '')}\n"
            f"감정 반응: {p.get('emotion_level', '중간')}\n"
            f"심리적 편향: {p.get('bias', '')}\n"
            f"특성: {p.get('special_trait', '')}\n"
            "한국 주식 시장 투자자로서 결정하세요.\n"
            "중요: 매수만이 정답이 아닙니다. 시장이 불확실하거나 하락 신호가 있으면 "
            "매도 또는 관망이 더 합리적입니다. 낙관 편향을 경계하세요.\n"
            "반드시 JSON 객체만 출력하세요."
        )

    def _filter_context(self, market_context: str) -> str:
        p_type = self.persona.get("type", "retail")
        name   = self.persona.get("name", self.agent_id)
        bias   = self.persona.get("bias", "")
        trait  = self.persona.get("special_trait", "")

        filters = {
            "retail": f"[{name}의 시각 — 편향: {bias}]\n{market_context}\n\n나는 주로 커뮤니티/뉴스에서 정보를 얻고, {trait}.",
            "institutional": f"[{name} 내부 리서치 — 편향: {bias}]\n{market_context}\n\n{trait}. 감정 배제, 데이터 기반 판단.",
            "day_trader": f"[{name} 실시간 신호 — 편향: {bias}]\n{market_context}\n\n{trait}. 오늘 안에 포지션 정리.",
            "value_investor": f"[{name} 장기 분석 — 편향: {bias}]\n{market_context}\n\n{trait}. 단기 노이즈 무시.",
        }
        return filters.get(p_type, market_context)

    def _get_decision_constraint(self) -> str:
        p_type   = self.persona.get("type", "retail")
        bias     = self.persona.get("bias", "")
        tendency = getattr(self, "_base_tendency", "중립")

        base = {
            "retail": (
                f"나의 심리적 편향은 '{bias}'이다. 현재 나의 성향은 [{tendency}].\n"
                "손실 공포(loss aversion)와 군중 심리에 영향받는다.\n"
                "주어진 정보에 부정적 신호가 있으면 매도나 관망이 자연스러운 반응이다.\n"
                "정보가 없거나 불확실하면 무리하게 매수하지 말고 관망을 선택하라.\n"
                "매수가 항상 옳지 않다. 지금 들어가면 손해볼 것 같으면 매도 또는 관망하라."
            ),
            "institutional": (
                f"나의 편향은 '{bias}'이지만 리스크 관리가 최우선이다.\n"
                "기대수익률이 리스크를 정당화하지 못하면 매도 또는 관망이 합리적 선택이다.\n"
                "불확실성이 높거나 정보가 부족한 상황에서는 포지션을 줄이는 것이 원칙이다.\n"
                "감정 배제, 주어진 데이터만으로 판단하라. 없는 정보를 추측하지 마라."
            ),
            "day_trader": (
                f"나의 편향은 '{bias}'. 현재 성향은 [{tendency}].\n"
                "오늘 안에 수익을 내야 한다. 방향이 불명확하면 즉시 현금화(매도 또는 관망).\n"
                "주어진 정보에서 하락 신호가 보이면 매도가 수익 기회다.\n"
                "정보가 없으면 섣불리 포지션 잡지 말고 관망하라. 확신 없는 매수는 금물이다."
            ),
            "value_investor": (
                f"나의 편향은 '{bias}'이다.\n"
                "현재 주가가 내재가치 대비 비싸 보이거나 성장 모멘텀이 꺾였으면 매도가 맞다.\n"
                "단기 호재에 흔들리지 않는다. 장기 펀더멘털이 훼손됐으면 관망 또는 매도.\n"
                "정보가 부족할 때는 섣불리 판단하지 말고 관망이 최선이다. 싸지 않으면 사지 않는다."
            ),
        }
        return base.get(p_type, f"편향({bias})을 인식하며 주어진 데이터에만 근거해 결정하라.")

    def get_summary(self) -> dict:
        return {"agent_id": self.agent_id, "type": self.persona.get("type"), "decision": self.current_decision}