"""
파일 기반 결과 저장소 (JSON → db/ 폴더)
나중에 SQLite/PostgreSQL로 마이그레이션 용이하도록 인터페이스 분리

구조:
  db/
  ├── index.json              ← 전체 시뮬레이션 메타 인덱스
  ├── runs/
  │   └── {run_id}.json       ← 단일 실행 결과
  └── daily/
      └── {ticker}_{date}.json ← 날짜별 결과 (빠른 조회용)
"""
import json
import os
import uuid
from datetime import datetime

DB_DIR     = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR   = os.path.join(DB_DIR, "runs")
DAILY_DIR  = os.path.join(DB_DIR, "daily")
INDEX_PATH = os.path.join(DB_DIR, "index.json")

for d in [RUNS_DIR, DAILY_DIR]:
    os.makedirs(d, exist_ok=True)


def _load_index() -> list[dict]:
    if not os.path.exists(INDEX_PATH):
        return []
    with open(INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)

def _save_index(index: list[dict]):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2, default=str)


def save_run(daily_results: list[dict], corp: str, ticker: str, sector: str = "") -> str:
    if not daily_results:
        return ""

    run_id   = str(uuid.uuid4())[:8]
    dates    = [r.get("issue_date", "") for r in daily_results]
    valid    = [r for r in daily_results if "result" in r]
    evals_1d = [
        r["validation"]["evaluations"]["1d"]
        for r in valid
        if r.get("validation", {}).get("evaluations", {}).get("1d")
    ]
    accuracy = (
        sum(1 for e in evals_1d if e["is_correct"]) / len(evals_1d) * 100
        if evals_1d else None
    )

    run_data = {
        "run_id":        run_id,
        "corp":          corp,
        "ticker":        ticker,
        "sector":        sector,
        "start_date":    dates[0] if dates else "",
        "end_date":      dates[-1] if dates else "",
        "days":          len(daily_results),
        "accuracy_1d":   round(accuracy, 1) if accuracy is not None else None,
        "created_at":    datetime.now().isoformat(),
        "daily_results": daily_results,
    }

    with open(os.path.join(RUNS_DIR, f"{run_id}.json"), "w", encoding="utf-8") as f:
        json.dump(run_data, f, ensure_ascii=False, indent=2, default=str)

    for r in daily_results:
        date = r.get("issue_date", "")
        if not date:
            continue
        with open(os.path.join(DAILY_DIR, f"{ticker}_{date}.json"), "w", encoding="utf-8") as f:
            json.dump({**r, "run_id": run_id, "corp": corp, "sector": sector},
                      f, ensure_ascii=False, indent=2, default=str)

    index = [i for i in _load_index() if not (
        i["ticker"] == ticker and
        i["start_date"] == run_data["start_date"] and
        i["end_date"] == run_data["end_date"]
    )]
    index.append({
        "run_id":      run_id,
        "corp":        corp,
        "ticker":      ticker,
        "sector":      sector,
        "start_date":  run_data["start_date"],
        "end_date":    run_data["end_date"],
        "days":        run_data["days"],
        "accuracy_1d": run_data["accuracy_1d"],
        "created_at":  run_data["created_at"],
    })
    _save_index(sorted(index, key=lambda x: x["created_at"], reverse=True))

    print(f"[DB] 저장 완료: {corp} ({ticker}) / run_id={run_id} / {len(daily_results)}일")
    return run_id


def list_runs(ticker: str = None, sector: str = None, latest_only: bool = False) -> list[dict]:
    """
    인덱스 목록 반환.
    latest_only=True 이면 ticker당 가장 최근 실행 1개만 반환.
    대시보드·요약 뷰에서는 항상 latest_only=True 를 사용할 것.
    """
    index = _load_index()
    if ticker:
        index = [i for i in index if i["ticker"] == ticker]
    if sector:
        index = [i for i in index if i.get("sector") == sector]

    if latest_only:
        # ticker 기준으로 created_at 최신 1개만 유지
        seen: dict[str, dict] = {}
        for entry in sorted(index, key=lambda x: x["created_at"], reverse=True):
            t = entry["ticker"]
            if t not in seen:
                seen[t] = entry
        return list(seen.values())

    return index


def get_latest_run_per_ticker() -> list[dict]:
    """ticker별 최신 실행의 전체 run 데이터를 한 번에 로드해 반환."""
    latest_metas = list_runs(latest_only=True)
    results = []
    for meta in latest_metas:
        run = load_run(meta["run_id"])
        if run:
            results.append(run)
    return results


def load_run(run_id: str) -> dict | None:
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_all_daily(ticker: str = None) -> list[dict]:
    results = []
    for fname in sorted(os.listdir(DAILY_DIR)):
        if not fname.endswith(".json"):
            continue
        if ticker and not fname.startswith(f"{ticker}_"):
            continue
        with open(os.path.join(DAILY_DIR, fname), encoding="utf-8") as f:
            results.append(json.load(f))
    return results

def get_summary_stats() -> dict:
    index = _load_index()
    if not index:
        return {}
    tickers  = list({i["ticker"] for i in index})
    acc_vals = [i["accuracy_1d"] for i in index if i.get("accuracy_1d") is not None]
    return {
        "total_runs":    len(index),
        "total_tickers": len(tickers),
        "tickers":       tickers,
        "avg_accuracy":  round(sum(acc_vals) / len(acc_vals), 1) if acc_vals else None,
        "latest_run":    index[0]["created_at"] if index else None,
    }