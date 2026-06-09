# AgentFlow — Multi-Agent Stock Market Simulator

**[🇰🇷 한국어 README](./README.md)**

**Live Demo:** https://agentflow-pkw.streamlit.app/

> **Predicting stock price direction by simulating investor collective behavior with LLMs**
> Portfolio Project | Python · Ollama (phi4) · Streamlit · DART · Public Data Portal

---

## Overview

AgentFlow is a multi-agent system that simulates stock market participants' collective decision-making using LLM reasoning — without any ML training.

**The core hypothesis:** If we simulate how diverse investors react to disclosures and news as a group, we can predict short-term stock price direction.

### Why Not Traditional ML?

Conventional stock prediction models (LSTM, XGBoost, etc.) have two fundamental limitations:

1. **Blind to new events** — Models cannot respond to disclosures, news, or surprise events not seen in training data (earnings surprises, sudden CEO changes, regulatory announcements).
2. **Ignore market psychology** — Stock prices are the aggregate of human buy/sell decisions. The same negative news triggers completely different reactions depending on whether it was anticipated or not. Numerical pattern learning cannot capture this.

### AgentFlow's Approach

- **Situation understanding over pattern learning**: Ask LLM directly — "How would a retail investor react to this disclosure/news right now?"
- **Collective psychology simulation**: 20 agents with different investment styles independently judge the same information, then re-judge after seeing each other's behavior
- **Real data-driven**: Real-time collection of DART disclosures, Naver news, and public stock price data as LLM seeds

---

## System Architecture

### Full Pipeline

```
[External Data Collection]
   DART Disclosures ──┐
   Naver News       ──┼──▶  [Seed Parser / LLM Summary]  ──▶  {issue type, sentiment, impact, key points}
   Stock Price Data ──┘

                    ┌────────────────────────────┐
                    │      AgentFlow Engine       │
                    │                             │
                    │  Round 1 (Pre-market)       │  ← No social context, independent judgment
                    │  ┌───────────────────────┐  │    (ThreadPoolExecutor parallel)
                    │  │ Retail×5  Inst×5      │  │
                    │  │ DayTr×5   Value×5     │  │
                    │  └──────────┬────────────┘  │
                    │             │               │
                    │   InteractionEngine         │  ← Generate crowd pressure signal
                    │             │               │
                    │  Round 2 (During market)    │  ← Re-judge with crowd signal
                    │  ┌───────────────────────┐  │
                    │  │ Same 20 agents        │  │
                    │  └──────────┬────────────┘  │
                    │             │               │
                    │   ResultAggregator          │  ← KOSPI-weighted, net-based verdict
                    └────────────┬───────────────-┘
                                 │
                    Prediction (UP / DOWN / NEUTRAL)
                    Buy pressure% / Sell pressure%
                                 │
                    ┌────────────▼──────────────┐
                    │   Validator               │
                    │   Actual 1d/5d/20d change │
                    │   vs prediction           │
                    └───────────────────────────┘
```

### Key Design Decisions

**Time Engine** — Simulates actual market time flow (pre-market → during market). Information changes each round, and crowd behavior influences the next round.

**Social Interaction** — `InteractionEngine` aggregates Round 1 results and converts them into text signals like "🔴 Strong selling (70% sell vs 10% buy)". LLM agents read crowd pressure expressed in numbers and emojis and adjust their judgment.

**Persona Diversity** — 4 investor types (retail/institutional/day-trader/value) × 5 each = 20 total. Each agent has independent `bias_val` (sentiment bias) and `base_tendency` (default stance), leading to different conclusions from the same information.

**Multi-day Simulation** — `run_continuous.py` injects the previous day's simulation results (buy/sell pressure, prediction, issue summary) into the next day's seed. Agents remember their previous decisions via SQLite memory.

---

## Project Structure

