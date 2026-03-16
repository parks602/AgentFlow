from agents.base_agent import BaseAgent

VALUE_INVESTOR_PERSONA = {
    "type": "value_investor",
    "description": "장기 가치 투자를 추구하는 워런 버핏형 투자자",
    "risk_tolerance": "낮음 (원금 보전 최우선, 안전마진 중시)",
    "decision_criteria": "내재가치, PER/PBR, 경쟁 우위, 장기 사업 전망",
    "emotion_level": "매우 낮음 - 시장 소음에 흔들리지 않음",
}


def create_value_investor_agents(llm, memory, count: int = 5) -> list[BaseAgent]:
    return [
        BaseAgent(f"value_investor_{i+1}", VALUE_INVESTOR_PERSONA, llm, memory)
        for i in range(count)
    ]
