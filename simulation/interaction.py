from config.settings import SOCIAL_CONTEXT_SAMPLE
import random


class InteractionEngine:
    """
    에이전트 간 상호작용 - 군집행동 구현
    이전 라운드의 다른 에이전트 결정을 요약해서
    다음 라운드 에이전트의 컨텍스트로 제공
    """

    def __init__(self, agents):
        self.agents = agents

    def build_social_context(self, prev_decisions: list[dict]) -> str:
        if not prev_decisions:
            return ""

        # 타입별 행동 집계
        type_counts: dict[str, dict[str, int]] = {}
        for d in prev_decisions:
            ptype  = d.get("persona_type", "unknown")
            action = d.get("action", "관망")
            if ptype not in type_counts:
                type_counts[ptype] = {"매수": 0, "매도": 0, "관망": 0}
            type_counts[ptype][action] = type_counts[ptype].get(action, 0) + 1

        total = {"매수": 0, "매도": 0, "관망": 0}
        for counts in type_counts.values():
            for action, cnt in counts.items():
                total[action] = total.get(action, 0) + cnt

        total_count = sum(total.values()) or 1
        buy_pct  = total["매수"]  / total_count * 100
        sell_pct = total["매도"]  / total_count * 100
        hold_pct = total["관망"]  / total_count * 100
        net      = buy_pct - sell_pct

        # 군중 압력 메시지 — 수치가 클수록 강한 신호로 표현
        if net >= 40:
            crowd_signal = f"🟢 강한 매수세 (매수 {buy_pct:.0f}% vs 매도 {sell_pct:.0f}%) — 시장이 상승에 베팅 중"
        elif net >= 20:
            crowd_signal = f"🟢 매수 우위 (매수 {buy_pct:.0f}% vs 매도 {sell_pct:.0f}%) — 낙관론 우세"
        elif net <= -40:
            crowd_signal = f"🔴 강한 매도세 (매도 {sell_pct:.0f}% vs 매수 {buy_pct:.0f}%) — 패닉셀 분위기"
        elif net <= -20:
            crowd_signal = f"🔴 매도 우위 (매도 {sell_pct:.0f}% vs 매수 {buy_pct:.0f}%) — 비관론 우세"
        elif hold_pct >= 60:
            crowd_signal = f"🟡 관망 지배 ({hold_pct:.0f}%) — 불확실성으로 눈치보기"
        else:
            crowd_signal = f"⚪ 혼조세 (매수 {buy_pct:.0f}% / 매도 {sell_pct:.0f}% / 관망 {hold_pct:.0f}%)"

        # 타입별 요약 — 기관/단타는 신호로서 강조
        type_labels = {
            "retail":         "개인투자자",
            "institutional":  "기관투자자",
            "day_trader":     "단타트레이더",
            "value_investor": "가치투자자",
        }
        type_lines = []
        for ptype, counts in type_counts.items():
            label    = type_labels.get(ptype, ptype)
            dominant = max(counts, key=counts.get)
            total_t  = sum(counts.values())
            pct      = counts[dominant] / total_t * 100
            # 기관/단타가 강한 방향 시 강조
            emphasis = " ⚠️ 강한 신호" if (ptype in ("institutional","day_trader") and dominant != "관망" and pct >= 60) else ""
            type_lines.append(f"  - {label} ({total_t}명): '{dominant}' {pct:.0f}%{emphasis}")

        # 샘플 코멘트
        sample   = random.sample(prev_decisions, min(SOCIAL_CONTEXT_SAMPLE, len(prev_decisions)))
        comments = [
            f"  [{type_labels.get(d.get('persona_type',''), '투자자')}] \"{d.get('reason','')}\""
            for d in sample if d.get("reason")
        ]

        return (
            f"=== 직전 라운드 시장 참여자 반응 ({total_count}명) ===\n"
            f"{crowd_signal}\n\n"
            f"유형별 행동:\n" + "\n".join(type_lines) + "\n\n"
            f"주요 의견 샘플:\n" + "\n".join(comments) + "\n\n"
            f"※ 위 군중 반응을 참고해 당신의 결정을 재검토하세요. "
            f"군중과 같은 방향이면 확신도를 높이고, 반대 방향이면 근거를 명확히 하세요."
        )
