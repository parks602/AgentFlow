import os
from dotenv import load_dotenv

load_dotenv()

# LLM
LLM_MODE = os.getenv("LLM_MODE", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi4:latest")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# DART
DART_API_KEY = os.getenv("DART_API_KEY", "")

# 시뮬레이션 설정
NUM_AGENTS_PER_TYPE = 5        # 에이전트 타입당 인원수 (총 20명)
INTERACTION_ROUNDS = 3         # 에이전트 간 상호작용 라운드 수
SOCIAL_CONTEXT_SAMPLE = 5      # 상호작용 시 참고할 주변 에이전트 수

# 검증 설정
VALIDATION_DAYS = [1, 5, 20]   # 1일, 1주, 1달 후 비교
