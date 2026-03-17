import json
from llm.client import LLMClient


class SeedParser:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def parse(
        self,
        corp_name: str,
        disclosures: list[dict],
        news_text: str,
        market_context: dict,
        raw_articles: list[dict] | None = None,  # 원문 기사 리스트 (대시보드 표시용)
    ) -> dict:

        # 데이터 없으면 LLM 호출 스킵
        if not disclosures and (not news_text or news_text == "관련 뉴스 없음") and not market_context:
            print("[SeedParser] 수집된 데이터 없음")
            return {
                "corp_name": corp_name,
                "summary": f"{corp_name} 관련 공시/뉴스를 찾을 수 없습니다.",
                "issue_type": "기타",
                "sentiment": "neutral",
                "impact_level": "low",
                "key_points": ["데이터 없음"],
                "raw_disclosure_count": 0,
                "raw_articles": [],
                "raw_disclosures": [],
            }

        disclosure_text = "\n".join(
            [f"[공시] {d['report_nm']}: {d['text'][:500]}" for d in disclosures]
        ) if disclosures else "공시 없음"

        price_text = (
            f"최근 5일 주가 추이: {market_context.get('trend', '정보없음')} "
            f"({market_context.get('price_change_5d_pct', 0):+.1f}%), "
            f"현재가: {market_context.get('current_price', 0):,.0f}원"
            if market_context else "주가 정보 없음"
        )

        user_prompt = f"""
다음은 {corp_name}에 대한 시장 정보입니다.

=== 공시 내용 ===
{disclosure_text}

=== 관련 뉴스 ===
{news_text}

=== 주가 현황 ===
{price_text}

위 정보를 분석해서 반드시 아래 JSON 객체 형식으로만 응답하세요.

중요 지침:
- 주가가 하락 추세이거나 부정적 공시/뉴스면 sentiment는 반드시 negative
- 긍정/부정 근거가 혼재하면 neutral, 명확한 호재만 있을 때 positive
- 낙관적으로 해석하지 말고 리스크 요인을 우선 반영하세요
- key_points에는 상승 근거와 하락 근거를 균형있게 포함하세요

{{
    "summary": "투자자 관점의 시장 상황 요약 — 리스크와 기회를 균형있게 (200자 이내)",
    "issue_type": "실적발표/유상증자/오너리스크/업황변화/인수합병/기타 중 하나",
    "sentiment": "positive/negative/neutral 중 하나 (주가 추세와 반드시 일치)",
    "impact_level": "high/medium/low 중 하나",
    "key_points": ["상승 근거 또는 리스크 요인 1", "리스크 또는 불확실성 2", "기타 포인트 3"]
}}
"""
        system_prompt = (
            "당신은 한국 주식 시장 리스크 분석가입니다. "
            "낙관 편향 없이 데이터에 근거해 냉정하게 분석하세요. "
            "주가 하락 추세나 부정적 공시는 명확히 negative로 판단하세요. "
            "반드시 JSON 객체만 출력하세요. 배열([])이 아닌 객체({})로 응답하세요."
        )

        raw = self.llm.chat(system_prompt, user_prompt, temperature=0.3)

        # JSON 직접 파싱 (client.py chat_json과 동일한 로직)
        result = self._parse_json(raw, corp_name)
        result["corp_name"] = corp_name
        result["raw_disclosure_count"] = len(disclosures)

        # 원문 기사/공시 저장 (대시보드 스토리 카드용)
        if raw_articles:
            result["raw_articles"] = [
                {
                    "title":       a.get("title", ""),
                    "description": a.get("description", "")[:300],
                    "press":       a.get("press", ""),
                    "date":        a.get("date", ""),
                    "url":         a.get("url", ""),
                    "source":      a.get("source", ""),
                }
                for a in raw_articles[:8]  # 최대 8건
            ]
        if disclosures:
            result["raw_disclosures"] = [
                {
                    "title": d.get("report_nm", ""),
                    "date":  d.get("rcept_dt", ""),
                    "corp":  d.get("corp_name", corp_name),
                }
                for d in disclosures[:5]  # 최대 5건
            ]

        print(f"[SeedParser] 씨드 파싱 완료: {result.get('issue_type')} / {result.get('sentiment')}")
        return result

    def _parse_json(self, raw: str, corp_name: str) -> dict:
        """LLM 응답에서 JSON 객체 추출 — 배열/코드블록 모두 처리"""
        cleaned = raw.strip()

        # 코드블록 제거
        for prefix in ["```json", "```"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # { } 구간만 추출
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            cleaned = cleaned[start:end]

        try:
            result = json.loads(cleaned)
            # 배열로 왔을 경우 첫 번째 요소 사용
            if isinstance(result, list):
                result = result[0] if result else {}
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            print(f"[SeedParser] JSON 파싱 실패, 기본값 사용. raw={raw[:100]}")

        # 파싱 완전 실패 시 기본값
        return {
            "summary": f"{corp_name} 관련 이슈 발생",
            "issue_type": "기타",
            "sentiment": "neutral",
            "impact_level": "medium",
            "key_points": ["파싱 오류로 기본값 사용"],
        }