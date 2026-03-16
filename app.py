"""
AgentFlow 멀티 종목 대시보드
실행: streamlit run dashboard/app.py
"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # 상대경로(db/, stocks_config.json 등) 기준점 통일

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from collections import defaultdict
from db.store import list_runs, load_run, load_all_daily, get_summary_stats, get_latest_run_per_ticker

st.set_page_config(page_title="AgentFlow", page_icon="📈", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+KR:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: #FFFFFF; color: #c8d4e8; }
.metric-card { background: #0d1526; border: 1px solid #1a2a45; border-radius: 8px; padding: 18px; text-align: center; }
.metric-val { font-family: 'IBM Plex Mono', monospace; font-size: 1.8rem; font-weight: 600; }
.metric-lbl { font-size: 0.68rem; color: #3a6ea8; text-transform: uppercase; letter-spacing: 2px; margin-top: 4px; }
.sec-title { font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: #3a6ea8; text-transform: uppercase; letter-spacing: 3px; border-bottom: 1px solid #1a2a45; padding-bottom: 6px; margin: 24px 0 16px; }
.up { color: #00e676; } .down { color: #ff4444; } .hold { color: #ffa726; }
</style>
""", unsafe_allow_html=True)

P = dict(paper_bgcolor="#D3D3D3", plot_bgcolor="#0d1526",
         font=dict(color="#c8d4e8", family="IBM Plex Mono"),
         margin=dict(l=40, r=20, t=36, b=36))

def pred_col(p):
    return "#00e676" if p=="상승" else "#ff4444" if p=="하락" else "#ffa726"

# ── 사이드바 ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📈 AgentFlow")
    stats = get_summary_stats()
    if not stats:
        st.warning("DB 비어있음\n`python run_multi_stock.py` 먼저 실행")
        st.stop()

    st.markdown(f"**{stats['total_tickers']}종목 / {stats['total_runs']}runs**")
    if stats.get("avg_accuracy"):
        st.markdown(f"평균 정확도: **{stats['avg_accuracy']}%**")

    st.divider()
    view = st.radio("보기 모드", ["📊 전체 종목 비교", "🔍 종목 상세", "📈 백테스트 분석", "🧠 시뮬레이션 흐름"])

    if view == "🔍 종목 상세" or view == "🧠 시뮬레이션 흐름":
        runs  = list_runs(latest_only=True)
        corps = {r["corp"]: r for r in runs}
        selected_corp = st.selectbox("종목 선택", list(corps.keys()))
        selected_run  = corps[selected_corp]

