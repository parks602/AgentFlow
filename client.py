import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """
    Ollama ↔ OpenAI 전환 추상화 레이어
    .env의 LLM_MODE=ollama or openai 로 전환
    """

    def __init__(self):
        self.mode = os.getenv("LLM_MODE", "ollama")

        if self.mode == "ollama":
            self.client = OpenAI(
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key="ollama",
            )
            self.model = os.getenv("OLLAMA_MODEL", "phi4:latest")
        else:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        print(f"[LLMClient] mode={self.mode}, model={self.model}")

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        """기본 텍스트 응답"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        """JSON 응답 파싱까지 처리 — 에이전트 행동 결정에 사용"""
        full_system = system_prompt + "\n반드시 JSON 객체 형식으로만 응답하세요. 배열이 아닌 객체({})로 응답하세요. 마크다운 코드블록 없이 JSON만 출력하세요."
        raw = self.chat(full_system, user_prompt, temperature=0.3)

        # 코드블록 제거
        cleaned = raw.strip()
        for prefix in ["```json", "```"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # JSON 객체 부분만 추출 (앞뒤 불필요한 텍스트 제거)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]

        try:
            result = json.loads(cleaned)
            # list로 파싱된 경우 첫 번째 요소 사용
            if isinstance(result, list):
                result = result[0] if result else {}
            return result
        except json.JSONDecodeError:
            print(f"[LLMClient] JSON 파싱 실패: {raw[:200]}")
            return {"action": "관망", "reason": "파싱 오류", "confidence": 0.0}