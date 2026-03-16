"""
페르소나 기반 에이전트 팩토리
generate_personas()로 생성된 페르소나 목록을 받아 BaseAgent 리스트 반환
"""
from agents.base_agent import BaseAgent
from agents.persona_generator import generate_personas
from agents.memory.agent_memory import AgentMemory
from llm.client import LLMClient


def create_agents(llm: LLMClient, memory: AgentMemory, cache_path: str = "personas_cache.json") -> list[BaseAgent]:
    """LLM으로 페르소나 생성 후 에이전트 초기화"""
    personas = generate_personas(llm, cache_path)
    agents = [
        BaseAgent(
            agent_id=p["id"],
            persona=p,
            llm=llm,
            memory=memory,
        )
        for p in personas
    ]
    print(f"[Factory] 에이전트 {len(agents)}명 초기화 완료")
    return agents


def reset_personas(cache_path: str = "personas_cache.json"):
    """캐시 삭제 — 다음 실행 시 새 페르소나 생성"""
    import os
    if os.path.exists(cache_path):
        os.remove(cache_path)
        print(f"[Factory] 페르소나 캐시 삭제: {cache_path}")