# ── 전체 종목 비교 뷰 ────────────────────────────────────────
if view == "📊 전체 종목 비교":
    st.markdown("# AgentFlow — 전체 종목 분석")

    # ticker당 최신 실행 1건만 로드 (과거 재실행 데이터 제외)
    runs = get_latest_run_per_ticker()
    if not runs:
        st.info("데이터 없음")
        st.stop()

    # 요약 테이블
    st.markdown("<div class='sec-title'>종목별 최신 예측 & 정확도</div>", unsafe_allow_html=True)

    rows = []
    for run in runs:
        daily = run.get("daily_results", [])
        valid = [d for d in daily if "result" in d]
        if not valid:
            continue
        last = valid[-1]
        res  = last["result"]
        evs  = last.get("validation", {}).get("evaluations", {})
        rows.append({
            "종목":      run["corp"],
            "티커":      run["ticker"],
            "섹터":      run.get("sector", ""),
            "최신예측":  res["prediction"],
            "매수%":     res["buy_pressure"],
            "매도%":     res["sell_pressure"],
            "순압력":    res.get("net_pressure", 0),
            "1일정확도": run.get("accuracy_1d"),
            "기간":      f"{run['start_date']} ~ {run['end_date']}",
        })

    df = pd.DataFrame(rows)

    # 종목별 예측 색상 바 차트
    fig_bar = go.Figure()
    for _, row in df.iterrows():
        fig_bar.add_trace(go.Bar(
            name=row["종목"],
            x=[row["종목"]],
            y=[row["순압력"]],
            marker_color=pred_col(row["최신예측"]),
            text=f"{row['최신예측']}<br>{row['순압력']:+.1f}%",
            textposition="outside",
        ))
    fig_bar.update_layout(
        title="종목별 순압력 (매수 - 매도)",
        showlegend=False, height=320,
        yaxis=dict(gridcolor="#1a2a45", zeroline=True, zerolinecolor="#3a6ea8"),
        **P,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # 정확도 비교
    acc_df = df.dropna(subset=["1일정확도"]).sort_values("1일정확도", ascending=True)
    if not acc_df.empty:
        fig_acc = go.Figure(go.Bar(
            x=acc_df["1일정확도"],
            y=acc_df["종목"],
            orientation="h",
            marker=dict(
                color=["#00e676" if v >= 60 else "#ff4444" if v < 40 else "#ffa726"
                       for v in acc_df["1일정확도"]],
                line=dict(width=0),
            ),
            text=[f"{v:.0f}%" for v in acc_df["1일정확도"]],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono", size=12),
            width=0.55,   # 바 두께 — 간격 확보
        ))
        fig_acc.update_layout(
            title=dict(text="종목별 1일 예측 정확도", font=dict(size=13)),
            height=max(280, len(acc_df) * 40 + 80),
            xaxis=dict(
                range=[0, 115],
                gridcolor="#1a2a45",
                zeroline=True,
                zerolinecolor="#3a6ea8",
                zerolinewidth=2,
                ticksuffix="%",
                fixedrange=True,
            ),
            yaxis=dict(
                gridcolor="#1a2a45",
                fixedrange=True,
            ),
            bargap=0.35,   # 바 사이 간격
            **P,
        )
        st.plotly_chart(fig_acc, use_container_width=True)

    # 섹터별 분포
    st.markdown("<div class='sec-title'>섹터별 심리 분포</div>", unsafe_allow_html=True)
    sector_data = defaultdict(lambda: {"상승": 0, "하락": 0, "보합": 0})
    for _, row in df.iterrows():
        sector_data[row["섹터"]][row["최신예측"]] += 1

    sectors = list(sector_data.keys())
    fig_sec = go.Figure()
    for pred, color in [("상승", "#00e676"), ("보합", "#ffa726"), ("하락", "#ff4444")]:
        fig_sec.add_trace(go.Bar(
            name=pred, x=sectors,
            y=[sector_data[s][pred] for s in sectors],
            marker_color=color, opacity=0.85,
        ))
    fig_sec.update_layout(
        barmode="stack", height=280,
        xaxis=dict(gridcolor="#1a2a45"),
        yaxis=dict(gridcolor="#1a2a45"),
        **P,
    )
    st.plotly_chart(fig_sec, use_container_width=True)

    # ── 예측 vs 실제 종합 테이블 ───────────────────────────────
    st.markdown("<div class='sec-title'>예측 vs 실제 종합 테이블</div>", unsafe_allow_html=True)

    all_rows = []
    for run in runs:
        for d in run.get("daily_results", []):
            if "result" not in d:
                continue
            res  = d["result"]
            evs  = d.get("validation", {}).get("evaluations", {})
            seed = d.get("seed", {})

            def get_ev(period):
                e = evs.get(period, {})
                return e.get("actual_change_pct"), e.get("actual_direction"), e.get("is_correct")

            chg_1d,  dir_1d,  ok_1d  = get_ev("1d")
            chg_5d,  dir_5d,  ok_5d  = get_ev("5d")
            chg_20d, dir_20d, ok_20d = get_ev("20d")

            all_rows.append({
                "_종목":       run["corp"],
                "_날짜":       d["issue_date"],
                "_이슈":       seed.get("issue_type", ""),
                "_AI예측":     res["prediction"],
                "_매수%":      res["buy_pressure"],
                "_매도%":      res["sell_pressure"],
                "_순압력":     res.get("net_pressure", 0),
                "_1일실제등락": chg_1d,
                "_1일실제방향": dir_1d,
                "_1일판정":    ok_1d,
                "_5일실제등락": chg_5d,
                "_5일실제방향": dir_5d,
                "_5일판정":    ok_5d,
                "_20일실제등락": chg_20d,
                "_20일실제방향": dir_20d,
                "_20일판정":   ok_20d,
            })

    if all_rows:
        raw_df = pd.DataFrame(all_rows).sort_values(["_종목", "_날짜"])

        # ── 필터 ──────────────────────────────────────────────
        fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
        with fc1:
            corps_opt = ["전체"] + sorted(raw_df["_종목"].unique().tolist())
            sel_corp  = st.selectbox("종목", corps_opt, key="gf_corp")
        with fc2:
            sel_pred  = st.selectbox("AI예측", ["전체","상승","하락","보합"], key="gf_pred")
        with fc3:
            sel_judge = st.selectbox("1일 판정", ["전체","✓ 맞음","✗ 틀림"], key="gf_judge")
        with fc4:
            sel_period = st.selectbox("비교 기간", ["1일","5일","20일"], key="gf_period")

        mask = pd.Series([True] * len(raw_df), index=raw_df.index)
        if sel_corp  != "전체": mask &= raw_df["_종목"]   == sel_corp
        if sel_pred  != "전체": mask &= raw_df["_AI예측"] == sel_pred
        if sel_judge == "✓ 맞음": mask &= raw_df["_1일판정"] == True
        if sel_judge == "✗ 틀림": mask &= raw_df["_1일판정"] == False
        filtered = raw_df[mask].copy()

        # ── 정확도 요약 메트릭 ───────────────────────────────
        has_judge = filtered["_1일판정"].notna()
        judged    = filtered[has_judge]
        total_j   = len(judged)
        correct_j = int((judged["_1일판정"] == True).sum()) if total_j else 0
        acc       = correct_j / total_j * 100 if total_j else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("표시 행",    len(filtered))
        m2.metric("판정 가능",  total_j)
        m3.metric("맞음",       correct_j)
        m4.metric("틀림",       total_j - correct_j)
        m5.metric("1일 정확도", f"{acc:.0f}%" if total_j else "—",
                  delta=f"{'▲' if acc>=60 else '▼'} {acc:.0f}%" if total_j else None)

        # ── 표시용 df 구성 ────────────────────────────────────
        period_key = {"1일": "1d", "5일": "5d", "20일": "20d"}[sel_period]
        chg_col  = f"_{sel_period}실제등락"
        dir_col  = f"_{sel_period}실제방향"
        ok_col   = f"_{sel_period}판정"

        def fmt_pct(v):
            if v is None: return "—"
            return f"{v:+.2f}%"

        def fmt_judge(v):
            if v is True:  return "✓ 맞음"
            if v is False: return "✗ 틀림"
            return "—"

        def fmt_pred(v):
            return {"상승": "▲ 상승", "하락": "▼ 하락", "보합": "━ 보합"}.get(v, v)

        def fmt_dir(v):
            if v is None: return "—"
            return {"상승": "▲ 상승", "하락": "▼ 하락", "보합": "━ 보합"}.get(v, v)

        show_df = pd.DataFrame({
            "종목":          filtered["_종목"],
            "날짜":          filtered["_날짜"],
            "이슈유형":      filtered["_이슈"],
            "AI 예측":       filtered["_AI예측"].apply(fmt_pred),
            "매수 압력":     filtered["_매수%"].apply(lambda x: f"{x:.1f}%"),
            "매도 압력":     filtered["_매도%"].apply(lambda x: f"{x:.1f}%"),
            "순압력":        filtered["_순압력"].apply(lambda x: f"{x:+.1f}%"),
            f"{sel_period} 실제 등락": filtered[chg_col].apply(fmt_pct),
            f"{sel_period} 실제 방향": filtered[dir_col].apply(fmt_dir),
            f"{sel_period} 판정":      filtered[ok_col].apply(fmt_judge),
        }).reset_index(drop=True)

        def style_table(val):
            s = val
            if s in ("✓ 맞음",):        return "color:#00e676; font-weight:700"
            if s in ("✗ 틀림",):        return "color:#ff4444; font-weight:700"
            if s in ("▲ 상승",):        return "color:#00e676; font-weight:600"
            if s in ("▼ 하락",):        return "color:#ff4444; font-weight:600"
            if s in ("━ 보합",):        return "color:#ffa726; font-weight:600"
            if isinstance(s, str) and s.startswith("+"): return "color:#00e676; font-family:monospace"
            if isinstance(s, str) and s.startswith("-"): return "color:#ff4444; font-family:monospace"
            return "font-family:monospace"

        st.dataframe(
            show_df.style.applymap(style_table),
            use_container_width=True,
            height=460,
        )

    # 전체 테이블 (기존 간소화)
    st.markdown("<div class='sec-title'>상세 테이블</div>", unsafe_allow_html=True)
    def color_pred(val):
        if val == "상승": return "color: #00e676"
        if val == "하락": return "color: #ff4444"
        return "color: #ffa726"
    def color_acc(val):
        if val is None: return ""
        return "color: #00e676" if val >= 60 else "color: #ff4444" if val < 40 else "color: #ffa726"

    st.dataframe(
        df.style
          .applymap(color_pred, subset=["최신예측"])
          .applymap(color_acc, subset=["1일정확도"]),
        use_container_width=True, height=350,
    )

# ── 종목 상세 뷰 ─────────────────────────────────────────────
elif view == "🔍 종목 상세":
    run = load_run(selected_run["run_id"])
    if not run:
        st.error("데이터 없음")
        st.stop()

    daily  = run.get("daily_results", [])
    valid  = [d for d in daily if "result" in d]
    corp   = run["corp"]
    ticker = run["ticker"]

    st.markdown(f"# {corp} `{ticker}` 상세 분석")

    # 메트릭
    last     = valid[-1]["result"] if valid else {}
    evals_1d = [d["validation"]["evaluations"]["1d"]
                for d in valid
                if d.get("validation",{}).get("evaluations",{}).get("1d")]
    accuracy = sum(1 for e in evals_1d if e["is_correct"]) / len(evals_1d) * 100 if evals_1d else 0

    # disagreement / confidence_avg (신규 필드, 구 데이터엔 없을 수 있음)
    disagree_val  = last.get("disagreement", None)
    conf_avg_val  = last.get("confidence_avg", None)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    for col, val, lbl, cls in [
        (c1, last.get("prediction","—"), "최신 예측", "up" if last.get("prediction")=="상승" else "down" if last.get("prediction")=="하락" else "hold"),
        (c2, f"{last.get('buy_pressure',0):.1f}%",  "매수 압력", "up"),
        (c3, f"{last.get('sell_pressure',0):.1f}%", "매도 압력", "down"),
        (c4, f"{accuracy:.0f}%", "1일 정확도", "up" if accuracy>=60 else "down" if accuracy<40 else "hold"),
        (c5, f"{disagree_val:.2f}" if disagree_val is not None else "—",
             "불일치 지수", "down" if (disagree_val or 0) >= 0.45 else "hold" if (disagree_val or 0) >= 0.3 else "up"),
        (c6, f"{conf_avg_val:.2f}" if conf_avg_val is not None else "—",
             "평균 확신도", "up" if (conf_avg_val or 0) >= 0.65 else "down" if (conf_avg_val or 0) < 0.5 else "hold"),
    ]:
        col.markdown(f"<div class='metric-card'><div class='metric-val {cls}'>{val}</div><div class='metric-lbl'>{lbl}</div></div>", unsafe_allow_html=True)

    # ── 4번: 불일치 경고 배너 ────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if disagree_val is not None:
        if disagree_val >= 0.45:
            st.markdown(
                f"<div style='background:#2a1a0d; border:1px solid #ff8c00; border-radius:6px; "
                f"padding:10px 16px; font-size:0.85rem; color:#ffa726;'>"
                f"⚠️ <b>높은 의견 불일치 (Disagreement: {disagree_val:.2f})</b> — "
                f"에이전트 간 견해가 크게 갈립니다. 이 예측의 신뢰도가 낮을 수 있습니다.</div>",
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)
        elif disagree_val >= 0.3:
            st.markdown(
                f"<div style='background:#1a1a0d; border:1px solid #5a5a00; border-radius:6px; "
                f"padding:10px 16px; font-size:0.85rem; color:#c8c840;'>"
                f"ℹ️ <b>중간 수준의 불일치 (Disagreement: {disagree_val:.2f})</b> — "
                f"소수 의견이 존재합니다.</div>",
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)

    # ── 씨드 흐름 시각화 ────────────────────────────────────
    st.markdown("<div class='sec-title'>씨드 흐름 — 날짜별 시장 신호 변화</div>", unsafe_allow_html=True)

    # 씨드 데이터 수집
    seed_dates      = [d["issue_date"] for d in valid]
    seed_sentiments = [d.get("seed", {}).get("sentiment", "neutral") for d in valid]
    seed_impacts    = [d.get("seed", {}).get("impact_level", "medium") for d in valid]
    seed_issues     = [d.get("seed", {}).get("issue_type", "기타") or "기타" for d in valid]
    seed_summaries  = [d.get("seed", {}).get("summary", "") for d in valid]
    seed_kp         = [d.get("seed", {}).get("key_points", []) for d in valid]

    # sentiment → 수치 매핑
    SENT_NUM  = {"positive": 1, "neutral": 0, "negative": -1}
    SENT_COL  = {"positive": "#00e676", "neutral": "#ffa726", "negative": "#ff4444"}
    SENT_LBL  = {"positive": "긍정", "neutral": "중립", "negative": "부정"}
    IMPACT_NUM = {"high": 3, "medium": 2, "low": 1}
    IMPACT_COL = {"high": "#ff4444", "medium": "#ffa726", "low": "#7ecfff"}

    sent_nums   = [SENT_NUM.get(s, 0) for s in seed_sentiments]
    impact_nums = [IMPACT_NUM.get(i, 2) for i in seed_impacts]

    fig_seed = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.4, 0.3, 0.3],
        vertical_spacing=0.06,
        subplot_titles=["감성(Sentiment) 흐름", "영향도(Impact) 흐름", "이슈 유형 분포"],
    )

    # ── 행1: 감성 라인 + 영역 ──────────────────────────────
    fig_seed.add_trace(go.Scatter(
        x=seed_dates, y=sent_nums,
        mode="lines+markers+text",
        line=dict(color="#c8d4e8", width=2),
        marker=dict(
            size=14,
            color=[SENT_COL.get(s, "#ffa726") for s in seed_sentiments],
            line=dict(width=2, color="#ffffff"),
        ),
        fill="tozeroy",
        fillcolor="rgba(200,212,232,0.06)",
        text=[SENT_LBL.get(s, s) for s in seed_sentiments],
        textposition="top center",
        textfont=dict(family="IBM Plex Mono", size=10),
        name="감성",
        hovertemplate="<b>%{x}</b><br>감성: %{text}<br>요약: " +
                      "<br>".join([""] * len(seed_dates)),
    ), row=1, col=1)
    fig_seed.add_hline(y=0, line_color="#1a2a45", line_dash="dash", row=1, col=1)

    # ── 행2: 영향도 바 ─────────────────────────────────────
    fig_seed.add_trace(go.Bar(
        x=seed_dates,
        y=impact_nums,
        marker_color=[IMPACT_COL.get(i, "#ffa726") for i in seed_impacts],
        text=[i.upper() for i in seed_impacts],
        textposition="inside",
        textfont=dict(family="IBM Plex Mono", size=10, color="#ffffff"),
        name="영향도",
        hovertemplate="<b>%{x}</b><br>영향도: %{text}",
    ), row=2, col=1)

    # ── 행3: 이슈 유형 타임라인 (색상 마커) ──────────────
    # 이슈 유형별 y 고정값 + 색상 팔레트
    unique_issues = list(dict.fromkeys(seed_issues))
    issue_palette = ["#7ecfff", "#00e676", "#ffa726", "#ff4444", "#c8a8ff",
                     "#ff8c69", "#69ffde", "#ffde69"]
    issue_color_map = {t: issue_palette[i % len(issue_palette)]
                       for i, t in enumerate(unique_issues)}

    for issue_type in unique_issues:
        x_vals, y_vals, texts = [], [], []
        for i, (d, it) in enumerate(zip(seed_dates, seed_issues)):
            if it == issue_type:
                x_vals.append(d)
                y_vals.append(1)
                texts.append(it)
        if x_vals:
            fig_seed.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode="markers+text",
                marker=dict(
                    symbol="square",
                    size=22,
                    color=issue_color_map[issue_type],
                    opacity=0.85,
                ),
                text=texts,
                textposition="middle center",
                textfont=dict(family="IBM Plex Mono", size=9, color="#070b14"),
                name=issue_type,
                showlegend=True,
            ), row=3, col=1)

    fig_seed.update_layout(
        height=560,
        barmode="stack",
        legend=dict(orientation="h", y=-0.08, x=0),
        **P,
    )
    fig_seed.update_yaxes(gridcolor="#1a2a45")
    fig_seed.update_yaxes(
        tickvals=[-1, 0, 1],
        ticktext=["부정", "중립", "긍정"],
        row=1, col=1,
    )
    fig_seed.update_yaxes(
        tickvals=[1, 2, 3],
        ticktext=["LOW", "MEDIUM", "HIGH"],
        row=2, col=1,
    )
    fig_seed.update_yaxes(showticklabels=False, row=3, col=1)
    st.plotly_chart(fig_seed, use_container_width=True)

    # ── 씨드 상세 카드 (날짜별 key_points) ────────────────
    st.markdown("<div class='sec-title'>날짜별 씨드 상세</div>", unsafe_allow_html=True)

    SENT_BORDER = {"positive": "#00e676", "neutral": "#3a6ea8", "negative": "#ff4444"}
    IMPACT_BADGE_COL = {"high": "#ff4444", "medium": "#ffa726", "low": "#7ecfff"}

    cols_per_row = 3
    for row_start in range(0, len(valid), cols_per_row):
        row_items = valid[row_start:row_start + cols_per_row]
        cols = st.columns(len(row_items))
        for col, d in zip(cols, row_items):
            seed    = d.get("seed", {})
            date    = d["issue_date"]
            sent    = seed.get("sentiment", "neutral")
            impact  = seed.get("impact_level", "medium")
            itype   = seed.get("issue_type", "기타") or "기타"
            summary = seed.get("summary", "")[:100]
            kps     = seed.get("key_points", [])[:3]
            result  = d.get("result", {})
            pred    = result.get("prediction", "—")
            buy     = result.get("buy_pressure", 0)
            sell    = result.get("sell_pressure", 0)

            pred_symbol = {"상승": "▲", "하락": "▼", "보합": "━"}.get(pred, "—")
            pred_color  = pred_col(pred)
            border_col  = SENT_BORDER.get(sent, "#3a6ea8")
            badge_col   = IMPACT_BADGE_COL.get(impact, "#ffa726")
            sent_label  = SENT_LBL.get(sent, sent)

            kp_html = "".join(
                f"<li style='margin:3px 0; color:#a0b4cc;'>{kp}</li>"
                for kp in kps
            )

            card_html = f"""
<div style="background:#0d1526; border:1px solid {border_col};
            border-top:3px solid {border_col}; border-radius:8px;
            padding:14px; margin-bottom:12px; font-size:0.82rem; line-height:1.7;">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
    <span style="font-family:'IBM Plex Mono',monospace; color:#7ecfff; font-size:0.75rem;">{date}</span>
    <span style="background:{badge_col}22; color:{badge_col}; border:1px solid {badge_col};
                 border-radius:4px; padding:1px 7px; font-size:0.68rem;
                 font-family:'IBM Plex Mono',monospace;">{impact.upper()}</span>
  </div>
  <div style="color:#c8d4e8; font-weight:600; margin-bottom:4px;">{itype}</div>
  <div style="color:{border_col}; font-size:0.75rem; margin-bottom:8px;">● {sent_label}</div>
  <div style="color:#8a9ab5; font-size:0.78rem; margin-bottom:8px;">{summary}...</div>
  <ul style="margin:0 0 10px 14px; padding:0; font-size:0.78rem;">
    {kp_html}
  </ul>
  <div style="border-top:1px solid #1a2a45; padding-top:8px; margin-top:4px;
              display:flex; justify-content:space-between; align-items:center;">
    <span style="color:{pred_color}; font-family:'IBM Plex Mono',monospace;
                 font-size:0.9rem; font-weight:700;">{pred_symbol} {pred}</span>
    <span style="color:#3a6ea8; font-size:0.72rem; font-family:'IBM Plex Mono',monospace;">
      매수 {buy:.0f}% / 매도 {sell:.0f}%
    </span>
  </div>
</div>"""
            col.markdown(card_html, unsafe_allow_html=True)

    # ── 차트1: 날짜별 압력 + 실제 주가 ──────────────────────
    st.markdown("<div class='sec-title'>날짜별 압력 변화 & 실제 등락</div>", unsafe_allow_html=True)
    dates  = [d["issue_date"] for d in valid]
    buy_p  = [d["result"]["buy_pressure"]  for d in valid]
    sell_p = [d["result"]["sell_pressure"] for d in valid]
    hold_p = [d["result"]["hold_pressure"] for d in valid]
    net_p  = [d["result"].get("net_pressure", 0) for d in valid]
    preds  = [d["result"]["prediction"]    for d in valid]
    act_1d = [d.get("validation",{}).get("evaluations",{}).get("1d",{}).get("actual_change_pct") for d in valid]

    fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True,
                         row_heights=[0.6, 0.4], vertical_spacing=0.05)
    fig1.add_trace(go.Bar(name="매수", x=dates, y=buy_p,  marker_color="#00e676", opacity=0.85), row=1, col=1)
    fig1.add_trace(go.Bar(name="관망", x=dates, y=hold_p, marker_color="#3a6ea8", opacity=0.6),  row=1, col=1)
    fig1.add_trace(go.Bar(name="매도", x=dates, y=sell_p, marker_color="#ff4444", opacity=0.85), row=1, col=1)
    fig1.add_trace(go.Scatter(
        name="예측", x=dates, y=[108]*len(dates), mode="markers+text",
        marker=dict(symbol="diamond", size=13, color=[pred_col(p) for p in preds]),
        text=preds, textposition="top center", textfont=dict(size=9),
    ), row=1, col=1)
    fig1.add_trace(go.Bar(
        name="실제 1일 등락", x=dates,
        y=[v if v is not None else 0 for v in act_1d],
        marker_color=["#00e676" if (v or 0) >= 0 else "#ff4444" for v in act_1d],
    ), row=2, col=1)
    fig1.add_hline(y=0, line_color="#3a6ea8", line_dash="dash", row=2, col=1)
    fig1.update_layout(barmode="stack", height=480, legend=dict(orientation="h", y=1.04), **P)
    fig1.update_yaxes(gridcolor="#1a2a45")
    st.plotly_chart(fig1, use_container_width=True)

    # ── 3번: 예측 방향 vs 실제 등락 라인 차트 ────────────────
    st.markdown("<div class='sec-title'>예측 방향 vs 실제 주가 등락 (누적 비교)</div>", unsafe_allow_html=True)

    # 예측 방향을 수치로 변환 (+1 상승 / -1 하락 / 0 보합)
    pred_numeric = [1 if p == "상승" else (-1 if p == "하락" else 0) for p in preds]
    # 순압력을 정규화 (-100~+100 → -1~+1)
    net_normalized = [n / 100 for n in net_p]

    fig_line = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.45], vertical_spacing=0.06,
        subplot_titles=["예측 방향 vs 실제 등락률", "누적 등락 비교"],
    )

    # 상단: 예측 방향(마커) + 실제 등락(선)
    fig_line.add_trace(go.Scatter(
        name="실제 1일 등락(%)", x=dates,
        y=[v if v is not None else None for v in act_1d],
        mode="lines+markers",
        line=dict(color="#7ecfff", width=2),
        marker=dict(size=7, color=["#00e676" if (v or 0) >= 0 else "#ff4444" for v in act_1d]),
        connectgaps=False,
    ), row=1, col=1)
    fig_line.add_trace(go.Scatter(
        name="순압력 (정규화)", x=dates, y=net_normalized,
        mode="lines", line=dict(color="#ffa726", width=1.5, dash="dot"),
    ), row=1, col=1)
    # 예측 방향 마커
    fig_line.add_trace(go.Scatter(
        name="AI 예측", x=dates, y=pred_numeric,
        mode="markers+text",
        marker=dict(symbol="diamond", size=14,
                    color=[pred_col(p) for p in preds],
                    line=dict(width=1, color="#ffffff")),
        text=preds, textposition="top center",
        textfont=dict(size=9, family="IBM Plex Mono"),
        yaxis="y",
    ), row=1, col=1)
    fig_line.add_hline(y=0, line_color="#1a2a45", line_dash="dash", row=1, col=1)

    # 하단: 누적 실제 등락 vs 예측이 맞았을 때만 누적
    cumulative_actual = []
    cumulative_correct = []
    cum_a = 0.0
    cum_c = 0.0
    for i, d in enumerate(valid):
        ev = d.get("validation", {}).get("evaluations", {}).get("1d", {})
        chg = ev.get("actual_change_pct")
        ok  = ev.get("is_correct")
        cum_a += (chg or 0)
        cumulative_actual.append(round(cum_a, 2))
        if ok:
            cum_c += (chg or 0)
        cumulative_correct.append(round(cum_c, 2))

    fig_line.add_trace(go.Scatter(
        name="누적 실제 등락", x=dates, y=cumulative_actual,
        mode="lines+markers", fill="tozeroy",
        fillcolor="rgba(0,230,118,0.07)",
        line=dict(color="#00e676", width=2),
        marker=dict(size=5),
    ), row=2, col=1)
    fig_line.add_trace(go.Scatter(
        name="예측 적중 시 누적", x=dates, y=cumulative_correct,
        mode="lines+markers",
        line=dict(color="#7ecfff", width=2, dash="dash"),
        marker=dict(size=5),
    ), row=2, col=1)
    fig_line.add_hline(y=0, line_color="#1a2a45", line_dash="dash", row=2, col=1)

    fig_line.update_layout(
        height=520,
        legend=dict(orientation="h", y=1.04),
        **P,
    )
    fig_line.update_yaxes(gridcolor="#1a2a45")
    fig_line.update_yaxes(ticksuffix="%", row=1, col=1)
    fig_line.update_yaxes(ticksuffix="%", row=2, col=1)
    st.plotly_chart(fig_line, use_container_width=True)

    # ── 차트2: 에이전트 결정 흐름 (타입별) ──────────────────
    st.markdown("<div class='sec-title'>에이전트 결정 흐름</div>", unsafe_allow_html=True)
    type_map  = {"retail":"개인", "day_trader":"단타", "institutional":"기관", "value_investor":"가치"}
    fig2 = make_subplots(rows=1, cols=4, subplot_titles=list(type_map.values()))

    for col_idx, (ptype, plabel) in enumerate(type_map.items(), 1):
        buy_vals, sell_vals, hold_vals = [], [], []
        for d in valid:
            tb = d["result"].get("type_breakdown", {})
            t  = tb.get(ptype, {})
            tot = t.get("total", 1) or 1
            buy_vals.append(t.get("매수", 0) / tot * 100)
            sell_vals.append(t.get("매도", 0) / tot * 100)
            hold_vals.append(t.get("관망", 0) / tot * 100)

        for vals, name, color in [
            (buy_vals, "매수", "#00e676"),
            (hold_vals, "관망", "#3a6ea8"),
            (sell_vals, "매도", "#ff4444"),
        ]:
            fig2.add_trace(go.Bar(
                name=name, x=dates, y=vals,
                marker_color=color, opacity=0.85,
                showlegend=(col_idx == 1),
            ), row=1, col=col_idx)

    fig2.update_layout(barmode="stack", height=300, **P)
    fig2.update_yaxes(gridcolor="#1a2a45", range=[0, 100])
    st.plotly_chart(fig2, use_container_width=True)

    # ── 5번: 이슈 유형별 정확도 분석 ─────────────────────────
    st.markdown("<div class='sec-title'>이슈 유형별 예측 정확도</div>", unsafe_allow_html=True)

    issue_stats: dict[str, dict] = {}
    for d in valid:
        issue_type = d.get("seed", {}).get("issue_type", "기타") or "기타"
        ev = d.get("validation", {}).get("evaluations", {}).get("1d", {})
        is_correct = ev.get("is_correct")
        if issue_type not in issue_stats:
            issue_stats[issue_type] = {"correct": 0, "wrong": 0, "unknown": 0,
                                        "avg_net": [], "avg_buy": [], "avg_sell": []}
        if is_correct is True:
            issue_stats[issue_type]["correct"] += 1
        elif is_correct is False:
            issue_stats[issue_type]["wrong"] += 1
        else:
            issue_stats[issue_type]["unknown"] += 1
        issue_stats[issue_type]["avg_net"].append(d["result"].get("net_pressure", 0))
        issue_stats[issue_type]["avg_buy"].append(d["result"]["buy_pressure"])
        issue_stats[issue_type]["avg_sell"].append(d["result"]["sell_pressure"])

    if issue_stats:
        issue_rows = []
        for itype, s in issue_stats.items():
            judged = s["correct"] + s["wrong"]
            acc = s["correct"] / judged * 100 if judged else None
            issue_rows.append({
                "이슈유형":    itype,
                "총횟수":      judged + s["unknown"],
                "판정횟수":    judged,
                "정확도":      acc,
                "평균순압력":  round(sum(s["avg_net"]) / len(s["avg_net"]), 1) if s["avg_net"] else 0,
            })
        issue_df = pd.DataFrame(issue_rows).sort_values("정확도", ascending=False, na_position="last")

        i_c1, i_c2 = st.columns([1, 1])
        with i_c1:
            # 이슈 유형별 정확도 수평 바
            judged_df = issue_df.dropna(subset=["정확도"])
            if not judged_df.empty:
                fig_issue = go.Figure(go.Bar(
                    x=judged_df["정확도"],
                    y=judged_df["이슈유형"],
                    orientation="h",
                    marker=dict(
                        color=["#00e676" if v >= 60 else "#ff4444" if v < 40 else "#ffa726"
                               for v in judged_df["정확도"]],
                    ),
                    text=[f"{v:.0f}% ({r['판정횟수']}건)"
                          for _, (v, r) in zip(judged_df["정확도"], judged_df.iterrows())],
                    textposition="outside",
                    textfont=dict(family="IBM Plex Mono", size=11),
                ))
                fig_issue.update_layout(
                    title="이슈 유형별 1일 예측 정확도",
                    height=max(250, len(judged_df) * 45 + 80),
                    xaxis=dict(range=[0, 120], ticksuffix="%", gridcolor="#1a2a45"),
                    yaxis=dict(gridcolor="#1a2a45"),
                    **P,
                )
                st.plotly_chart(fig_issue, use_container_width=True)

        with i_c2:
            # 이슈 유형별 평균 순압력 + 건수
            if not issue_df.empty:
                colors = ["#00e676" if v >= 0 else "#ff4444" for v in issue_df["평균순압력"]]
                fig_net = go.Figure(go.Bar(
                    x=issue_df["이슈유형"],
                    y=issue_df["평균순압력"],
                    marker_color=colors,
                    text=[f"{v:+.1f}%" for v in issue_df["평균순압력"]],
                    textposition="outside",
                    textfont=dict(family="IBM Plex Mono", size=11),
                ))
                fig_net.add_hline(y=0, line_color="#3a6ea8", line_dash="dash")
                fig_net.update_layout(
                    title="이슈 유형별 평균 순압력 (매수-매도)",
                    height=max(250, len(issue_df) * 45 + 80),
                    xaxis=dict(gridcolor="#1a2a45"),
                    yaxis=dict(ticksuffix="%", gridcolor="#1a2a45"),
                    **P,
                )
                st.plotly_chart(fig_net, use_container_width=True)

        # 이슈 유형별 요약 테이블
        display_issue = issue_df.copy()
        display_issue["정확도"] = display_issue["정확도"].apply(
            lambda x: f"{x:.0f}%" if x is not None else "—"
        )
        display_issue["평균순압력"] = display_issue["평균순압력"].apply(lambda x: f"{x:+.1f}%")
        st.dataframe(display_issue, use_container_width=True, hide_index=True)

    # ── 차트3: 에이전트 확신도 분석 ──────────────────────────
    st.markdown("<div class='sec-title'>에이전트 확신도 분석 (최신 라운드)</div>", unsafe_allow_html=True)
    last_decisions = valid[-1].get("final_decisions", []) if valid else []
    if last_decisions:
        conf_df = pd.DataFrame([{
            "에이전트":  d.get("agent_id", ""),
            "타입":     type_map.get(d.get("persona_type","retail"), d.get("persona_type","")),
            "결정":     d.get("action", "관망"),
            "확신도":   float(d.get("confidence", 0.5)),
        } for d in last_decisions])

        # 확신도 요약 메트릭
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("평균 확신도",    f"{conf_df['확신도'].mean():.2f}")
        mc2.metric("최고 확신도",    f"{conf_df['확신도'].max():.2f}")
        mc3.metric("최저 확신도",    f"{conf_df['확신도'].min():.2f}")
        high_conf = (conf_df["확신도"] >= 0.7).sum()
        mc4.metric("고확신(≥0.7)", f"{high_conf}명 / {len(conf_df)}명")

        st.markdown("<br>", unsafe_allow_html=True)
        c3a, c3b = st.columns([1, 1])

        # 왼쪽: 확신도 히스토그램 (결정별 색상 오버레이)
        with c3a:
            fig_hist = go.Figure()
            for action, color in [("매수", "#00e676"), ("매도", "#ff4444"), ("관망", "#ffa726")]:
                sub = conf_df[conf_df["결정"] == action]["확신도"]
                if not sub.empty:
                    fig_hist.add_trace(go.Histogram(
                        x=sub, name=action,
                        marker_color=color, opacity=0.75,
                        xbins=dict(start=0, end=1.0, size=0.1),
                    ))
            fig_hist.update_layout(
                title="확신도 분포 (전체 에이전트)",
                barmode="overlay", height=300,
                xaxis=dict(title="확신도", range=[0, 1.05], gridcolor="#1a2a45",
                           tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0]),
                yaxis=dict(title="에이전트 수", gridcolor="#1a2a45"),
                legend=dict(orientation="h", y=1.12),
                **P,
            )
            st.plotly_chart(fig_hist, use_container_width=True)

        # 오른쪽: 타입별 결정 수 + 평균 확신도 이중축
        with c3b:
            type_order    = ["개인", "단타", "기관", "가치"]
            avg_conf_by_type = conf_df.groupby("타입")["확신도"].mean().reindex(type_order).fillna(0)
            action_counts = conf_df.groupby(["타입", "결정"]).size().unstack(fill_value=0)

            fig_type = go.Figure()
            for action, color in [("매수", "#00e676"), ("매도", "#ff4444"), ("관망", "#ffa726")]:
                if action in action_counts.columns:
                    y_vals = [action_counts.loc[t, action] if t in action_counts.index else 0
                              for t in type_order]
                    fig_type.add_trace(go.Bar(
                        x=type_order, y=y_vals,
                        name=action, marker_color=color, opacity=0.8,
                    ))
            # 평균 확신도 선 (오른쪽 y축)
            fig_type.add_trace(go.Scatter(
                x=avg_conf_by_type.index.tolist(),
                y=avg_conf_by_type.values,
                mode="lines+markers+text",
                name="평균 확신도",
                line=dict(color="#7ecfff", width=2, dash="dot"),
                marker=dict(size=9, color="#7ecfff"),
                text=[f"{v:.2f}" for v in avg_conf_by_type.values],
                textposition="top center",
                textfont=dict(family="IBM Plex Mono", size=11, color="#7ecfff"),
                yaxis="y2",
            ))
            fig_type.update_layout(
                title="타입별 결정 수 & 평균 확신도",
                barmode="stack", height=300,
                xaxis=dict(gridcolor="#1a2a45"),
                yaxis=dict(title="에이전트 수", gridcolor="#1a2a45"),
                yaxis2=dict(title="평균 확신도", overlaying="y", side="right",
                            range=[0, 1.3], showgrid=False,
                            tickfont=dict(color="#7ecfff"), tickformat=".1f"),
                legend=dict(orientation="h", y=1.12),
                **P,
            )
            st.plotly_chart(fig_type, use_container_width=True)

    # ── 2번: 에이전트 발언 카드 ────────────────────────────────
    st.markdown("<div class='sec-title'>에이전트 주요 발언 (최신 라운드)</div>", unsafe_allow_html=True)
    if last_decisions:
        buy_voices  = [d for d in last_decisions if d.get("action") == "매수" and d.get("reason")]
        sell_voices = [d for d in last_decisions if d.get("action") == "매도" and d.get("reason")]
        hold_voices = [d for d in last_decisions if d.get("action") == "관망" and d.get("reason")]

        def voice_card(d: dict, color: str) -> str:
            ptype  = type_map.get(d.get("persona_type", "retail"), d.get("persona_type", ""))
            action = d.get("action", "")
            conf   = float(d.get("confidence", 0.5))
            reason = d.get("reason", "")[:140]
            action_symbol = {"매수": "▲", "매도": "▼", "관망": "━"}.get(action, "")
            return f"""
<div style="background:#0d1526; border-left:3px solid {color}; border-radius:6px;
            padding:12px 14px; margin-bottom:10px; font-size:0.85rem; line-height:1.6;">
  <div style="color:{color}; font-family:'IBM Plex Mono',monospace; font-size:0.7rem;
              letter-spacing:1px; margin-bottom:6px;">
    {action_symbol} {action} &nbsp;|&nbsp; {ptype} &nbsp;|&nbsp; 확신도 {conf:.0%}
  </div>
  <div style="color:#c8d4e8;">"{reason}..."</div>
</div>"""

        vc1, vc2, vc3 = st.columns(3)
        with vc1:
            st.markdown(f"<div style='color:#00e676; font-size:0.75rem; letter-spacing:2px; margin-bottom:8px;'>▲ 매수 ({len(buy_voices)}명)</div>", unsafe_allow_html=True)
            for d in buy_voices[:3]:
                st.markdown(voice_card(d, "#00e676"), unsafe_allow_html=True)
        with vc2:
            st.markdown(f"<div style='color:#ff4444; font-size:0.75rem; letter-spacing:2px; margin-bottom:8px;'>▼ 매도 ({len(sell_voices)}명)</div>", unsafe_allow_html=True)
            for d in sell_voices[:3]:
                st.markdown(voice_card(d, "#ff4444"), unsafe_allow_html=True)
        with vc3:
            st.markdown(f"<div style='color:#ffa726; font-size:0.75rem; letter-spacing:2px; margin-bottom:8px;'>━ 관망 ({len(hold_voices)}명)</div>", unsafe_allow_html=True)
            for d in hold_voices[:3]:
                st.markdown(voice_card(d, "#ffa726"), unsafe_allow_html=True)

    # ── 예측 vs 실제 상세 테이블 ───────────────────────────────
    st.markdown("<div class='sec-title'>예측 vs 실제 상세</div>", unsafe_allow_html=True)

    # 기간 선택 탭
    tab_1d, tab_5d, tab_20d = st.tabs(["📅 1일 (익일 종가)", "📅 5일 (1주)", "📅 20일 (1달)"])

    def build_detail_df(period_key: str) -> pd.DataFrame:
        rows = []
        for d in valid:
            res  = d["result"]
            seed = d.get("seed", {})
            ev   = d.get("validation", {}).get("evaluations", {}).get(period_key, {})

            chg = ev.get("actual_change_pct")
            dir_ = ev.get("actual_direction")
            ok  = ev.get("is_correct")

            def arrow(v):
                return {"상승": "▲ 상승", "하락": "▼ 하락", "보합": "━ 보합"}.get(v, "—") if v else "—"

            rows.append({
                "날짜":        d["issue_date"],
                "이슈유형":    seed.get("issue_type", ""),
                "시장심리":    seed.get("sentiment", ""),
                "AI 예측":     arrow(res["prediction"]),
                "매수 압력":   f"{res['buy_pressure']:.1f}%",
                "매도 압력":   f"{res['sell_pressure']:.1f}%",
                "순압력":      f"{res.get('net_pressure', 0):+.1f}%",
                "실제 등락":   f"{chg:+.2f}%" if chg is not None else "—",
                "실제 방향":   arrow(dir_),
                "판정":        "✓ 맞음" if ok is True else ("✗ 틀림" if ok is False else "—"),
            })
        return pd.DataFrame(rows)

    def render_detail_tab(period_key: str):
        df = build_detail_df(period_key)
        judged = df[df["판정"].isin(["✓ 맞음", "✗ 틀림"])]
        if not judged.empty:
            acc = (judged["판정"] == "✓ 맞음").sum() / len(judged) * 100
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("전체",    len(df))
            m2.metric("판정 가능", len(judged))
            m3.metric("맞음 / 틀림",
                      f"{(judged['판정']=='✓ 맞음').sum()} / {(judged['판정']=='✗ 틀림').sum()}")
            m4.metric("정확도", f"{acc:.0f}%")

        def sty(val):
            if val == "✓ 맞음":  return "color:#00e676; font-weight:700"
            if val == "✗ 틀림":  return "color:#ff4444; font-weight:700"
            if val == "▲ 상승":  return "color:#00e676; font-weight:600"
            if val == "▼ 하락":  return "color:#ff4444; font-weight:600"
            if val == "━ 보합":  return "color:#ffa726; font-weight:600"
            if isinstance(val, str) and val.startswith("+"): return "color:#00e676; font-family:monospace"
            if isinstance(val, str) and val.startswith("-"): return "color:#ff4444; font-family:monospace"
            return "font-family:monospace"

        st.dataframe(df.style.applymap(sty), use_container_width=True, height=400)

    with tab_1d:  render_detail_tab("1d")
    with tab_5d:  render_detail_tab("5d")
    with tab_20d: render_detail_tab("20d")