```
AgentFlow/
├── config/settings.py              # Global settings (agent count, thresholds)
├── llm/client.py                   # Ollama ↔ OpenAI abstraction layer
├── data/
│   ├── collector/dart_collector.py  # DART API (corpCode.xml ZIP parsing)
│   ├── collector/news_collector.py  # Naver Search API
│   ├── collector/price_collector.py # Public Data Portal stock API
│   └── seed_parser.py               # Multi-source → simulation seed LLM parsing
├── agents/
│   ├── base_agent.py                # Agent base class (decide method)
│   ├── persona_generator.py         # LLM-based dynamic persona generation
│   ├── agent_factory.py             # Persona cache load/generate
│   ├── memory/agent_memory.py       # SQLite decision history storage
│   └── personas/                    # 4 investor type factories
├── simulation/
│   ├── engine.py                    # Time Engine (2 rounds, parallel execution)
│   ├── interaction.py               # Crowd pressure signal generation
│   └── aggregator.py                # KOSPI-weighted aggregation, final prediction
├── evaluation/validator.py          # Accuracy validation vs actual prices
├── dashboard/app.py                 # Streamlit multi-stock dashboard
├── db/
│   ├── store.py                     # File-based DB
│   ├── runs/                        # Full run result JSON
│   └── daily/                       # Date-indexed fast lookup JSON
├── main.py                          # Single stock single day run
├── run_continuous.py                # Date range continuous simulation
├── run_multi_stock.py               # Multi-stock batch run
├── generate_report.py               # HTML report generation
└── stocks_config.json               # Stock configuration
```

---

## Key Technical Techniques

### Aggregation Algorithm

```python
# Investor type weights — reflects KOSPI actual trading volume ratios
TYPE_WEIGHTS = {
    "retail":         1.8,
    "day_trader":     1.6,
    "value_investor": 1.2,
    "institutional":  1.0,
}

# net (buy% - sell%) based prediction
net = buy_pct - sell_pct
if   net >= 45: → Strong UP
elif net >= 25: → UP
elif net <= -45: → Strong DOWN
elif net <= -25: → DOWN
else:            → NEUTRAL

# HHI-based Disagreement Score
hhi = buy_share² + sell_share² + hold_share²
disagreement = 1.0 - hhi   # 0.0 = full consensus, ~0.667 = full split
```

### Defensive JSON Parsing

LLMs don't always return valid JSON. Every parser defends against code blocks, surrounding text, and array wrapping:

```python
cleaned = raw.strip()
start = cleaned.find("{")
end   = cleaned.rfind("}") + 1
cleaned = cleaned[start:end]
result = json.loads(cleaned)
if isinstance(result, list):
    result = result[0] if result else {}
```

### Parallel Execution

Python GIL prevents CPU parallelism, but overlapping Ollama API I/O wait times yields real speedup:

```python
with ThreadPoolExecutor(max_workers=8) as executor:
    future_to_idx = {
        executor.submit(agent.decide, sim_id, round_num, ...): i
        for i, agent in enumerate(self.agents)
    }
```

~2–3× faster than sequential for 20 agents. Set `OLLAMA_NUM_PARALLEL=4` for Ollama to process up to 4 requests simultaneously.

### News Collection Strategy

| Condition | Method |
|-----------|--------|
| Within 7 days | Naver API (`sort=sim`, pubDate filter) |
| Over 7 days | Web crawling (`ds`/`de` date params) |

**Key rules:**
- Search query: `"{stock name} 주식"` — focus on stock-related news
- `sort=sim` (relevance) — prioritize related articles
- **Exclude simulation day itself; use only -1d to -7d** — prevent future data leakage

---

## Results

| Metric | Value |
|--------|-------|
| 1-day directional accuracy | **73%** (backtest) |
| Speed gain vs sequential | **2–3×** (ThreadPoolExecutor) |
| API calls per stock | **3 total** (DART + News + Price, pre-fetched) |

Dashboard warning banner auto-displays when `disagreement ≥ 0.45` — the system explicitly signals when predictions are unreliable.

---

## Installation & Usage

### Environment Setup (.env)

