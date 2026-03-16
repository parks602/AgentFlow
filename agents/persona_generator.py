"""
LLM으로 다양한 투자자 페르소나를 동적 생성
에이전트 초기화 시 1회 호출, 결과는 캐싱
"""
import json
from llm.client import LLMClient


PERSONA_TEMPLATES = {
    "retail": {
        "count": 5,
        "prompt": """한국 주식 시장의 개인 투자자 {count}명을 생성하세요.
각자 나이, 직업, 투자 경력, 성격, 투자 스타일이 완전히 달라야 합니다.
다양한 배경: 2030 직장인, 4050 자영업자, 코인 경험자, 손실 트라우마 보유자, 주식 초보 등
반드시 JSON 배열로만 응답하세요:
[
  {{
    "id": "retail_1",
    "type": "retail",
    "name": "투자자 닉네임",
    "background": "나이/직업/투자경력 한 줄 설명",
    "description": "이 사람이 어떤 투자자인지 2문장",
    "risk_tolerance": "매우높음/높음/중간/낮음/매우낮음 중 하나",
    "decision_criteria": "투자 결정 시 가장 중요하게 보는 것",
    "emotion_level": "매우높음/높음/중간/낮음 중 하나",
    "bias": "이 투자자의 심리적 편향 (예: 손실회피, FOMO, 확증편향 등)",
    "special_trait": "이 투자자만의 독특한 특성 (예: 반도체 업종 전문가, 커뮤니티 의존도 높음)"
  }}
]""",
    },
    "institutional": {
        "count": 5,
        "prompt": """한국 주식 시장의 기관 투자자 {count}명을 생성하세요.
각자 소속 기관 유형, 운용 전략, 리스크 기준이 완전히 달라야 합니다.
다양한 배경: 연기금, 외국계 IB, 국내 자산운용사, 헤지펀드, 보험사 등
반드시 JSON 배열로만 응답하세요:
[
  {{
    "id": "institutional_1",
    "type": "institutional",
    "name": "기관명/역할",
    "background": "소속 기관 유형/운용 규모/투자 철학",
    "description": "이 기관 투자자가 어떻게 판단하는지 2문장",
    "risk_tolerance": "매우높음/높음/중간/낮음/매우낮음 중 하나",
    "decision_criteria": "투자 결정 시 가장 중요하게 보는 지표",
    "emotion_level": "매우높음/높음/중간/낮음 중 하나",
    "bias": "이 기관의 구조적 편향 (예: 벤치마크 추종, 단기 성과 압박 등)",
    "special_trait": "이 기관만의 독특한 투자 기준"
  }}
]""",
    },
    "day_trader": {
        "count": 5,
        "prompt": """한국 주식 시장의 단기 트레이더 {count}명을 생성하세요.
각자 매매 스타일, 사용 지표, 심리 패턴이 완전히 달라야 합니다.
다양한 배경: 전업 트레이더, 스캘퍼, 파생상품 병행, 알고리즘 트레이더, 테마주 전문 등
반드시 JSON 배열로만 응답하세요:
[
  {{
    "id": "day_trader_1",
    "type": "day_trader",
    "name": "트레이더 닉네임",
    "background": "트레이딩 경력/주요 매매 스타일",
    "description": "이 트레이더가 어떻게 매매하는지 2문장",
    "risk_tolerance": "매우높음/높음/중간/낮음/매우낮음 중 하나",
    "decision_criteria": "매매 결정의 핵심 신호",
    "emotion_level": "매우높음/높음/중간/낮음 중 하나",
    "bias": "이 트레이더의 매매 편향 (예: 추세추종, 역추세, 뇌동매매 등)",
    "special_trait": "이 트레이더만의 독특한 매매 패턴"
  }}
]""",
    },
    "value_investor": {
        "count": 5,
        "prompt": """한국 주식 시장의 가치 투자자 {count}명을 생성하세요.
각자 투자 철학, 선호 섹터, 분석 방법이 완전히 달라야 합니다.
다양한 배경: 워런 버핏 추종자, 퀀트 가치투자, 배당투자자, 턴어라운드 전문, 글로벌 매크로 등
반드시 JSON 배열로만 응답하세요:
[
  {{
    "id": "value_investor_1",
    "type": "value_investor",
    "name": "투자자 닉네임",
    "background": "투자 경력/철학/주요 관심 섹터",
    "description": "이 투자자가 어떻게 기업을 분석하는지 2문장",
    "risk_tolerance": "매우높음/높음/중간/낮음/매우낮음 중 하나",
    "decision_criteria": "투자 결정의 핵심 기준",
    "emotion_level": "매우높음/높음/중간/낮음 중 하나",
    "bias": "이 투자자의 인지 편향 (예: 가치함정, 앵커링, 집중투자 고집 등)",
    "special_trait": "이 투자자만의 독특한 분석 방법"
  }}
]""",
    },
}


