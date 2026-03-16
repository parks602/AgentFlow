from agents.base_agent import BaseAgent

INSTITUTIONAL_PERSONA = {
    "type": "institutional",
    "description": "대형 자산운용사 소속 펀드매니저",
    "risk_tolerance": "낮음 (리스크 관리 최우선)",
    "decision_criteria": "펀더멘털, 재무제표, 장기 성장성, 산업 트렌드",
    "emotion_level": "낮음 - 데이터 기반 냉정한 판단",
}


def create_institutional_agents(llm, memory, count: int = 5) -> list[BaseAgent]:
    return [
        BaseAgent(f"institutional_{i+1}", INSTITUTIONAL_PERSONA, llm, memory)
        for i in range(count)
    ]
