class SimulationValidator:
    """
    시뮬레이션 예측 vs 실제 주가 비교 검증
    1일 / 5일(1주) / 20일(1달) 3구간 평가
    market_ctx에 actual_1d_pct / actual_5d_pct / actual_20d_pct 포함되어 있으면
    API 재호출 없이 바로 검증
    """

    def validate(self, sim_result: dict, ticker: str, issue_date: str, market_ctx: dict = None) -> dict:
        result = sim_result["result"]
        prediction = result["prediction"]  # 상승/하락/보합

        # market_ctx에서 실제 등락률 추출
        changes = {}
        if market_ctx:
            if market_ctx.get("actual_1d_pct") is not None:
                changes["1d"] = market_ctx["actual_1d_pct"]
            if market_ctx.get("actual_5d_pct") is not None:
                changes["5d"] = market_ctx["actual_5d_pct"]
            if market_ctx.get("actual_20d_pct") is not None:
                changes["20d"] = market_ctx["actual_20d_pct"]

        if not changes:
            return {"error": "주가 데이터 없음 — market_ctx에 actual_*_pct 값 필요"}

        evaluations = {}
        for period, change_pct in changes.items():
            actual_direction = (
                "상승" if change_pct > 1.0
                else "하락" if change_pct < -1.0
                else "보합"
            )
            evaluations[period] = {
                "predicted":        prediction,
                "actual_direction": actual_direction,
                "actual_change_pct": change_pct,
                "is_correct":       prediction == actual_direction,
            }

        correct_count = sum(1 for e in evaluations.values() if e["is_correct"])
        accuracy = correct_count / len(evaluations) * 100 if evaluations else 0

        return {
            "ticker":         ticker,
            "issue_date":     issue_date,
            "prediction":     prediction,
            "buy_pressure":   result["buy_pressure"],
            "sell_pressure":  result["sell_pressure"],
            "evaluations":    evaluations,
            "accuracy_pct":   round(accuracy, 1),
            "correct_count":  correct_count,
            "total_periods":  len(evaluations),
            "base_price":     market_ctx.get("current_price") if market_ctx else None,
        }

    @staticmethod
    def summarize_cases(validations: list[dict]) -> dict:
        """여러 케이스의 정확도 종합 요약 (대시보드용)"""
        if not validations:
            return {}

        valid = [v for v in validations if "error" not in v]
        if not valid:
            return {}

        total_accuracy = sum(v["accuracy_pct"] for v in valid) / len(valid)

        period_accuracy = {}
        for period in ["1d", "5d", "20d"]:
            correct = sum(
                1 for v in valid
                if v.get("evaluations", {}).get(period, {}).get("is_correct", False)
            )
            period_accuracy[period] = round(correct / len(valid) * 100, 1)

        return {
            "total_cases":     len(valid),
            "avg_accuracy_pct": round(total_accuracy, 1),
            "period_accuracy": period_accuracy,
        }