def generate_personas(llm: LLMClient, cache_path: str = "personas_cache.json") -> list[dict]:
    """
    LLM으로 20개 페르소나 동적 생성
    cache_path에 저장해두고 재실행 시 재사용
    """
    import os
    if os.path.exists(cache_path):
        print(f"[Persona] 캐시 로드: {cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    print("[Persona] LLM으로 투자자 페르소나 생성 중...")
    all_personas = []

    for p_type, config in PERSONA_TEMPLATES.items():
        print(f"  [{p_type}] {config['count']}명 생성...")
        prompt = config["prompt"].format(count=config["count"])

        raw = llm.chat(
            system_prompt="당신은 한국 주식 시장 투자자 캐릭터 설계 전문가입니다. 반드시 JSON 배열만 출력하세요.",
            user_prompt=prompt,
            temperature=0.9,  # 다양성을 위해 높게
        )

        personas = _parse_persona_list(raw, p_type, config["count"])
        all_personas.extend(personas)
        print(f"  [{p_type}] {len(personas)}명 생성 완료")

    # 캐시 저장
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(all_personas, f, ensure_ascii=False, indent=2)
    print(f"[Persona] 총 {len(all_personas)}명 생성 완료 → {cache_path}")

    return all_personas


def _parse_persona_list(raw: str, p_type: str, count: int) -> list[dict]:
    """LLM 응답에서 JSON 배열 파싱"""
    cleaned = raw.strip()
    for prefix in ["```json", "```"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # [ ] 구간 추출
    start = cleaned.find("[")
    end   = cleaned.rfind("]") + 1
    if start != -1 and end > start:
        cleaned = cleaned[start:end]

    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            # id/type 보정
            for i, p in enumerate(result):
                p["id"]   = f"{p_type}_{i+1}"
                p["type"] = p_type
            return result
    except json.JSONDecodeError:
        print(f"  [경고] {p_type} 페르소나 파싱 실패, 기본값 사용")

    # 파싱 실패 시 기본 페르소나
    return [_default_persona(p_type, i+1) for i in range(count)]


def _default_persona(p_type: str, idx: int) -> dict:
    defaults = {
        "retail":         {"description": f"개인투자자 {idx}호", "risk_tolerance": "중간", "decision_criteria": "뉴스와 커뮤니티 반응", "emotion_level": "높음", "bias": "FOMO", "special_trait": "단타 선호"},
        "institutional":  {"description": f"기관투자자 {idx}호", "risk_tolerance": "낮음", "decision_criteria": "DCF 밸류에이션", "emotion_level": "낮음", "bias": "벤치마크 추종", "special_trait": "리스크 관리 중시"},
        "day_trader":     {"description": f"단타트레이더 {idx}호", "risk_tolerance": "매우높음", "decision_criteria": "거래량과 모멘텀", "emotion_level": "매우높음", "bias": "추세추종", "special_trait": "빠른 손절"},
        "value_investor": {"description": f"가치투자자 {idx}호", "risk_tolerance": "낮음", "decision_criteria": "PBR/PER 내재가치", "emotion_level": "낮음", "bias": "가치함정", "special_trait": "장기보유"},
    }
    d = defaults.get(p_type, defaults["retail"])
    return {"id": f"{p_type}_{idx}", "type": p_type, "name": f"{p_type}_{idx}", "background": "기본 설정", **d}