# ── 6번 + 7번: 백테스트 분석 뷰 ─────────────────────────────
elif view == "📈 백테스트 분석":
    st.markdown("# 백테스트 분석")
    st.markdown("<div style='color:#3a6ea8; font-size:0.8rem; margin-bottom:24px;'>전체 시뮬레이션 이력 기반 통계 분석</div>", unsafe_allow_html=True)

    # ticker당 최신 실행 1건만 로드
    runs = get_latest_run_per_ticker()
    if not runs:
        st.info("데이터 없음 — `python run_multi_stock.py` 먼저 실행")
        st.stop()

    # 전체 데이터 수집
    all_daily = []
    for run in runs:
        for d in run.get("daily_results", []):
            if "result" not in d:
                continue
            all_daily.append({
                "run_id":       run["run_id"],
                "corp":         run["corp"],
                "ticker":       run["ticker"],
                "sector":       run.get("sector", ""),
                "date":         d["issue_date"],
                "prediction":   d["result"]["prediction"],
                "buy_p":        d["result"]["buy_pressure"],
                "sell_p":       d["result"]["sell_pressure"],
                "net_p":        d["result"].get("net_pressure", 0),
                "strength":     d["result"].get("strength", "-"),
                "disagreement": d["result"].get("disagreement"),
                "conf_avg":     d["result"].get("confidence_avg"),
                "issue_type":   d.get("seed", {}).get("issue_type", "기타") or "기타",
                "ev_1d":        d.get("validation", {}).get("evaluations", {}).get("1d", {}),
                "ev_5d":        d.get("validation", {}).get("evaluations", {}).get("5d", {}),
                "ev_20d":       d.get("validation", {}).get("evaluations", {}).get("20d", {}),
            })

    if not all_daily:
        st.warning("유효 데이터 없음")
        st.stop()

    # ── 6번: 백테스트 요약 통계 ──────────────────────────────
    st.markdown("<div class='sec-title'>전체 백테스트 요약</div>", unsafe_allow_html=True)

    def calc_accuracy(data, period_key):
        evs = [d[f"ev_{period_key}"] for d in data if d[f"ev_{period_key}"].get("is_correct") is not None]
        if not evs:
            return None
        return round(sum(1 for e in evs if e["is_correct"]) / len(evs) * 100, 1)

    total_sims  = len(all_daily)
    acc_1d  = calc_accuracy(all_daily, "1d")
    acc_5d  = calc_accuracy(all_daily, "5d")
    acc_20d = calc_accuracy(all_daily, "20d")

    # 예측별 평균 실제 등락
    pred_actual: dict[str, list] = {"상승": [], "하락": [], "보합": []}
    for d in all_daily:
        chg = d["ev_1d"].get("actual_change_pct")
        if chg is not None:
            pred_actual[d["prediction"]].append(chg)
    pred_avg = {k: round(sum(v)/len(v), 2) if v else None for k, v in pred_actual.items()}

    # 강/약 신호별 정확도
    strong_correct = [d for d in all_daily if d["strength"] == "강" and d["ev_1d"].get("is_correct") is True]
    strong_total   = [d for d in all_daily if d["strength"] == "강" and d["ev_1d"].get("is_correct") is not None]
    weak_correct   = [d for d in all_daily if d["strength"] == "약" and d["ev_1d"].get("is_correct") is True]
    weak_total     = [d for d in all_daily if d["strength"] == "약" and d["ev_1d"].get("is_correct") is not None]
    strong_acc = round(len(strong_correct)/len(strong_total)*100, 1) if strong_total else None
    weak_acc   = round(len(weak_correct)/len(weak_total)*100, 1)   if weak_total   else None

    # 요약 메트릭 카드
    bm1, bm2, bm3, bm4 = st.columns(4)
    for col, val, lbl, cls in [
        (bm1, str(total_sims), "총 시뮬레이션", "hold"),
        (bm2, f"{acc_1d}%" if acc_1d is not None else "—", "1일 정확도", "up" if (acc_1d or 0) >= 60 else "down" if (acc_1d or 0) < 40 else "hold"),
        (bm3, f"{acc_5d}%" if acc_5d is not None else "—", "5일 정확도", "up" if (acc_5d or 0) >= 60 else "down" if (acc_5d or 0) < 40 else "hold"),
        (bm4, f"{acc_20d}%" if acc_20d is not None else "—", "20일 정확도", "up" if (acc_20d or 0) >= 60 else "down" if (acc_20d or 0) < 40 else "hold"),
    ]:
        col.markdown(f"<div class='metric-card'><div class='metric-val {cls}'>{val}</div><div class='metric-lbl'>{lbl}</div></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 예측 방향별 평균 실제 등락 (핵심 검증 지표)
    st.markdown("<div class='sec-title'>예측 방향별 실제 평균 등락 (1일)</div>", unsafe_allow_html=True)
    bc1, bc2 = st.columns([1, 1])

    with bc1:
        labels = list(pred_avg.keys())
        values = [pred_avg[k] if pred_avg[k] is not None else 0 for k in labels]
        counts = [len(pred_actual[k]) for k in labels]
        fig_pred_chg = go.Figure(go.Bar(
            x=labels,
            y=values,
            marker_color=["#00e676" if v >= 0 else "#ff4444" for v in values],
            text=[f"{v:+.2f}%<br>({c}건)" if pred_avg[k] is not None else "데이터없음"
                  for v, c, k in zip(values, counts, labels)],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono", size=12),
        ))
        fig_pred_chg.add_hline(y=0, line_color="#3a6ea8", line_dash="dash")
        fig_pred_chg.update_layout(
            title="'상승' 예측 시 실제로 얼마나 올랐나?",
            height=320,
            xaxis=dict(gridcolor="#1a2a45"),
            yaxis=dict(ticksuffix="%", gridcolor="#1a2a45"),
            **P,
        )
        st.plotly_chart(fig_pred_chg, use_container_width=True)

    with bc2:
        # 강/약 신호별 정확도 비교
        signal_labels = ["강한 신호", "약한 신호"]
        signal_accs   = [strong_acc or 0, weak_acc or 0]
        signal_counts = [len(strong_total), len(weak_total)]
        fig_strength = go.Figure(go.Bar(
            x=signal_labels,
            y=signal_accs,
            marker_color=["#00e676" if v >= 60 else "#ffa726" for v in signal_accs],
            text=[f"{v:.0f}%<br>({c}건)" for v, c in zip(signal_accs, signal_counts)],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono", size=12),
        ))
        fig_strength.update_layout(
            title="신호 강도별 1일 정확도",
            height=320,
            xaxis=dict(gridcolor="#1a2a45"),
            yaxis=dict(range=[0, 115], ticksuffix="%", gridcolor="#1a2a45"),
            **P,
        )
        st.plotly_chart(fig_strength, use_container_width=True)

    # 순압력 구간별 정확도 (신뢰도 곡선)
    st.markdown("<div class='sec-title'>순압력 구간별 1일 예측 정확도</div>", unsafe_allow_html=True)
    bins = [(-100, -50), (-50, -25), (-25, 0), (0, 25), (25, 50), (50, 100)]
    bin_labels = ["≤-50", "-50~-25", "-25~0", "0~25", "25~50", "≥50"]
    bin_accs, bin_counts = [], []
    for lo, hi in bins:
        subset = [d for d in all_daily
                  if lo <= d["net_p"] < hi
                  and d["ev_1d"].get("is_correct") is not None]
        if subset:
            acc = sum(1 for d in subset if d["ev_1d"]["is_correct"]) / len(subset) * 100
            bin_accs.append(round(acc, 1))
        else:
            bin_accs.append(None)
        bin_counts.append(len(subset))

    fig_curve = go.Figure()
    valid_bins = [(l, a, c) for l, a, c in zip(bin_labels, bin_accs, bin_counts) if a is not None]
    if valid_bins:
        vl, va, vc = zip(*valid_bins)
        fig_curve.add_trace(go.Scatter(
            x=list(vl), y=list(va),
            mode="lines+markers+text",
            line=dict(color="#7ecfff", width=2),
            marker=dict(size=[max(8, c*2) for c in vc],
                        color=["#00e676" if a >= 60 else "#ff4444" if a < 40 else "#ffa726" for a in va],
                        line=dict(width=1, color="#ffffff")),
            text=[f"{a:.0f}%\n({c}건)" for a, c in zip(va, vc)],
            textposition="top center",
            textfont=dict(family="IBM Plex Mono", size=10),
        ))
    fig_curve.add_hline(y=50, line_color="#3a6ea8", line_dash="dash",
                        annotation_text="랜덤 기준선 50%", annotation_position="right")
    fig_curve.update_layout(
        title="순압력이 클수록 예측이 정확한가? (신뢰도 곡선)",
        height=320,
        xaxis=dict(title="순압력 구간", gridcolor="#1a2a45"),
        yaxis=dict(title="정확도", range=[0, 110], ticksuffix="%", gridcolor="#1a2a45"),
        **P,
    )
    st.plotly_chart(fig_curve, use_container_width=True)

    # 종목별 × 기간별 정확도 히트맵
    st.markdown("<div class='sec-title'>종목 × 기간별 정확도 히트맵</div>", unsafe_allow_html=True)
    corps_list  = sorted({d["corp"] for d in all_daily})
    periods     = ["1d", "5d", "20d"]
    period_lbls = ["1일", "5일", "20일"]
    heat_data   = []
    for corp in corps_list:
        row = []
        for p in periods:
            sub = [d for d in all_daily if d["corp"] == corp and d[f"ev_{p}"].get("is_correct") is not None]
            acc = sum(1 for d in sub if d[f"ev_{p}"]["is_correct"]) / len(sub) * 100 if sub else None
            row.append(acc)
        heat_data.append(row)

    if corps_list:
        import numpy as np
        z_data = [[v if v is not None else -1 for v in row] for row in heat_data]
        text_data = [[f"{v:.0f}%" if v is not None else "—" for v in row] for row in heat_data]
        fig_heat = go.Figure(go.Heatmap(
            z=z_data, x=period_lbls, y=corps_list,
            text=text_data, texttemplate="%{text}",
            colorscale=[[0, "#ff4444"], [0.5, "#ffa726"], [1, "#00e676"]],
            zmin=0, zmax=100,
            colorbar=dict(title="정확도%", ticksuffix="%"),
        ))
        fig_heat.update_layout(
            title="종목별 예측 정확도 히트맵",
            height=max(300, len(corps_list) * 40 + 100),
            xaxis=dict(side="top"),
            **P,
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    # ── 7번: 시뮬레이션 재현성 (안정성) 분석 ─────────────────
    st.markdown("<div class='sec-title'>시뮬레이션 재현성 — 안정성 분석 (Stability Score)</div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='color:#3a6ea8; font-size:0.8rem; margin-bottom:16px;'>"
        "동일 종목·날짜에 여러 번 실행했을 때 예측이 얼마나 일관되는지 측정합니다. "
        "LLM의 랜덤성이 결과에 미치는 영향을 정량화한 지표입니다.</div>",
        unsafe_allow_html=True
    )

    # 종목+날짜 기준으로 그룹핑
    from collections import defaultdict as _ddict
    key_groups: dict[str, list] = _ddict(list)
    for d in all_daily:
        key = f"{d['ticker']}_{d['date']}"
        key_groups[key].append(d)

    multi_run_keys = {k: v for k, v in key_groups.items() if len(v) >= 2}

    if not multi_run_keys:
        # 단일 실행 데이터만 있을 때 — 날짜별 net_pressure 분산으로 대체 분석
        st.info("동일 종목·날짜 복수 실행 데이터가 없습니다. 순압력 분포로 안정성을 대신 분석합니다.")

        net_vals = [d["net_p"] for d in all_daily]
        disagree_vals = [d["disagreement"] for d in all_daily if d["disagreement"] is not None]
        conf_vals     = [d["conf_avg"]     for d in all_daily if d["conf_avg"]     is not None]

        s1, s2 = st.columns([1, 1])
        with s1:
            # 순압력 분포 히스토그램
            fig_net_dist = go.Figure(go.Histogram(
                x=net_vals, nbinsx=20,
                marker_color="#7ecfff", opacity=0.8,
                name="순압력 분포",
            ))
            fig_net_dist.add_vline(x=0, line_color="#3a6ea8", line_dash="dash")
            fig_net_dist.update_layout(
                title=f"순압력 전체 분포 (표준편차: {round(float(pd.Series(net_vals).std()), 1) if net_vals else '—'}%p)",
                height=300,
                xaxis=dict(title="순압력 (%p)", gridcolor="#1a2a45"),
                yaxis=dict(title="빈도", gridcolor="#1a2a45"),
                **P,
            )
            st.plotly_chart(fig_net_dist, use_container_width=True)

        with s2:
            if disagree_vals:
                fig_disagree = go.Figure()
                fig_disagree.add_trace(go.Histogram(
                    x=disagree_vals, nbinsx=15,
                    marker_color="#ffa726", opacity=0.8, name="불일치 지수",
                ))
                if conf_vals:
                    fig_disagree.add_trace(go.Histogram(
                        x=conf_vals, nbinsx=15,
                        marker_color="#00e676", opacity=0.6, name="평균 확신도",
                    ))
                fig_disagree.update_layout(
                    title="불일치 지수 & 평균 확신도 분포",
                    barmode="overlay", height=300,
                    xaxis=dict(title="값", gridcolor="#1a2a45"),
                    yaxis=dict(title="빈도", gridcolor="#1a2a45"),
                    legend=dict(orientation="h", y=1.1),
                    **P,
                )
                st.plotly_chart(fig_disagree, use_container_width=True)

        # 안정성 지표 요약
        if disagree_vals and conf_vals:
            avg_disagree = sum(disagree_vals) / len(disagree_vals)
            avg_conf     = sum(conf_vals) / len(conf_vals)
            high_disagree_pct = sum(1 for v in disagree_vals if v >= 0.45) / len(disagree_vals) * 100

            stability_score = round((1 - avg_disagree) * avg_conf * 100, 1)

            st.markdown("<div class='sec-title'>안정성 종합 지표</div>", unsafe_allow_html=True)
            ss1, ss2, ss3, ss4 = st.columns(4)
            for col, val, lbl, cls in [
                (ss1, f"{stability_score:.1f}", "Stability Score", "up" if stability_score >= 60 else "down" if stability_score < 40 else "hold"),
                (ss2, f"{avg_disagree:.3f}", "평균 불일치 지수", "down" if avg_disagree >= 0.4 else "up" if avg_disagree < 0.25 else "hold"),
                (ss3, f"{avg_conf:.3f}", "평균 확신도", "up" if avg_conf >= 0.65 else "down" if avg_conf < 0.5 else "hold"),
                (ss4, f"{high_disagree_pct:.0f}%", "고불일치 비율(≥0.45)", "down" if high_disagree_pct >= 30 else "up"),
            ]:
                col.markdown(
                    f"<div class='metric-card'><div class='metric-val {cls}'>{val}</div>"
                    f"<div class='metric-lbl'>{lbl}</div></div>",
                    unsafe_allow_html=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f"<div style='background:#0d1526; border:1px solid #1a2a45; border-radius:6px; padding:14px 18px; font-size:0.85rem; line-height:1.8;'>"
                f"<b style='color:#7ecfff; font-family:IBM Plex Mono;'>Stability Score</b>란? "
                f"<span style='color:#c8d4e8;'>"
                f"(1 - 평균 불일치 지수) × 평균 확신도 × 100 으로 계산됩니다. "
                f"에이전트들이 얼마나 일관되고 확신 있게 판단하는지를 0~100으로 표현합니다. "
                f"점수가 높을수록 예측의 재현성이 높고, 낮을수록 LLM 랜덤성의 영향을 많이 받습니다."
                f"</span></div>",
                unsafe_allow_html=True,
            )

    else:
        # 복수 실행 데이터가 있을 때 — 예측 일관성 직접 측정
        stability_rows = []
        for key, group in multi_run_keys.items():
            preds_group = [d["prediction"] for d in group]
            majority    = max(set(preds_group), key=preds_group.count)
            consistency = preds_group.count(majority) / len(preds_group) * 100
            net_vals_g  = [d["net_p"] for d in group]
            net_std     = float(pd.Series(net_vals_g).std()) if len(net_vals_g) > 1 else 0
            stability_rows.append({
                "종목날짜":  key,
                "실행횟수":  len(group),
                "다수예측":  majority,
                "일관성%":   round(consistency, 1),
                "순압력편차": round(net_std, 1),
            })

        stab_df = pd.DataFrame(stability_rows).sort_values("일관성%", ascending=False)
        avg_consistency = stab_df["일관성%"].mean()
        avg_net_std     = stab_df["순압력편차"].mean()
        stability_score = round(avg_consistency * (1 - avg_net_std / 100), 1)

        ss1, ss2, ss3 = st.columns(3)
        for col, val, lbl, cls in [
            (ss1, f"{stability_score:.1f}", "Stability Score", "up" if stability_score >= 70 else "down" if stability_score < 50 else "hold"),
            (ss2, f"{avg_consistency:.1f}%", "평균 예측 일관성", "up" if avg_consistency >= 70 else "down" if avg_consistency < 50 else "hold"),
            (ss3, f"{avg_net_std:.1f}%p", "순압력 평균 표준편차", "up" if avg_net_std < 10 else "down" if avg_net_std >= 20 else "hold"),
        ]:
            col.markdown(
                f"<div class='metric-card'><div class='metric-val {cls}'>{val}</div>"
                f"<div class='metric-lbl'>{lbl}</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        fig_stab = go.Figure(go.Bar(
            x=stab_df["종목날짜"], y=stab_df["일관성%"],
            marker_color=["#00e676" if v >= 70 else "#ff4444" if v < 50 else "#ffa726"
                          for v in stab_df["일관성%"]],
            text=[f"{v:.0f}%" for v in stab_df["일관성%"]],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono", size=10),
        ))
        fig_stab.add_hline(y=avg_consistency, line_color="#7ecfff", line_dash="dash",
                           annotation_text=f"평균 {avg_consistency:.0f}%", annotation_position="right")
        fig_stab.update_layout(
            title="동일 조건 복수 실행 — 예측 일관성",
            height=350,
            xaxis=dict(gridcolor="#1a2a45", tickangle=-30),
            yaxis=dict(range=[0, 115], ticksuffix="%", gridcolor="#1a2a45"),
            **P,
        )
        st.plotly_chart(fig_stab, use_container_width=True)

        def sty_stab(val):
            if isinstance(val, float) and val >= 70: return "color:#00e676"
            if isinstance(val, float) and val < 50:  return "color:#ff4444"
            return ""
        st.dataframe(
            stab_df.style.applymap(sty_stab, subset=["일관성%"]),
            use_container_width=True, hide_index=True,
        )

# ════════════════════════════════════════════════════════════
# 🧠 시뮬레이션 흐름 뷰
# ════════════════════════════════════════════════════════════
elif view == "🧠 시뮬레이션 흐름":

    # ── 흰 배경 + 라이트 테마 CSS 오버라이드 ──────────────
    st.markdown("""
<style>
.stApp { background: #FFFFFF !important; color: #1a1a2e !important; }
[data-testid="stSidebar"] { background: #f0f0f0 !important; }
.sim-section { margin: 32px 0 16px; }
.sim-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem; color: #666; text-transform: uppercase;
    letter-spacing: 3px; border-bottom: 2px solid #1a1a2e;
    padding-bottom: 6px; margin-bottom: 18px;
}
.flow-arrow {
    text-align: center; font-size: 2rem; color: #888; margin: 4px 0;
}
.seed-card {
    background: #fff; border: 1.5px solid #e0e0e0;
    border-top: 4px solid #1a1a2e; border-radius: 10px;
    padding: 16px; margin-bottom: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.agent-card {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 12px; margin-bottom: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.tag {
    display:inline-block; border-radius:4px; padding:2px 8px;
    font-size:0.68rem; font-family:'IBM Plex Mono',monospace;
    font-weight:600; margin-right:4px;
}
.tag-pos  { background:#e6faf0; color:#00a854; border:1px solid #00a854; }
.tag-neg  { background:#fff0f0; color:#d93025; border:1px solid #d93025; }
.tag-neu  { background:#fff8e6; color:#b07d00; border:1px solid #b07d00; }
.tag-high { background:#fde8e8; color:#c62828; border:1px solid #c62828; }
.tag-med  { background:#fff3e0; color:#e65100; border:1px solid #e65100; }
.tag-low  { background:#e3f2fd; color:#1565c0; border:1px solid #1565c0; }
.pred-up   { color:#00a854; font-weight:700; font-size:1.1rem; }
.pred-down { color:#d93025; font-weight:700; font-size:1.1rem; }
.pred-hold { color:#b07d00; font-weight:700; font-size:1.1rem; }
.kp-item { font-size:0.8rem; color:#444; padding:3px 0; border-bottom:1px dashed #eee; }
.timeline-date {
    font-family:'IBM Plex Mono',monospace; font-size:0.75rem;
    color:#888; margin-bottom:4px;
}
.summary-text { font-size:0.82rem; color:#555; line-height:1.6; margin:8px 0; }
.agent-reason { font-size:0.78rem; color:#444; line-height:1.5; font-style:italic; }
.stat-box {
    background:#f5f5f5; border-radius:8px; padding:14px;
    text-align:center; border:1px solid #e0e0e0;
}
.stat-val { font-family:'IBM Plex Mono',monospace; font-size:1.5rem; font-weight:700; }
.stat-lbl { font-size:0.68rem; color:#888; text-transform:uppercase; letter-spacing:1.5px; margin-top:4px; }
</style>
""", unsafe_allow_html=True)

    # ── 플롯리 라이트 테마 ─────────────────────────────────
    PL = dict(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#D3D3D3",
        font=dict(color="#1a1a2e", family="IBM Plex Mono"),
        margin=dict(l=40, r=20, t=40, b=36),
    )

    run  = load_run(selected_run["run_id"])
    if not run:
        st.error("데이터 없음")
        st.stop()

    daily  = run.get("daily_results", [])
    valid  = [d for d in daily if "result" in d]
    corp   = run["corp"]
    ticker = run["ticker"]

    # ── 헤더 ───────────────────────────────────────────────
    st.markdown(f"""
<div style='padding:28px 0 8px;'>
  <div style='font-family:IBM Plex Mono,monospace; font-size:0.7rem; color:#888;
              letter-spacing:3px; text-transform:uppercase;'>AgentFlow — Simulation Walkthrough</div>
  <h1 style='font-size:2rem; font-weight:700; color:#1a1a2e; margin:6px 0 4px;'>
    {corp} <span style='color:#888; font-size:1.2rem;'>{ticker}</span>
  </h1>
  <p style='color:#666; font-size:0.9rem; max-width:640px; line-height:1.7;'>
    이 탭은 AgentFlow가 <b>패턴 학습 없이</b> 어떻게 주가 방향을 예측하는지
    그 과정을 날짜별로 보여줍니다.<br>
    <b>공시·뉴스 씨드 → 에이전트 독립 판단 → 군중 압력 → 최종 예측</b> 순서로 읽으세요.
  </p>
</div>
""", unsafe_allow_html=True)

    # ── 0. 시스템 개요 다이어그램 ──────────────────────────
    st.markdown("<div class='sim-title sim-section'>How It Works — 시스템 흐름도</div>",
                unsafe_allow_html=True)

    SENT_TAG  = {"positive":"<span class='tag tag-pos'>긍정</span>",
                 "negative":"<span class='tag tag-neg'>부정</span>",
                 "neutral" :"<span class='tag tag-neu'>중립</span>"}
    IMPACT_TAG= {"high":"<span class='tag tag-high'>HIGH</span>",
                 "medium":"<span class='tag tag-med'>MEDIUM</span>",
                 "low":"<span class='tag tag-low'>LOW</span>"}

    steps = [
        ("01", "데이터 수집", "#1a1a2e",
         "DART 전자공시 + 네이버 뉴스 + 공공데이터포털 주가를 실시간 수집합니다."),
        ("02", "씨드 파싱 (LLM)", "#2a5298",
         "LLM(리스크 분석가 롤)이 수집 데이터를 이슈유형·감성·영향도·핵심포인트로 요약합니다."),
        ("03", "라운드 1 — 독립 판단", "#00a854",
         "20명 에이전트(개인·기관·단타·가치)가 씨드만 보고 각자 매수/매도/관망을 결정합니다."),
        ("04", "군중 압력 생성", "#e65100",
         "InteractionEngine이 라운드 1 결과를 집계해 '🔴 강한 매도세(70%)' 같은 신호 텍스트를 생성합니다."),
        ("05", "라운드 2 — 재판단", "#7b1fa2",
         "에이전트들이 군중 신호 + 자신의 직전 결정을 보고 입장을 재검토합니다."),
        ("06", "집계 & 예측", "#c62828",
         "KOSPI 가중치·확신도·HHI 불일치 지수를 반영해 최종 상승/하락/보합을 판정합니다."),
    ]

    cols6 = st.columns(6)
    for col, (num, title, color, desc) in zip(cols6, steps):
        col.markdown(f"""
<div style='background:#fff; border:1px solid #e0e0e0; border-top:3px solid {color};
            border-radius:8px; padding:14px 10px; text-align:center; height:160px;
            box-shadow:0 2px 6px rgba(0,0,0,0.05);'>
  <div style='font-family:IBM Plex Mono,monospace; font-size:1.4rem;
              font-weight:700; color:{color}; margin-bottom:4px;'>{num}</div>
  <div style='font-size:0.8rem; font-weight:700; color:#1a1a2e; margin-bottom:8px;'>{title}</div>
  <div style='font-size:0.72rem; color:#555; line-height:1.5;'>{desc}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 1. 씨드 흐름 개요 차트 ────────────────────────────
    st.markdown("<div class='sim-title sim-section'>씨드 흐름 — 날짜별 시장 신호</div>",
                unsafe_allow_html=True)

    seed_dates   = [d["issue_date"] for d in valid]
    sentiments   = [d.get("seed",{}).get("sentiment","neutral")    for d in valid]
    impacts      = [d.get("seed",{}).get("impact_level","medium")  for d in valid]
    issue_types  = [d.get("seed",{}).get("issue_type","기타") or "기타" for d in valid]
    buy_ps       = [d["result"]["buy_pressure"]  for d in valid]
    sell_ps      = [d["result"]["sell_pressure"] for d in valid]
    hold_ps      = [d["result"].get("hold_pressure",0) for d in valid]
    preds        = [d["result"]["prediction"]    for d in valid]
    act_1ds      = [d.get("validation",{}).get("evaluations",{}).get("1d",{}).get("actual_change_pct") for d in valid]

    SENT_NUM  = {"positive":1,"neutral":0,"negative":-1}
    SENT_COL_L= {"positive":"#00a854","neutral":"#b07d00","negative":"#d93025"}
    IMPACT_NUM= {"high":3,"medium":2,"low":1}
    IMPACT_COL_L={"high":"#c62828","medium":"#e65100","low":"#1565c0"}

    sent_nums   = [SENT_NUM.get(s,0)  for s in sentiments]
    impact_nums = [IMPACT_NUM.get(i,2) for i in impacts]

    from plotly.subplots import make_subplots as _msp
    fig_flow = _msp(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.38, 0.27, 0.35],
        vertical_spacing=0.07,
        subplot_titles=["감성 흐름 (Sentiment)", "영향도 (Impact Level)", "에이전트 매수/매도 압력 → 예측"],
    )

    # 행1: 감성
    fig_flow.add_trace(go.Scatter(
        x=seed_dates, y=sent_nums,
        mode="lines+markers+text",
        line=dict(color="#2a5298", width=2.5),
        fill="tozeroy", fillcolor="rgba(42,82,152,0.08)",
        marker=dict(size=14, color=[SENT_COL_L.get(s,"#b07d00") for s in sentiments],
                    line=dict(width=2,color="#fff")),
        text=["긍정" if s=="positive" else "부정" if s=="negative" else "중립"
              for s in sentiments],
        textposition="top center",
        textfont=dict(size=10, family="IBM Plex Mono"),
        name="감성",
    ), row=1, col=1)
    fig_flow.add_hline(y=0, line_color="#888", line_dash="dash", line_width=1, row=1, col=1)

    # 행2: 영향도
    fig_flow.add_trace(go.Bar(
        x=seed_dates, y=impact_nums,
        marker_color=[IMPACT_COL_L.get(i,"#e65100") for i in impacts],
        text=[i.upper() for i in impacts],
        textposition="inside",
        textfont=dict(size=10, family="IBM Plex Mono", color="#fff"),
        name="영향도",
    ), row=2, col=1)

    # 행3: 압력 스택 + 예측 마커 + 실제 등락
    pred_col_l = lambda p: "#00a854" if p=="상승" else "#d93025" if p=="하락" else "#b07d00"
    fig_flow.add_trace(go.Bar(x=seed_dates, y=buy_ps,
        marker_color="#00a854", opacity=0.8, name="매수압력"), row=3, col=1)
    fig_flow.add_trace(go.Bar(x=seed_dates, y=hold_ps,
        marker_color="#aaaaaa", opacity=0.6, name="관망"), row=3, col=1)
    fig_flow.add_trace(go.Bar(x=seed_dates, y=sell_ps,
        marker_color="#d93025", opacity=0.8, name="매도압력"), row=3, col=1)
    fig_flow.add_trace(go.Scatter(
        x=seed_dates, y=[108]*len(seed_dates),
        mode="markers+text",
        marker=dict(symbol="diamond", size=14,
                    color=[pred_col_l(p) for p in preds],
                    line=dict(width=1.5, color="#1a1a2e")),
        text=preds, textposition="top center",
        textfont=dict(size=9, family="IBM Plex Mono", color="#1a1a2e"),
        name="AI 예측",
    ), row=3, col=1)

    fig_flow.update_layout(
        height=580, barmode="stack",
        legend=dict(orientation="h", y=-0.06, x=0, font=dict(size=11)),
        **PL,
    )
    fig_flow.update_yaxes(gridcolor="#bbb", row=1, col=1,
        tickvals=[-1,0,1], ticktext=["부정","중립","긍정"])
    fig_flow.update_yaxes(gridcolor="#bbb", row=2, col=1,
        tickvals=[1,2,3], ticktext=["LOW","MED","HIGH"])
    fig_flow.update_yaxes(gridcolor="#bbb", row=3, col=1, ticksuffix="%")
    st.plotly_chart(fig_flow, use_container_width=True)

    # ── 2. 날짜별 스토리 카드 ─────────────────────────────
    st.markdown("<div class='sim-title sim-section'>날짜별 시뮬레이션 스토리</div>",
                unsafe_allow_html=True)
    st.markdown("<p style='color:#666; font-size:0.85rem; margin-bottom:20px;'>"
                "각 날짜마다 <b>어떤 공시·뉴스가 있었고</b>, 그것이 <b>에이전트들을 어떻게 움직였는지</b>를 보여줍니다.</p>",
                unsafe_allow_html=True)

    for idx, d in enumerate(valid):
        seed    = d.get("seed", {})
        result  = d.get("result", {})
        val_ev  = d.get("validation", {}).get("evaluations", {})

        date     = d["issue_date"]
        sent     = seed.get("sentiment", "neutral")
        impact   = seed.get("impact_level", "medium")
        itype    = seed.get("issue_type", "기타") or "기타"
        summary  = seed.get("summary", "") or ""
        disc_cnt = seed.get("raw_disclosure_count", 0)

        # 원문 기사/공시 (새 데이터) + key_points 이월 분리 (구 데이터 호환)
        raw_articles    = seed.get("raw_articles", []) or []
        raw_disclosures = seed.get("raw_disclosures", []) or []
        raw_kps         = seed.get("key_points", []) or []
        carryover_kp    = next((kp for kp in raw_kps if str(kp).startswith("[전일")), None)

        pred     = result.get("prediction", "—")
        buy_p    = result.get("buy_pressure", 0)
        sell_p   = result.get("sell_pressure", 0)
        hold_p   = result.get("hold_pressure", 0)
        net_p    = result.get("net_pressure", 0)
        strength = result.get("strength", "-")
        disagree = result.get("disagreement")
        t_break  = result.get("type_breakdown", {})

        ev_1d   = val_ev.get("1d", {})
        chg_1d  = ev_1d.get("actual_change_pct")
        ok_1d   = ev_1d.get("is_correct")

        # 예측 색상
        pred_cls = "pred-up" if pred=="상승" else "pred-down" if pred=="하락" else "pred-hold"
        pred_sym = "▲" if pred=="상승" else "▼" if pred=="하락" else "━"

        # 태그
        sent_tag   = SENT_TAG.get(sent, "")
        impact_tag = IMPACT_TAG.get(impact, "")

        # 실제 결과 표시
        if chg_1d is not None:
            chg_color = "#00a854" if chg_1d >= 0 else "#d93025"
            chg_sign  = "+" if chg_1d >= 0 else ""
            result_html = f"""
<div style='background:#f9f9f9; border-radius:6px; padding:10px 14px; margin-top:10px;
            border-left:3px solid {"#00a854" if ok_1d else "#d93025"};'>
  <span style='font-size:0.72rem; color:#888; font-family:IBM Plex Mono,monospace;'>
    실제 1일 등락
  </span><br>
  <span style='font-size:1.2rem; font-weight:700; color:{chg_color};
               font-family:IBM Plex Mono,monospace;'>
    {chg_sign}{chg_1d:.2f}%
  </span>
  <span style='margin-left:10px; font-size:0.85rem;
               color:{"#00a854" if ok_1d else "#d93025"};'>
    {"✓ 예측 적중" if ok_1d else "✗ 예측 빗나감"}
  </span>
</div>"""
        else:
            result_html = "<div style='color:#aaa; font-size:0.8rem; margin-top:10px;'>실제 등락 데이터 없음</div>"

        # 에이전트 대표 발언
        decisions = d.get("final_decisions", [])
        tmap = {"retail":"개인","day_trader":"단타","institutional":"기관","value_investor":"가치"}
        voice_rows = {"매수":[], "매도":[], "관망":[]}
        for dec in decisions:
            act = dec.get("action","관망")
            if act in voice_rows and dec.get("reason") and len(voice_rows[act]) < 2:
                voice_rows[act].append({
                    "type": tmap.get(dec.get("persona_type",""),""),
                    "reason": dec.get("reason","")[:100],
                    "conf": float(dec.get("confidence",0.5)),
                })

        voices_html = ""
        for act, color_v in [("매수","#00a854"),("매도","#d93025"),("관망","#b07d00")]:
            for v in voice_rows[act]:
                voices_html += f"""
<div style='border-left:3px solid {color_v}; padding:8px 12px; margin:5px 0;
            background:#fafafa; border-radius:0 6px 6px 0;'>
  <span style='font-size:0.68rem; color:{color_v}; font-family:IBM Plex Mono,monospace; font-weight:600;'>
    {act} &nbsp;·&nbsp; {v["type"]} &nbsp;·&nbsp; 확신도 {v["conf"]:.0%}
  </span><br>
  <span style='font-size:0.8rem; color:#333; line-height:1.5;'>
    {v["reason"]}
  </span>
</div>"""
        if not voices_html:
            voices_html = "<div style='color:#aaa; font-size:0.78rem;'>발언 데이터 없음</div>"

        # 타입별 반응 바지
        type_summary_html = ""
        type_labels_l = {"retail":"개인","day_trader":"단타","institutional":"기관","value_investor":"가치"}
        for pt, pl in type_labels_l.items():
            tb = t_break.get(pt, {})
            if not tb.get("total"):
                continue
            tot = tb["total"]
            dom = max(["매수","매도","관망"], key=lambda x: tb.get(x,0))
            dom_pct = tb.get(dom,0) / tot * 100
            dom_col = "#00a854" if dom=="매수" else "#d93025" if dom=="매도" else "#888"
            type_summary_html += f"""
<div style='display:inline-block; margin:3px 5px 3px 0; padding:4px 12px;
            background:#f5f5f5; border-radius:20px; font-size:0.75rem;
            border:1px solid #e0e0e0;'>
  <span style='color:#555;'>{pl}</span>
  <span style='color:{dom_col}; font-weight:700; font-family:IBM Plex Mono,monospace;
               margin-left:6px;'>{dom} {dom_pct:.0f}%</span>
</div>"""

        # ── 뉴스 기사 카드 HTML ──────────────────────────────
        if raw_articles:
            article_items = []
            for a in raw_articles[:6]:
                title   = a.get("title", "")
                desc    = a.get("description", "")
                press   = a.get("press", "")
                art_dt  = a.get("date", "")
                url     = a.get("url", "")
                link_start = f"<a href='{url}' target='_blank' style='text-decoration:none;'>" if url else ""
                link_end   = "</a>" if url else ""
                article_items.append(f"""
<div style='padding:10px 0; border-bottom:1px solid #f0f0f0;'>
  <div style='font-size:0.7rem; color:#888; margin-bottom:4px;
              font-family:IBM Plex Mono,monospace;'>
    📰 {press} &nbsp;·&nbsp; {art_dt}
  </div>
  {link_start}
  <div style='font-size:0.85rem; font-weight:600; color:#1a1a2e;
              line-height:1.5; margin-bottom:4px;'>{title}</div>
  {link_end}
  <div style='font-size:0.8rem; color:#555; line-height:1.6;'>{desc}</div>
</div>""")
            news_html = "".join(article_items)
        else:
            news_html = "<div style='color:#aaa; font-size:0.8rem; padding:8px 0;'>수집된 뉴스 기사 없음 (과거 날짜 또는 API 미수집)</div>"

        # ── 공시 리스트 HTML ─────────────────────────────────
        if raw_disclosures:
            disc_items = []
            for disc in raw_disclosures:
                disc_items.append(f"""
<div style='padding:6px 0; border-bottom:1px solid #f5f5f5;
            font-size:0.8rem; color:#333; line-height:1.5;'>
  <span style='color:#c62828; font-size:0.68rem; font-family:IBM Plex Mono,monospace;
               margin-right:6px;'>📋 공시</span>
  <span style='font-weight:600;'>{disc.get("title","")}</span>
  <span style='color:#aaa; font-size:0.72rem; margin-left:6px;'>{disc.get("date","")}</span>
</div>""")
            disc_html = "".join(disc_items)
        else:
            disc_html = "" 

        # 전일 이월 컨텍스트 (있을 때만 표시)
        carryover_html = ""
        if carryover_kp:
            # 전일 이월 텍스트에서 날짜/예측/분위기 핵심만 추출
            lines = str(carryover_kp).replace("[전일","").split("\n")
            co_title = lines[0].strip().strip("]").strip() if lines else ""
            co_body  = " · ".join(l.strip() for l in lines[1:] if l.strip())[:120]
            carryover_html = f"""
<div style='background:#f0f4ff; border-radius:6px; padding:8px 12px; margin-top:8px;
            font-size:0.75rem; color:#555; border-left:3px solid #2a5298;'>
  <span style='font-family:IBM Plex Mono,monospace; color:#2a5298; font-weight:600;'>
    📅 전일 이월 {co_title}
  </span><br>
  <span>{co_body}</span>
</div>"""

        # 카드 전체 레이아웃
        st.markdown(f"""
<div style='background:#fff; border:1px solid #e0e0e0; border-radius:12px;
            padding:0; margin-bottom:28px; overflow:hidden;
            box-shadow:0 3px 12px rgba(0,0,0,0.07);'>

  <!-- 헤더 바 -->
  <div style='background:#1a1a2e; padding:14px 22px; display:flex;
              justify-content:space-between; align-items:center;'>
    <div>
      <span style='font-family:IBM Plex Mono,monospace; color:#fff;
                   font-size:1rem; font-weight:700;'>Day {idx+1} &nbsp; {date}</span>
      <span style='margin-left:14px; font-family:IBM Plex Mono,monospace;
                   color:#7ecfff; font-size:0.82rem; font-weight:600;'>{itype}</span>
    </div>
    <div>{sent_tag} {impact_tag}
      <span style='font-size:0.7rem; color:#aaa; font-family:IBM Plex Mono,monospace;
                   margin-left:8px;'>공시 {disc_cnt}건</span>
    </div>
  </div>

  <div style='padding:22px; display:grid; grid-template-columns:1.1fr 0.9fr 1fr; gap:24px;'>

    <!-- 컬럼1: 공시·뉴스 내용 -->
    <div>
      <div style='font-size:0.65rem; color:#888; text-transform:uppercase;
                  letter-spacing:2px; margin-bottom:12px; font-family:IBM Plex Mono,monospace;
                  border-bottom:1px solid #eee; padding-bottom:6px;'>
        📰 공시 · 뉴스 헤드라인
      </div>
      <div style='font-size:0.85rem; color:#333; line-height:1.7;
                  background:#fafafa; border-radius:6px; padding:10px 14px;
                  border-left:3px solid #1a1a2e; margin-bottom:10px;'>
        {summary}
      </div>
      {news_html}
      {disc_html}
      {carryover_html}
    </div>

    <!-- 컬럼2: 에이전트 반응 -->
    <div>
      <div style='font-size:0.65rem; color:#888; text-transform:uppercase;
                  letter-spacing:2px; margin-bottom:12px; font-family:IBM Plex Mono,monospace;
                  border-bottom:1px solid #eee; padding-bottom:6px;'>
        🤖 에이전트 반응
      </div>
      <div style='margin-bottom:12px;'>{type_summary_html}</div>
      <div style='font-size:0.7rem; color:#888; margin:12px 0 6px;'>대표 발언</div>
      {voices_html}
    </div>

    <!-- 컬럼3: 집계 결과 -->
    <div>
      <div style='font-size:0.68rem; color:#888; text-transform:uppercase;
                  letter-spacing:2px; margin-bottom:10px; font-family:IBM Plex Mono,monospace;'>
        📊 시뮬레이션 결과
      </div>

      <div style='display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px;'>
        <div style='background:#f5f5f5; border-radius:8px; padding:10px; text-align:center;'>
          <div style='font-size:0.65rem; color:#888; margin-bottom:4px;'>AI 예측</div>
          <div class='{pred_cls}' style='font-family:IBM Plex Mono,monospace;
                                          font-size:1.3rem;'>{pred_sym} {pred}</div>
        </div>
        <div style='background:#f5f5f5; border-radius:8px; padding:10px; text-align:center;'>
          <div style='font-size:0.65rem; color:#888; margin-bottom:4px;'>신호 강도</div>
          <div style='font-family:IBM Plex Mono,monospace; font-size:1.1rem;
                      font-weight:700; color:#2a5298;'>{strength}</div>
        </div>
      </div>

      <!-- 압력 게이지 바 -->
      <div style='margin-bottom:10px;'>
        <div style='display:flex; justify-content:space-between; font-size:0.72rem;
                    color:#888; margin-bottom:4px;'>
          <span>매수 {buy_p:.0f}%</span>
          <span>관망 {hold_p:.0f}%</span>
          <span>매도 {sell_p:.0f}%</span>
        </div>
        <div style='height:10px; border-radius:5px; overflow:hidden; background:#eee;
                    display:flex;'>
          <div style='width:{buy_p:.0f}%; background:#00a854;'></div>
          <div style='width:{hold_p:.0f}%; background:#aaa;'></div>
          <div style='width:{sell_p:.0f}%; background:#d93025;'></div>
        </div>
        <div style='font-size:0.72rem; color:#555; margin-top:4px; text-align:right;
                    font-family:IBM Plex Mono,monospace;'>
          순압력 {net_p:+.1f}%p
          {"&nbsp;|&nbsp; 불일치 " + f"{disagree:.2f}" if disagree is not None else ""}
        </div>
      </div>

      {result_html}
    </div>

  </div>
</div>
""", unsafe_allow_html=True)

    # ── 3. 전체 흐름 요약 차트 ────────────────────────────
    st.markdown("<div class='sim-title sim-section'>전체 흐름 요약 — 씨드 감성 vs 에이전트 반응 vs 실제</div>",
                unsafe_allow_html=True)

    fig_sum = go.Figure()

    # 감성 선
    fig_sum.add_trace(go.Scatter(
        x=seed_dates, y=[SENT_NUM.get(s,0) for s in sentiments],
        mode="lines+markers", name="씨드 감성",
        line=dict(color="#2a5298", width=2.5, dash="dot"),
        marker=dict(size=9, color=[SENT_COL_L.get(s,"#b07d00") for s in sentiments]),
        yaxis="y",
    ))
    # 순압력 선
    fig_sum.add_trace(go.Scatter(
        x=seed_dates, y=[d["result"].get("net_pressure",0) for d in valid],
        mode="lines+markers", name="에이전트 순압력",
        line=dict(color="#e65100", width=2.5),
        marker=dict(size=9, color="#e65100"),
        yaxis="y2",
    ))
    # 실제 등락 바
    act_vals = [d.get("validation",{}).get("evaluations",{}).get("1d",{}).get("actual_change_pct") for d in valid]
    fig_sum.add_trace(go.Bar(
        x=seed_dates,
        y=[v if v is not None else 0 for v in act_vals],
        name="실제 1일 등락",
        marker_color=["#00a854" if (v or 0)>=0 else "#d93025" for v in act_vals],
        opacity=0.5,
        yaxis="y2",
    ))
    # 예측 마커
    fig_sum.add_trace(go.Scatter(
        x=seed_dates,
        y=[d["result"].get("net_pressure",0) for d in valid],
        mode="markers+text",
        marker=dict(symbol="diamond", size=16,
                    color=[("#00a854" if p=="상승" else "#d93025" if p=="하락" else "#b07d00") for p in preds],
                    line=dict(width=2, color="#1a1a2e")),
        text=preds, textposition="top center",
        textfont=dict(size=10, family="IBM Plex Mono", color="#1a1a2e"),
        name="AI 예측",
        yaxis="y2",
    ))
    fig_sum.add_hline(y=0, line_color="#888", line_dash="dash", line_width=1)

    fig_sum.update_layout(
        height=380,
        barmode="overlay",
        yaxis=dict(title="감성 (-1 부정 ~ +1 긍정)", tickvals=[-1,0,1],
                   ticktext=["부정","중립","긍정"], gridcolor="#bbb",
                   range=[-1.8, 1.8]),
        yaxis2=dict(title="순압력 / 등락 (%)", overlaying="y", side="right",
                    gridcolor="rgba(0,0,0,0)", ticksuffix="%"),
        legend=dict(orientation="h", y=1.1),
        **PL,
    )
    st.plotly_chart(fig_sum, use_container_width=True)

    # ── 4. 이슈 유형 × 에이전트 반응 히트맵 ──────────────
    st.markdown("<div class='sim-title sim-section'>이슈 유형별 에이전트 반응 패턴</div>",
                unsafe_allow_html=True)

    issue_agent: dict = {}
    for d in valid:
        it = d.get("seed",{}).get("issue_type","기타") or "기타"
        tb = d["result"].get("type_breakdown", {})
        if it not in issue_agent:
            issue_agent[it] = {"buy_sum":0,"sell_sum":0,"hold_sum":0,"cnt":0}
        for ptype in ["retail","day_trader","institutional","value_investor"]:
            t = tb.get(ptype,{})
            tot = t.get("total",0) or 1
            issue_agent[it]["buy_sum"]  += t.get("매수",0)/tot*100
            issue_agent[it]["sell_sum"] += t.get("매도",0)/tot*100
            issue_agent[it]["hold_sum"] += t.get("관망",0)/tot*100
            issue_agent[it]["cnt"] += 1

    if issue_agent:
        ia_labels = list(issue_agent.keys())
        buy_avgs  = [issue_agent[k]["buy_sum"] /max(issue_agent[k]["cnt"],1) for k in ia_labels]
        sell_avgs = [issue_agent[k]["sell_sum"]/max(issue_agent[k]["cnt"],1) for k in ia_labels]
        hold_avgs = [issue_agent[k]["hold_sum"]/max(issue_agent[k]["cnt"],1) for k in ia_labels]

        fig_ia = go.Figure()
        fig_ia.add_trace(go.Bar(name="평균 매수%", x=ia_labels, y=buy_avgs,
                                marker_color="#00a854", opacity=0.85))
        fig_ia.add_trace(go.Bar(name="평균 관망%", x=ia_labels, y=hold_avgs,
                                marker_color="#aaaaaa", opacity=0.7))
        fig_ia.add_trace(go.Bar(name="평균 매도%", x=ia_labels, y=sell_avgs,
                                marker_color="#d93025", opacity=0.85))
        fig_ia.update_layout(
            title="이슈 유형별 평균 에이전트 반응",
            barmode="group", height=320,
            xaxis=dict(gridcolor="#bbb"),
            yaxis=dict(ticksuffix="%", gridcolor="#bbb"),
            legend=dict(orientation="h", y=1.1),
            **PL,
        )
        st.plotly_chart(fig_ia, use_container_width=True)