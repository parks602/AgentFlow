"""
DB → HTML 리포트 자동 생성
사용법:
  python generate_report.py                    # 전체 종목 종합 리포트
  python generate_report.py --ticker 000660   # 특정 종목만
"""
import argparse, json, os
from datetime import datetime
from db.store import list_runs, load_run, get_summary_stats

def pred_col(p):
    return {"상승":"#00e676","하락":"#ff4444"}.get(p,"#ffa726")

def ev_cell(ev):
    if not ev: return "<span style='color:#333'>N/A</span>"
    c = ev.get("actual_change_pct",0)
    ok = ev.get("is_correct",False)
    col = "#00e676" if ok else "#ff4444"
    return f"<span style='color:{col}'>{c:+.1f}% {'✓' if ok else '✗'}</span>"

def generate(runs_data: list[dict], output_path: str):
    stats   = get_summary_stats()
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_runs  = len(runs_data)

    # 종목별 카드
    cards_html = ""
    all_rows   = ""
    chart_datasets = []

    for run in runs_data:
        corp   = run["corp"]
        ticker = run["ticker"]
        daily  = run.get("daily_results", [])
        valid  = [d for d in daily if "result" in d]
        if not valid: continue

        last    = valid[-1]["result"]
        evals   = [d["validation"]["evaluations"]["1d"]
                   for d in valid
                   if d.get("validation",{}).get("evaluations",{}).get("1d")]
        acc     = sum(1 for e in evals if e["is_correct"])/len(evals)*100 if evals else 0
        pc      = pred_col(last["prediction"])
        acc_col = "#00e676" if acc>=60 else "#ff4444" if acc<40 else "#ffa726"

        cards_html += f"""
        <div class="stock-card">
          <div class="stock-header">
            <span class="ticker">{ticker}</span>
            <span class="corp">{corp}</span>
            <span class="sector">{run.get('sector','')}</span>
          </div>
          <div class="pred" style="color:{pc}">{last['prediction']}</div>
          <div class="metrics-row">
            <span class="m"><span class="up">▲</span> {last['buy_pressure']:.0f}%</span>
            <span class="m"><span class="down">▼</span> {last['sell_pressure']:.0f}%</span>
            <span class="m" style="color:{acc_col}">✓ {acc:.0f}%</span>
          </div>
        </div>"""

        dates  = [d["issue_date"] for d in valid]
        net_p  = [d["result"].get("net_pressure",0) for d in valid]
        chart_datasets.append({"label": corp, "dates": dates, "net": net_p})

        for d in valid:
            res = d["result"]
            evs = d.get("validation",{}).get("evaluations",{})
            all_rows += f"""<tr>
              <td style='color:#5a7a9a'>{ticker}</td>
              <td>{corp}</td>
              <td style='color:#5a7a9a'>{d['issue_date']}</td>
              <td>{d.get('seed',{}).get('issue_type','')}</td>
              <td style='color:{pred_col(res["prediction"])};font-weight:600'>{res['prediction']}</td>
              <td style='color:{"#00e676" if res.get("net_pressure",0)>=0 else "#ff4444"};font-family:monospace'>{res.get("net_pressure",0):+.1f}%</td>
              <td>{ev_cell(evs.get('1d'))}</td>
              <td>{ev_cell(evs.get('5d'))}</td>
              <td>{ev_cell(evs.get('20d'))}</td>
            </tr>"""

    chart_js = f"const chartData = {json.dumps(chart_datasets)};"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>AgentFlow — 종합 리포트</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+KR:wght@300;400;600&display=swap" rel="stylesheet">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#070b14; color:#c8d4e8; font-family:'Noto Sans KR',sans-serif; padding:40px 48px; }}
