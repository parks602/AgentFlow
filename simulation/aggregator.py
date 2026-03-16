class ResultAggregator:
    """
    에이전트 결정 집계 → 매수/매도 압력 수치화 → 예측 방향 결정
    """

    # 타입별 가중치 — KOSPI 거래대금 현실 반영
    # 개인: 60~70% / 기관: 20% / 외국인+기타: 10~20%
    # 단타(개인 고빈도)도 개인 범주로 자금력 높음
    TYPE_WEIGHTS = {
        "retail":         1.8,   # 개인: 거래대금 1위, 군중심리 시장지배
        "day_trader":     1.6,   # 단타 개인: 고빈도 + 레버리지
        "value_investor": 1.2,   # 장기 개인/소형펀드
        "institutional":  1.0,   # 기관: 거래대금은 낮지만 방향성은 신뢰도 높음
    }

    def aggregate(self, decisions: list[dict], agents: list) -> dict:
        # agent_id → type 맵 구성
        id_to_type = {a.agent_id: a.persona.get("type", "retail") for a in agents}

        buy_score  = 0.0
        sell_score = 0.0
        hold_score = 0.0
        total_weight = 0.0
        type_breakdown: dict[str, dict] = {}

        for d in decisions:
            agent_id = d.get("agent_id", "")
            # agent_id로 타입 조회, 없으면 persona_type 폴백, 최후엔 retail
            ptype      = id_to_type.get(agent_id) or d.get("persona_type", "retail")
            action     = d.get("action", "관망")
            confidence = float(d.get("confidence", 0.5))
            weight     = self.TYPE_WEIGHTS.get(ptype, 1.0)
            score      = weight * confidence

            if action == "매수":
                buy_score += score
            elif action == "매도":
                sell_score += score
            else:
                hold_score += score

            total_weight += weight

            if ptype not in type_breakdown:
                type_breakdown[ptype] = {"매수": 0, "매도": 0, "관망": 0, "total": 0}
            type_breakdown[ptype][action] = type_breakdown[ptype].get(action, 0) + 1
            type_breakdown[ptype]["total"] += 1

        total_score = buy_score + sell_score + hold_score or 1
        buy_pct  = buy_score  / total_score * 100
        sell_pct = sell_score / total_score * 100
        hold_pct = hold_score / total_score * 100

        # ── 예측 방향 결정 ─────────────────────────────────────
        # 순압력(net = 매수점수% - 매도점수%) 기반으로만 판정
        # 단독 buy_pct/sell_pct 조건 제거 → 매수쏠림 방지
        net = buy_pct - sell_pct

        if net >= 25:
            prediction = "상승"
            strength   = "강" if net >= 45 else "약"
        elif net <= -25:
            prediction = "하락"
            strength   = "강" if net <= -45 else "약"
        else:
            prediction = "보합"
            strength   = "-"

        # ── 의견 불일치 지수 (Disagreement Score) ──────────────
        # 0.0 = 완전 일치(전원 한 방향), 1.0 = 완전 분열(3등분)
        # 허핀달-허쉬만 지수(HHI) 역산: disagreement = 1 - HHI
        # HHI = sum(share²), share = 각 행동의 비중
        buy_share  = buy_pct  / 100
        sell_share = sell_pct / 100
        hold_share = hold_pct / 100
        hhi = buy_share**2 + sell_share**2 + hold_share**2
        disagreement = round(1.0 - hhi, 3)  # 0=완전일치, ~0.667=완전분열

        # 평균 확신도
        conf_vals = [float(d.get("confidence", 0.5)) for d in decisions]
        confidence_avg = round(sum(conf_vals) / len(conf_vals), 3) if conf_vals else 0.5

        return {
            "prediction":       prediction,
            "strength":         strength,
            "buy_pressure":     round(buy_pct,  1),
            "sell_pressure":    round(sell_pct, 1),
            "hold_pressure":    round(hold_pct, 1),
            "net_pressure":     round(net, 1),
            "type_breakdown":   type_breakdown,
            "total_agents":     len(decisions),
            "disagreement":     disagreement,      # 0(일치)~0.667(분열)
            "confidence_avg":   confidence_avg,    # 에이전트 평균 확신도
        }