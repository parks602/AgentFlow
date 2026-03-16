"""
배치 백테스팅 스크립트
여러 종목/날짜를 순차 실행하고 종합 정확도를 출력

사용법:
  python batch_test.py                  # 기본 케이스 실행
  python batch_test.py --cases my_cases.json  # 커스텀 케이스 파일
"""
import argparse
import json
import time
from main import run_simulation
from evaluation.validator import SimulationValidator

# ── 기본 테스트 케이스 ─────────────────────────────────────────
# 이슈가 명확하고 주가 반응이 드라마틱한 날짜 선정
DEFAULT_CASES = [
    {
        "corp": "SK하이닉스",
        "ticker": "000660",
        "date": "2023-10-26",
        "memo": "3Q 실적발표 — 어닝쇼크, 당일 -5.88%",
    },
    {
        "corp": "SK하이닉스",
        "ticker": "000660",
        "date": "2024-01-25",
        "memo": "4Q 흑자전환 발표",
    },
    {
        "corp": "삼성전자",
        "ticker": "005930",
        "date": "2024-04-05",
        "memo": "1Q 잠정실적 — 반도체 흑자전환",
    },
]


def run_batch(cases: list[dict], delay_sec: float = 2.0) -> list[dict]:
    results = []

    for i, case in enumerate(cases, 1):
        print(f"\n{'#'*60}")
        print(f"# 케이스 {i}/{len(cases)}: {case['corp']} / {case['date']}")
        print(f"# 메모: {case.get('memo', '')}")
        print(f"{'#'*60}")

        try:
            output = run_simulation(case["corp"], case["ticker"], case["date"])
            output["memo"] = case.get("memo", "")
            results.append(output)
        except Exception as e:
            print(f"[ERROR] 케이스 실패: {e}")
            results.append({
                "corp_name": case["corp"],
                "ticker": case["ticker"],
                "issue_date": case["date"],
                "memo": case.get("memo", ""),
                "error": str(e),
            })

        if i < len(cases):
            print(f"\n[대기] {delay_sec}초 후 다음 케이스 실행...")
            time.sleep(delay_sec)

    return results


def print_summary(results: list[dict]):
    valid = [r for r in results if "validation" in r and "error" not in r["validation"]]

    print(f"\n{'='*60}")
    print(" 배치 테스트 종합 결과")
    print(f"{'='*60}")
    print(f"  총 케이스: {len(results)}개 / 성공: {len(valid)}개\n")

    if not valid:
        print("  검증 가능한 결과 없음")
        return

    # 케이스별 요약
    print(f"  {'종목':<12} {'날짜':<12} {'예측':<6} {'1일':>6} {'1주':>6} {'1달':>6} {'정확도':>6}  메모")
    print(f"  {'-'*80}")

    validations = []
    for r in valid:
        v = r["validation"]
        pred = r["result"]["prediction"]
        evs = v.get("evaluations", {})

        def ev_str(period):
            e = evs.get(period)
            if not e:
                return "  N/A"
            mark = "✓" if e["is_correct"] else "✗"
            return f"{e['actual_change_pct']:+.1f}%{mark}"

        print(f"  {r['corp_name']:<12} {r['issue_date']:<12} {pred:<6} "
              f"{ev_str('1d'):>7} {ev_str('5d'):>7} {ev_str('20d'):>7} "
              f"{v['accuracy_pct']:>5.0f}%  {r.get('memo','')[:20]}")

        validations.append(v)

    # 전체 정확도
    summary = SimulationValidator.summarize_cases(validations)
    print(f"\n  {'='*40}")
    print(f"  전체 평균 정확도: {summary['avg_accuracy_pct']:.1f}%")
    print(f"  구간별 정확도:")
    print(f"    1일 후:  {summary['period_accuracy'].get('1d', 0):.1f}%")
    print(f"    1주 후:  {summary['period_accuracy'].get('5d', 0):.1f}%")
    print(f"    1달 후:  {summary['period_accuracy'].get('20d', 0):.1f}%")

    # JSON 저장
    batch_output = {
        "summary": summary,
        "cases": results,
    }
    with open("batch_result.json", "w", encoding="utf-8") as f:
        json.dump(batch_output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  전체 결과 저장: batch_result.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentFlow 배치 백테스팅")
    parser.add_argument("--cases", help="케이스 JSON 파일 경로 (없으면 기본 케이스 사용)")
    parser.add_argument("--delay", type=float, default=2.0, help="케이스 간 대기 시간(초)")
    args = parser.parse_args()

    if args.cases:
        with open(args.cases, encoding="utf-8") as f:
            cases = json.load(f)
        print(f"[배치] 커스텀 케이스 {len(cases)}개 로드")
    else:
        cases = DEFAULT_CASES
        print(f"[배치] 기본 케이스 {len(cases)}개 실행")

    results = run_batch(cases, delay_sec=args.delay)
    print_summary(results)