.header {{ border-bottom:1px solid #1a2a45; padding-bottom:20px; margin-bottom:32px; }}
.header h1 {{ font-family:'IBM Plex Mono',monospace; font-size:1.5rem; color:#e0e8f8; }}
.header .meta {{ font-size:0.75rem; color:#3a6ea8; margin-top:6px; letter-spacing:2px; text-transform:uppercase; }}
.summary-row {{ display:flex; gap:16px; margin-bottom:36px; }}
.s-card {{ flex:1; background:#0d1526; border:1px solid #1a2a45; border-radius:6px; padding:16px; text-align:center; }}
.s-val {{ font-family:'IBM Plex Mono',monospace; font-size:1.6rem; font-weight:600; }}
.s-lbl {{ font-size:0.65rem; color:#3a6ea8; text-transform:uppercase; letter-spacing:2px; margin-top:4px; }}
.sec {{ margin-bottom:40px; }}
.sec h2 {{ font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#3a6ea8; text-transform:uppercase; letter-spacing:3px; border-bottom:1px solid #1a2a45; padding-bottom:6px; margin-bottom:16px; }}
.stock-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }}
.stock-card {{ background:#0d1526; border:1px solid #1a2a45; border-radius:6px; padding:14px; }}
.stock-header {{ display:flex; gap:8px; align-items:baseline; margin-bottom:8px; }}
.ticker {{ font-family:'IBM Plex Mono',monospace; font-size:0.85rem; color:#e0e8f8; }}
.corp {{ font-size:0.8rem; color:#7a8ba8; }}
.sector {{ font-size:0.65rem; color:#3a6ea8; margin-left:auto; }}
.pred {{ font-family:'IBM Plex Mono',monospace; font-size:1.5rem; font-weight:600; margin-bottom:8px; }}
.metrics-row {{ display:flex; gap:10px; font-size:0.75rem; }}
.up {{ color:#00e676; }} .down {{ color:#ff4444; }}
.chart-box {{ background:#0d1526; border:1px solid #1a2a45; border-radius:6px; padding:20px; }}
table {{ width:100%; border-collapse:collapse; font-size:0.82rem; }}
th {{ background:#0d1526; color:#3a6ea8; font-family:'IBM Plex Mono',monospace; font-size:0.62rem; text-transform:uppercase; letter-spacing:2px; padding:10px 14px; text-align:left; border-bottom:1px solid #1a2a45; }}
td {{ padding:10px 14px; border-bottom:1px solid #0d1526; }}
tr:hover td {{ background:#0d1526; }}
.footer {{ margin-top:60px; border-top:1px solid #1a2a45; padding-top:16px; text-align:center; font-size:0.72rem; color:#1a3050; }}
</style>
</head>
<body>
<div class="header">
  <h1>AgentFlow &nbsp;<span style='color:#1a3a60'>/</span>&nbsp; 종합 시뮬레이션 리포트</h1>
  <div class="meta">Multi-Agent Stock Market Simulation &nbsp;·&nbsp; {now} &nbsp;·&nbsp; {n_runs} runs</div>
</div>

<div class="summary-row">
  <div class="s-card"><div class="s-val" style="color:#e0e8f8">{stats.get('total_tickers',0)}</div><div class="s-lbl">분석 종목</div></div>
  <div class="s-card"><div class="s-val" style="color:#e0e8f8">{stats.get('total_runs',0)}</div><div class="s-lbl">총 시뮬레이션</div></div>
  <div class="s-card"><div class="s-val" style="color:{'#00e676' if (stats.get('avg_accuracy') or 0)>=60 else '#ff4444'}">{stats.get('avg_accuracy') or 'N/A'}%</div><div class="s-lbl">평균 1일 정확도</div></div>
</div>

<div class="sec">
  <h2>종목별 최신 예측</h2>
  <div class="stock-grid">{cards_html}</div>
</div>

<div class="sec">
  <h2>종목별 순압력 추이</h2>
  <div class="chart-box"><canvas id="netChart" height="80"></canvas></div>
</div>

<div class="sec">
  <h2>전체 시뮬레이션 결과</h2>
  <table>
    <thead><tr><th>티커</th><th>종목</th><th>날짜</th><th>이슈</th><th>예측</th><th>순압력</th><th>1일</th><th>5일</th><th>20일</th></tr></thead>
    <tbody>{all_rows}</tbody>
  </table>
</div>

<div class="footer">AgentFlow — Multi-Agent Stock Market Simulation · Powered by LLM</div>

<script>
{chart_js}
const COLORS = ['#00b4d8','#00e676','#ffa726','#ff4444','#b388ff','#ff6eb4','#64ffda','#ffee58','#80cbc4','#ce93d8'];
const allDates = [...new Set(chartData.flatMap(d => d.dates))].sort();
const datasets = chartData.map((d, i) => ({{
  label: d.label,
  data: allDates.map(date => {{
    const idx = d.dates.indexOf(date);
    return idx >= 0 ? d.net[idx] : null;
  }}),
  borderColor: COLORS[i % COLORS.length],
  backgroundColor: COLORS[i % COLORS.length] + '22',
  borderWidth: 2, pointRadius: 4,
  spanGaps: true, tension: 0.3,
}}));

new Chart(document.getElementById('netChart'), {{
  type: 'line',
  data: {{ labels: allDates, datasets }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color:'#7a8ba8', font:{{ family:'IBM Plex Mono', size:11 }} }} }} }},
    scales: {{
      x: {{ ticks:{{ color:'#4a6080' }}, grid:{{ color:'#111c2e' }} }},
      y: {{ ticks:{{ color:'#4a6080' }}, grid:{{ color:'#111c2e' }}, title:{{ display:true, text:'순압력 (%)', color:'#3a6ea8' }} }}
    }}
  }}
}});
</script>
</body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"리포트 생성 완료: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="특정 종목코드만")
    args = parser.parse_args()

    runs_meta = list_runs(ticker=args.ticker)
    if not runs_meta:
        print("DB에 데이터 없음. run_multi_stock.py 먼저 실행")
        exit(1)

    runs_data = [r for m in runs_meta if (r := load_run(m["run_id"]))]
    out = f"report_{'all' if not args.ticker else args.ticker}_{datetime.now().strftime('%Y%m%d')}.html"
    generate(runs_data, out)
