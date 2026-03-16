from agents.base_agent import BaseAgent

DAY_TRADER_PERSONA = {
    "type": "day_trader",
    "description": "단기 차익을 노리는 공격적인 단타 트레이더",
    "risk_tolerance": "높음 (고위험 고수익 추구)",
    "decision_criteria": "변동성, 거래량 급증, 단기 모멘텀, 시장 심리",
    "emotion_level": "매우 높음 - 빠른 판단과 즉각적인 행동",
}


def create_day_trader_agents(llm, memory, count: int = 5) -> list[BaseAgent]:
    return [
        BaseAgent(f"day_trader_{i+1}", DAY_TRADER_PERSONA, llm, memory)
        for i in range(count)
    ]