```bash
LLM_MODE=ollama
OLLAMA_MODEL=phi4:latest
OLLAMA_BASE_URL=http://localhost:11434/v1

# DART
DART_API_KEY=your_key

# Public Data Portal — ⚠️ Use DECODED key (with slashes and equals signs as-is)
DATA_GO_KR_API_KEY=62QrF8XBi8pUjF4C2bxLb.../DmQAC6...==

# Naver Search API
NAVER_CLIENT_ID=your_key
NAVER_CLIENT_SECRET=your_key
```

### Run Commands

```bash
pip install -r requirements.txt

# Single stock, single day
python main.py --corp SK하이닉스 --ticker 000660 --date 2024-01-15

# Date range continuous simulation
python run_continuous.py --corp SK하이닉스 --ticker 000660 --start 2024-01-10 --end 2024-01-20

# Last N days
python run_continuous.py --corp 삼성전자 --ticker 005930 --days 7

# Multi-stock batch (based on stocks_config.json)
python run_multi_stock.py --days 5

# Dashboard
streamlit run dashboard/app.py

# HTML report
python generate_report.py
```

---

## Dashboard Views

**📊 Multi-Stock Overview**
- Net pressure bar charts per stock, 1-day accuracy bars, sector sentiment distribution
- Prediction vs actual summary table with stock/prediction/verdict filters

**🔍 Stock Detail**
- Date-wise buy/sell/hold pressure stacked bar + actual change subplot
- **Prediction direction vs actual line chart**: AI prediction diamonds + actual change line
- **Agent confidence histogram**: Decision-colored overlay + type-wise average confidence dual axis
- **Agent quote cards**: Top 3 representative quotes per buy/sell/hold
- **Disagreement warning banner**: Auto-displays orange warning when `disagreement ≥ 0.45`
- **Issue type accuracy**: 1-day accuracy bar by disclosure type

**📈 Backtest Analysis**
- Overall 1d/5d/20d accuracy summary
- Average actual change by predicted direction ("When UP predicted, avg +X%")
- Reliability curve by net pressure interval (with 50% random baseline)
- Stock × period accuracy heatmap
- **Stability Score** — quantifies LLM randomness

---

## Selected Troubleshooting (15 issues documented)

| # | Issue | Root Cause | Fix |
|---|-------|-----------|-----|
| 1 | DART API 404 | Expected REST search, actual is ZIP download | Download corpCode.xml ZIP → XML parse → memory dict |
| 2 | phi4 returns tool_call format | Ollama serving phi4 with tool_call mode active | Use base model explicitly; independent JSON parsing in each module |
| 3 | FinanceDataReader/pykrx blocked | Yahoo Finance / KRX server blocks | Replaced with Korea Public Data Portal API |
| 4 | API 401 despite valid key | Encoded key → requests double-encodes | Use decoded key (with raw slashes and equals signs) |
| 5 | All agents select "hold" | Analyst role too optimistic; bias range too narrow | Changed to "cold risk analyst" role; expanded bias range to ±0.25 |
| 6 | Rounds 1-3 identical decisions | Crowd signal too weak; no previous round memory injection | Emoji+number crowd signal; inject "my last round decision" into prompt |
| 7 | `srtnCd` returns 46,000 stocks | `srtnCd` is response field, not request param | Changed to `likeSrtnCd` |
| 8 | News always shows today's articles | Naver API returns latest N by default | 7-day window with pubDate filter; crawling for older dates |

---

## Tech Stack

| Area | Technology |
|------|-----------|
| LLM | Ollama (phi4:latest) / OpenAI API |
| Language | Python 3.11 |
| Parallelism | `concurrent.futures.ThreadPoolExecutor` |
| Agent Memory | SQLite (`sqlite3`) |
| Stock Data | Korea Public Data Portal API |
| Disclosure Data | DART Electronic Disclosure API |
| News | Naver Search API |
| Dashboard | Streamlit + Plotly |
| Result Storage | File-based JSON DB |
| Config | `python-dotenv` |

---

## References

- [OASIS: Open Agent Social Interaction Simulations](https://arxiv.org/abs/2411.11581)
- DART Electronic Disclosure API: https://opendart.fss.or.kr
- Korea Public Data Portal: https://www.data.go.kr

---

*Built with Ollama phi4 + Python — AI/Data Engineering Portfolio Project*
