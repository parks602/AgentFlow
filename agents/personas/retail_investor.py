from agents.base_agent import BaseAgent

RETAIL_PERSONA = {
    "type": "retail",
    "description": "감정적으로 뉴스에 반응하는 개인 투자자",
    "risk_tolerance": "중간 (손실 회피 성향 강함)",
    "decision_criteria": "뉴스 제목, 커뮤니티 반응, 단기 주가 움직임",
    "emotion_level": "높음 - 공포와 탐욕에 쉽게 흔들림",
}


def create_retail_agents(llm, memory, count: int = 5) -> list[BaseAgent]:
    return [
        BaseAgent(f"retail_{i+1}", RETAIL_PERSONA, llm, memory)
        for i in range(count)
    ]
