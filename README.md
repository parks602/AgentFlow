# AgentFlow — 다중 에이전트 주식 시장 시뮬레이터

> **LLM 기반 투자자 행동 시뮬레이션으로 주가 방향을 예측한다**  
> AI/데이터 직군 포트폴리오 프로젝트 | Python · Ollama (phi4) · Streamlit · DART · 공공데이터포털

---

## 목차

1. [프로젝트 목적 — AI 학습의 한계를 넘어서](#1-프로젝트-목적)
2. [시스템 설계 — 흐름과 중점](#2-시스템-설계)
3. [아키텍처 구조](#3-아키텍처-구조)
4. [핵심 기술 기법](#4-핵심-기술-기법)
5. [결과 확인 방법](#5-결과-확인-방법)
6. [설치 및 실행](#6-설치-및-실행)
7. [시행착오 전체 기록](#7-시행착오-전체-기록)
8. [향후 개선 방향](#8-향후-개선-방향)

---

## 1. 프로젝트 목적

### 기존 머신러닝 주가 예측의 한계

전통적인 주가 예측 모델(LSTM, XGBoost 등)은 **과거 가격 패턴**을 학습해 미래를 예측한다.
이 접근법의 근본적인 한계는 두 가지다.

1. **새로운 이벤트에 무력하다** — 모델은 학습 데이터에 없던 공시·뉴스·돌발 이벤트에 대응할 수 없다. 기업 실적 어닝 서프라이즈, 갑작스런 CEO 교체, 정부 규제 발표 등은 패턴으로 학습되지 않는다.

2. **시장 참여자의 심리를 무시한다** — 주가는 결국 사람들이 매수/매도 버튼을 누르는 행위의 총합이다. 같은 악재라도 "이미 알려진 악재"와 "깜짝 악재"에 시장이 반응하는 방식은 전혀 다르다. 수치 패턴 학습만으로는 이 차이를 포착할 수 없다.

### AgentFlow의 접근

AgentFlow는 **LLM의 추론 능력**을 활용해 이 한계를 우회한다.

- **패턴 학습 대신 상황 이해**: LLM에게 "지금 이 공시/뉴스를 받은 개인투자자라면 어떻게 행동할까?"를 직접 물어본다
- **집단 심리 시뮬레이션**: 서로 다른 투자 성향을 가진 20명의 에이전트가 각자 독립적으로 판단하고, 서로의 행동을 보면서 재판단한다
- **실제 데이터 기반**: DART 전자공시, 네이버 뉴스, 공공데이터포털 주가 API를 실시간으로 수집해 씨드로 사용한다

> **핵심 가설**: 공시·뉴스를 읽은 다양한 성향의 투자자들이 집단으로 어떤 결정을 내리는지를 시뮬레이션하면, 단기 주가 방향을 예측할 수 있다.

이 프로젝트는 **"AI가 시장 참여자의 집합적 판단을 에뮬레이션할 수 있는가"** 라는 질문에 대한 실험이다.

---

## 2. 시스템 설계

### 전체 파이프라인

```
[외부 데이터 수집]
   DART 전자공시  ──┐
   네이버 뉴스    ──┼──▶  [씨드 파서 / LLM 요약]  ──▶  {이슈 유형, 감성, 영향도, 핵심 포인트}
   공공데이터 주가 ──┘

                    ┌───────────────────────────┐
                    │      AgentFlow Engine      │
                    │                            │
                    │  라운드 1 (장 시작 전)      │
                    │  ┌──────────────────────┐  │  ← 사회적 맥락 없음, 독립 판단
                    │  │ 개인×5  기관×5        │  │    (ThreadPoolExecutor 병렬)
                    │  │ 단타×5  가치×5        │  │
                    │  └─────────┬────────────┘  │
                    │            │               │
                    │   InteractionEngine        │  ← 군중 압력 텍스트 신호 생성
                    │            │               │
                    │  라운드 2 (장 중)           │
                    │  ┌──────────────────────┐  │  ← 직전 결정 + 군중 신호 반영
                    │  │ 동일 20명 재판단      │  │
                    │  └─────────┬────────────┘  │
                    │            │               │
                    │   ResultAggregator         │  ← KOSPI 가중치, net 기반 판정
                    └───────────┬───────────────-┘
                                │
                         예측 결과 (상승/하락/보합)
                         매수압력% / 매도압력%
                                │
                    ┌───────────▼──────────────┐
                    │   Validator (검증)        │
                    │   실제 1일/5일/20일 등락   │
                    │   vs 예측 비교            │
                    └──────────────────────────┘
```

### 설계 중점

**1. Time Engine — 장중 시간 흐름 구현**
단순히 LLM에게 "매수/매도?" 를 묻는 것이 아니라, 실제 주식 시장의 시간 흐름(장 시작 전 → 장 중)을 모방한다. 라운드마다 에이전트가 받는 정보가 달라지며, 군중의 행동이 다음 라운드에 영향을 미친다.

**2. 사회적 상호작용 — 군중심리 구현**
`InteractionEngine`이 라운드 1의 결과를 집계해 "🔴 강한 매도세 (매도 70% vs 매수 10%)" 같은 텍스트 신호로 변환한다. LLM이 수치와 이모지로 표현된 군중 압력을 읽고 자신의 판단을 조정하게 유도한다.

**3. 페르소나 다양성 — 에이전트 이질성 확보**
4가지 투자자 유형(개인/기관/단타/가치) × 5명씩 총 20명. LLM이 각 에이전트의 배경과 성격을 동적으로 생성(`persona_generator.py`)하고 JSON으로 캐시한다. 각 에이전트마다 독립적인 `bias_val`(편향값)과 `base_tendency`(기본 성향)를 부여해 같은 정보를 받아도 다른 결론을 내린다.

**4. 멀티일 연속 시뮬레이션 — 시장 기억 구현**
`run_continuous.py`는 전날 시뮬레이션 결과(매수/매도 압력, 예측 방향, 이슈 요약)를 다음날 씨드에 주입한다. 에이전트들은 SQLite 메모리를 통해 자신이 어제 어떤 결정을 내렸는지 기억한다.

---

## 3. 아키텍처 구조

```
AgentFlow/
├── config/settings.py              # 에이전트 수, 임계값 등 전역 설정
├── llm/client.py                   # Ollama ↔ OpenAI 추상화 레이어
├── data/
│   ├── collector/dart_collector.py  # DART API (corpCode.xml ZIP 파싱)
│   ├── collector/news_collector.py  # 네이버 검색 API
│   ├── collector/price_collector.py # 공공데이터포털 주가 API
│   └── seed_parser.py               # 멀티소스 → 시뮬레이션 씨드 LLM 파싱
├── agents/
│   ├── base_agent.py                # 에이전트 기반 클래스 (decide 메서드)
│   ├── persona_generator.py         # LLM 기반 동적 페르소나 생성
│   ├── agent_factory.py             # 페르소나 캐시 로드/생성
│   ├── memory/agent_memory.py       # SQLite 결정 이력 저장
│   └── personas/                    # 4종 투자자 타입 팩토리
├── simulation/
│   ├── engine.py                    # Time Engine (2라운드, 병렬 실행)
│   ├── interaction.py               # 군중 압력 신호 생성
│   └── aggregator.py                # KOSPI 가중치 집계, 최종 예측
├── evaluation/validator.py          # 실제 주가 대비 정확도 검증
├── dashboard/app.py                 # Streamlit 멀티종목 대시보드
├── db/
│   ├── store.py                     # 파일 기반 DB
│   ├── runs/                        # 전체 실행 결과 JSON
│   └── daily/                       # 날짜별 빠른 조회 JSON
├── main.py                          # 단일 종목 단일일 실행
├── run_continuous.py                # 날짜 범위 연속 시뮬레이션
├── run_multi_stock.py               # 멀티 종목 배치 실행
├── generate_report.py               # HTML 리포트 생성
└── stocks_config.json               # 종목 설정
```

### 집계 알고리즘 (`aggregator.py`)

```python
# 투자자 유형별 가중치 — KOSPI 실거래 비중 반영
TYPE_WEIGHTS = {
    "retail":         1.8,   # 개인투자자 (KOSPI 거래량 비중 높음)
    "day_trader":     1.6,   # 단타트레이더
    "value_investor": 1.2,
    "institutional":  1.0,
}

# net(매수% - 매도%) 기반 예측 판정
net = buy_pct - sell_pct
if   net >= 45: → 강한 상승
elif net >= 25: → 상승
elif net <= -45: → 강한 하락
elif net <= -25: → 하락
else:            → 보합

# 의견 불일치 지수 — HHI(허핀달-허쉬만) 역산
# 0.0 = 전원 일치, ~0.667 = 완전 3등분
hhi = buy_share² + sell_share² + hold_share²
disagreement = 1.0 - hhi

# 평균 확신도
confidence_avg = mean([agent.confidence for agent in decisions])
```

반환 딕셔너리에 `disagreement`, `confidence_avg`, `strength`("강"/"약"/"-") 포함.

---

## 4. 핵심 기술 기법

### 4-1. LLM 추상화 레이어

`.env` 파일 한 줄(`LLM_MODE=ollama|openai`)로 로컬 Ollama와 OpenAI API를 전환한다.
포트폴리오 데모 시에는 OpenAI로, 개발 중에는 로컬 phi4로 동일한 인터페이스를 사용한다.

```python
# llm/client.py — Ollama를 OpenAI 호환 엔드포인트로 래핑
self.client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)
self.model = os.getenv("OLLAMA_MODEL", "phi4:latest")
```

### 4-2. JSON 강제 파싱 — 방어적 LLM 응답 처리

LLM이 항상 올바른 JSON을 반환하지는 않는다. 코드블록, 앞뒤 설명 텍스트, 배열 래핑 등을 모두 방어한다.

```python
# { } 구간만 추출 → list 방어
cleaned = raw.strip()
start = cleaned.find("{")
end   = cleaned.rfind("}") + 1
cleaned = cleaned[start:end]
result = json.loads(cleaned)
if isinstance(result, list):
    result = result[0] if result else {}
```

`seed_parser.py`와 `base_agent.py` 각각 독립적으로 파싱. `client.py`에만 의존하지 않는 이중 방어 구조.

### 4-3. 페르소나별 편향 씨드

같은 공시를 받아도 에이전트마다 다른 결론이 나오도록, 두 가지 독립적인 편향 파라미터를 부여한다.

```python
# base_agent.py
self._bias_val = random.uniform(-0.25, 0.25)   # 감성 편향값
self._base_tendency = persona.get("base_tendency", "neutral")  # 기본 성향

# system_prompt에 직접 반영
f"당신의 감성 편향: {self._bias_val:+.2f} (-1=극도 비관, +1=극도 낙관)"
```

### 4-4. 라운드 간 메모리 주입

에이전트가 자신의 직전 라운드 결정을 기억해 일관성 있는 판단을 유지한다.
같은 `simulation_id`로 SQLite에서 조회하므로, 다른 시뮬레이션 결과와 섞이지 않는다.

```python
# base_agent.py decide() 메서드
recent = self.memory.get_recent(
    self.agent_id, simulation_id=simulation_id, limit=1
)
if recent:
    user_prompt += f"""
=== 나의 직전 라운드 결정 ===
라운드 {recent[0]['round_num']}: {recent[0]['action']}
이유: {recent[0]['reason']}
=========================
"""
```

### 4-5. 군중 압력 신호 설계

이모지 + 수치 텍스트 조합이 LLM이 군중 방향을 더 강하게 인식하게 만든다는 경험적 발견에 기반한다.
기관투자자와 단타트레이더가 강한 방향을 보일 때 ⚠️ 강조 신호를 추가한다.

```python
# interaction.py
if net >= 40:
    crowd_signal = "🟢 강한 매수세 (매수 X% vs 매도 Y%) — 시장이 상승에 베팅 중"
elif net <= -40:
    crowd_signal = "🔴 강한 매도세 (매도 X% vs 매수 Y%) — 패닉셀 분위기"

# 기관/단타가 강한 방향(60% 이상)이면 ⚠️
emphasis = " ⚠️ 강한 신호" if (ptype in ("institutional","day_trader")
                               and dominant != "관망" and pct >= 60) else ""
```

### 4-6. ThreadPoolExecutor 병렬 실행

Python GIL로 CPU 병렬은 불가하지만, Ollama API 호출의 I/O 대기 시간을 겹쳐서 실질적인 속도 향상을 얻는다.

```python
# engine.py
with ThreadPoolExecutor(max_workers=8) as executor:
    future_to_idx = {
        executor.submit(agent.decide, sim_id, round_num, ...): i
        for i, agent in enumerate(self.agents)
    }
    for future in as_completed(future_to_idx):
        decisions[idx] = future.result()
```

20명 에이전트 기준 순차 실행 대비 약 2~3배 빠르다.
`OLLAMA_NUM_PARALLEL=4` 환경변수 설정 시 Ollama 자체에서도 최대 4개 동시 처리.

### 4-7. DART API — ZIP 파싱 방식

DART의 기업 고유번호 조회는 REST API가 아닌 **ZIP 파일 다운로드 후 XML 파싱** 방식이다.
111,000여 개의 전체 기업 목록을 한 번에 받아 메모리 딕셔너리로 캐시한다.

```python
# dart_collector.py
resp = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                    params={"crtfc_key": api_key})
with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
    xml_data = z.read("CORPCODE.xml")
tree = ET.fromstring(xml_data)
# {회사명: corp_code} 딕셔너리로 메모리 캐시
```

### 4-8. 공공데이터포털 주가 API — 범위 조회 + 페이지네이션

`beginBasDt` / `endBasDt` 파라미터로 날짜 범위를 지정해 단일 호출로 여러 날의 데이터를 받는다.
**디코딩 키 사용 필수** — 인코딩 키를 사용하면 `requests`가 이중 URL 인코딩해서 401 오류 발생.

날짜 형식은 반드시 `YYYYMMDD` (하이픈 없음). 종목 필터는 `likeSrtnCd` 파라미터 사용.
`srtnCd`는 응답 필드명이지 요청 파라미터가 아니라서 필터가 적용되지 않아 전체 종목이 반환됨.
`mrktCls` 파라미터는 사용하지 않는다.

```python
# price_collector.py
params = {
    "serviceKey": os.getenv("DATA_GO_KR_API_KEY"),  # 디코딩 키!
    "beginBasDt": start_dt.strftime("%Y%m%d"),       # YYYYMMDD 형식
    "endBasDt":   end_dt.strftime("%Y%m%d"),
    "numOfRows":  100,
    "likeSrtnCd": str(ticker).zfill(6),              # 종목코드 필터 (6자리)
}

# totalCount > 100 이면 자동 페이지네이션
total_count = int(body.get("totalCount", 0))
if total_count > 100:
    for page in range(2, math.ceil(total_count / 100) + 1):
        # 추가 페이지 조회
```

### 4-9. 씨드 파서 — 리스크 분석가 롤

LLM이 공시 요약 시 낙관 편향을 보이는 문제를 해결하기 위해, 롤을 "애널리스트"에서 "냉철한 리스크 분석가"로 변경했다. 주가 하락 추세 시 negative 감성 강제 지시 포함.

```python
# seed_parser.py system_prompt
"당신은 냉철한 리스크 분석가입니다. "
"주가 하락 추세가 확인되면 반드시 negative 감성으로 판단하세요. "
"과도한 낙관론을 경계하세요."
```

### 4-10. 연속 시뮬레이션 — 전일 시장 심리 이월

```python
# run_continuous.py
def build_carry_over_context(prev_result: dict) -> str:
    """전날 결과를 다음날 초기 시장 심리 텍스트로 변환"""
    buy_p  = prev_result["result"]["buy_pressure"]
    sell_p = prev_result["result"]["sell_pressure"]
    pred   = prev_result["result"]["prediction"]
    # 분위기 설명 → 다음날 seed의 key_points에 주입
    return f"[전일({date}) 시장 심리 이월]\n  어제 예측: {pred} ..."
```

### 4-11. 멀티종목 파일 기반 DB

SQLite 없이 JSON 파일로 인덱스/실행결과/날짜별 조회를 분리 저장한다.
서버 없이 포트폴리오 데모 가능.

```
db/
├── index.json                    ← 전체 인덱스 (종목/날짜/정확도 메타)
├── runs/{run_id}.json            ← 전체 실행 결과
└── daily/{ticker}_{date}.json   ← 날짜별 빠른 조회
```

### 4-12. 의견 불일치 지수 (Disagreement Score)

20명 에이전트의 매수/매도/관망 비율이 얼마나 쏠려있는지를 HHI(허핀달-허쉬만 지수)의 역수로 계산한다.
전원 매수면 0.0(완전 일치), 세 방향이 균등하면 ~0.667(완전 분열).

대시보드에서 `disagreement ≥ 0.45`이면 주황색 경고 배너를 표시해 "이 예측은 불확실합니다"를 명시적으로 알린다.
**모델 신뢰도 관리**를 시스템이 스스로 하고 있다는 점이 핵심이다.

```python
hhi = buy_share**2 + sell_share**2 + hold_share**2
disagreement = round(1.0 - hhi, 3)
```

### 4-13. DB latest_only — 최신 실행만 읽기

같은 종목을 여러 번 재실행하면 `index.json`에 과거 실행이 모두 쌓인다.
대시보드가 모든 과거 데이터를 읽으면 속도 저하 + 오래된 예측이 섞이는 문제가 생긴다.

`list_runs(latest_only=True)`와 `get_latest_run_per_ticker()`를 신설해, 항상 ticker당 최신 1건의 run JSON만 로드하도록 강제한다.

```python
def list_runs(latest_only=False):
    if latest_only:
        seen = {}
        for entry in sorted(index, key=lambda x: x["created_at"], reverse=True):
            if entry["ticker"] not in seen:
                seen[entry["ticker"]] = entry
        return list(seen.values())

def get_latest_run_per_ticker():
    # 메타 조회 + run JSON 로드를 단일 호출로 통합
    return [load_run(m["run_id"]) for m in list_runs(latest_only=True)]
```

### 4-14. 백테스트 신뢰도 곡선

단순 정확도(맞음/틀림 %)를 넘어, **순압력 구간별 정확도**를 계산한다.
"순압력이 강할수록 예측이 정확한가?"를 검증하는 신뢰도 곡선으로, 모델의 강점과 한계를 스스로 분석한다.

구간 : `≤-50 / -50~-25 / -25~0 / 0~25 / 25~50 / ≥50`
각 구간의 정확도를 마커 크기(건수)와 색상(정확도)으로 시각화한다.

### 4-15. Stability Score — LLM 랜덤성 정량화

LLM은 같은 입력에도 매번 다른 출력을 낼 수 있다. 이를 방치하면 "운 좋게 맞춘 예측"과 "신뢰할 수 있는 예측"을 구분할 수 없다.

```
Stability Score = (1 - 평균 불일치 지수) × 평균 확신도 × 100
```

복수 실행 데이터가 있으면 예측 일관성을 직접 측정하고, 단일 실행만 있으면 불일치 지수/확신도 분포로 대체 추정한다.

### 4-16. 데이터 사전 일괄 수집 — API 호출 최소화

날짜 범위 시뮬레이션 시 매 날짜마다 API를 개별 호출하면 N일 × 3회 = 3N번 호출이 발생한다.
사전 일괄 수집 구조로 **종목당 항상 3번**(DART 1번 + 뉴스 1번 + 주가 1번)만 호출한다.

```python
# run_continuous.py / run_multi_stock.py
# ── 루프 전 사전 수집 (종목당 1회) ──
disc_range  = dart.get_disclosures_range(corp, start_date, end_date)   # DART 1번
news_range  = news.get_news_range(corp, start_date, end_date)           # 뉴스 1번
price_range = build_market_context_range(corp, start_date, end_date)    # 주가 1번

# ── 날짜 루프 (dict 조회만, 추가 API 호출 없음) ──
for date in dates:
    disclosures   = disc_range.get(date, [])
    news_articles = news_range.get(date, [])
    market_ctx    = price_range.get(date, {})
```

각 수집기에 `_range` 메서드를 추가해 전체 범위를 한 번에 수집하고 날짜별 딕셔너리로 반환한다.

### 4-17. 뉴스 수집 전략 — 날짜별 정확한 기사 할당

| 조건 | 방법 |
|---|---|
| 7일 이내 | 네이버 API (`sort=sim`, pubDate 필터) |
| 7일 초과 | 크롤링 (`ds`/`de` 날짜 파라미터) |

**핵심 규칙 3가지:**
1. 검색어: `"{종목명} 주식"` — 주식 관련 뉴스에 집중
2. `sort=sim` (정확도순) — 관련성 높은 기사 우선
3. **시뮬레이션 당일 제외, -1일 ~ -7일 기사만 사용** — 미래 정보 유입 차단

```python
# 시뮬레이션 날짜 2026-03-10 기준
end_dt   = base_dt - timedelta(days=1)   # 2026-03-09 (전일)
start_dt = base_dt - timedelta(days=7)   # 2026-03-03 (7일 전)
# 2026-03-10 당일 기사는 포함하지 않음
```

### 4-18. 주가 API 파라미터 교정 — likeSrtnCd

`srtnCd`는 응답 JSON의 필드명이고, 요청 파라미터는 `likeSrtnCd`다.
`srtnCd`로 요청하면 필터가 무시되어 **전체 종목 46,000건 이상이 반환**되는 문제가 있었다.

```
srtnCd   → 응답 필드명 (읽기용)
likeSrtnCd → 요청 필터 파라미터 (6자리 종목코드)
mrktCls  → 불필요, 제거
```

### 4-19. 종목 간 에이전트 메모리 격리

멀티 종목 배치 실행 시 에이전트 SQLite 메모리에 이전 종목의 결정이 누적되어
다음 종목 판단에 영향을 주는 **교차 오염** 문제가 있었다.

```python
# run_multi_stock.py — 종목 전환 시 메모리 초기화
for stock in stocks:
    memory.clear_all_agent_history()  # 이전 종목 기억 삭제
    run_stock(corp=stock["corp"], ...)
```

`agent_memory.py`에 `clear_all_agent_history()` 메서드 추가.
연속 시뮬레이션(`run_continuous.py`)은 날짜 간 기억 연속성이 필요하므로 초기화하지 않는다.

### 4-20. 에이전트 주의 집중 요소 (`_attention`) 프롬프트 반영

에이전트 생성 시 6개 요소(가격/거래량/공시/뉴스/업황/밸류에이션) 중 3개를 랜덤으로 부여한다.
이전엔 생성만 하고 프롬프트에 반영하지 않아 에이전트 이질성에 기여하지 못했다.

```python
# base_agent.py
attention_str = " / ".join(self._attention)  # 예: "공시 / 업황 / 가격"
user_prompt += f"""
=== 나의 주요 판단 기준 (이 요소들을 중심으로 분석할 것) ===
{attention_str}
"""
```

같은 정보를 받아도 "공시/업황/가격" 에이전트와 "뉴스/거래량/밸류에이션" 에이전트가
서로 다른 각도로 읽어 더 다양한 의견이 나온다.

---

## 5. 결과 확인 방법

### Streamlit 대시보드

```bash
streamlit run dashboard/app.py
```

3개 뷰로 구성된다.

**📊 전체 종목 비교**
- ticker당 최신 실행 1건만 로드 (`get_latest_run_per_ticker()`)
- 종목별 순압력 바 차트, 1일 정확도 수평 바, 섹터별 심리 분포
- 예측 vs 실제 종합 테이블 (종목·예측·판정 필터)

**🔍 종목 상세**
- 날짜별 매수/매도/관망 압력 스택 바 + 실제 등락 서브플롯
- **예측 방향 vs 실제 라인 차트**: AI 예측 다이아몬드 + 실제 등락선 + 누적 비교
- **에이전트 확신도 히스토그램**: 결정별 색상 오버레이 + 타입별 평균 확신도 이중축
- **에이전트 발언 카드**: 매수/매도/관망 대표 발언 3개씩 컬럼 배치
- **불일치 지수 경고 배너**: `disagreement ≥ 0.45` 시 주황색 경고 자동 표시
- **이슈 유형별 정확도**: 공시 유형별 1일 정확도 바 + 평균 순압력 비교
- 예측 vs 실제 상세 테이블 (1일/5일/20일 탭)

**📈 백테스트 분석**
- 전체 시뮬레이션 1일/5일/20일 정확도 요약
- 예측 방향별 실제 평균 등락 ("상승 예측 시 평균 +X%")
- 강/약 신호별 정확도 비교
- 순압력 구간별 신뢰도 곡선 (랜덤 기준선 50% 함께 표시)
- 종목 × 기간별 정확도 히트맵
- **Stability Score** — LLM 랜덤성 정량화 지표

### HTML 리포트

```bash
python generate_report.py              # 전체 종목
python generate_report.py --ticker 000660  # 특정 종목
```

### CLI 요약 (연속 시뮬레이션 종료 시 자동 출력)

```
날짜           예측    매수%   매도%   1일실제   정확(1d)
2026-03-06    상승    42.1%   18.3%   +1.8%     ✓
2026-03-07    하락    22.0%   38.5%   -0.9%     ✓
2026-03-10    보합    31.2%   28.7%   +0.3%     ✓

전체 평균 정확도: 73.2%
1일: 73% / 5일: 61% / 20일: 55%
```

---

## 6. 설치 및 실행

### .env 설정

```env
LLM_MODE=ollama
OLLAMA_MODEL=phi4:latest
OLLAMA_BASE_URL=http://localhost:11434/v1

# DART
DART_API_KEY=발급받은키

# 공공데이터포털 — ⚠️ 반드시 디코딩 키 사용 (특수문자 포함 그대로)
DATA_GO_KR_API_KEY=62QrF8XBi8pUjF4C2bxLb.../DmQAC6...==

# 네이버 검색 API
NAVER_CLIENT_ID=발급받은키
NAVER_CLIENT_SECRET=발급받은키
```

### 실행 명령어

```bash
pip install -r requirements.txt

# 단일 종목 단일일
python main.py --corp SK하이닉스 --ticker 000660 --date 2024-01-15

# 날짜 범위 연속 시뮬레이션
python run_continuous.py --corp SK하이닉스 --ticker 000660 --start 2024-01-10 --end 2024-01-20

# 오늘부터 N일 전까지
python run_continuous.py --corp 삼성전자 --ticker 005930 --days 7

# 멀티 종목 배치 (stocks_config.json 기준)
python run_multi_stock.py --days 5
python run_multi_stock.py --tickers 000660 005930 --days 3

# 대시보드
streamlit run dashboard/app.py

# HTML 리포트
python generate_report.py

# 페르소나 초기화 (재생성)
python -c "from agents.agent_factory import reset_personas; reset_personas()"
```

---

## 7. 시행착오 전체 기록

### 트러블 1: DART API 방식 오해

**문제**: 기업 고유번호 조회를 REST API로 시도 → 404

```
GET https://opendart.fss.or.kr/api/company.json?corp_name=SK하이닉스
→ 404 Not Found
```

**원인**: DART 고유번호 API는 `corpCode.xml` 엔드포인트로 **전체 기업 목록을 ZIP으로** 한 번에 다운로드하는 방식이다. 검색 REST API가 아니다.

**해결**: ZIP 다운로드 → XML 파싱 → `{회사명: corp_code}` 딕셔너리 메모리 캐시.

---

### 트러블 2: phi4 모델 tool_call 형식 문제

**문제**: LLM이 JSON 객체 대신 tool_call 형식으로 응답해 파싱 실패.

```json
// 기대: {"action": "매수", "reason": "...", "confidence": 0.7}
// 실제: [{"name": "decide_action", "arguments": {"action": "매수", ...}}]
```

**원인**: Ollama에서 phi4:latest 모델이 tool_call 형식 활성화 상태로 서빙됨.

**해결**: `.env`에서 base 모델을 명시 지정. 추가로 각 파서(`seed_parser.py`, `base_agent.py`)가 `client.py`에 의존하지 않고 독립적으로 JSON 파싱하도록 수정.

---

### 트러블 3: FinanceDataReader + pykrx 모두 차단

**문제**: 주가 수집 두 라이브러리 모두 실패.

```
FinanceDataReader: ConnectionResetError(10054) — 야후파이낸스 서버 차단
pykrx: get_market_ohlcv() → 빈 DataFrame — KRX 서버 측 차단
```

**해결**: **한국 공공데이터포털 주식 시세 API**로 완전 대체.  
`beginBasDt` / `endBasDt` 범위 파라미터로 단일 호출에 여러 날 데이터 수집.

---

### 트러블 4: 공공데이터포털 API 401 오류

**문제**: 정상 API 키인데 401 Unauthorized.

**원인**: 공공데이터포털은 인코딩 키(`%2F`, `%3D` 포함)와 디코딩 키 두 가지를 제공한다.
인코딩 키를 `.env`에 넣으면 `requests`가 URL 인코딩을 한 번 더 해서 이중 인코딩 발생.

**해결**: 마이페이지에서 **디코딩 키** (슬래시, 등호가 그대로 포함된 버전)를 복사해 사용.

---

### 트러블 5: `list indices must be integers` TypeError

**문제**:
```
result["corp_name"] = corp_name
TypeError: list indices must be integers or slices, not str
```

**원인**: `client.py`의 `chat_json()`이 list를 반환할 때 `seed_parser.py`가 처리하지 못함.

**해결**: `seed_parser.py`가 `client.py`에 의존하지 않고 직접 LLM 호출 및 JSON 파싱 처리. `{ }` 구간 추출 + `isinstance(result, list)` 방어 코드 추가.

---

### 트러블 6: 모든 에이전트가 "관망"만 선택 (낙관 편향)

**문제**: 에이전트 20명 전원이 매 라운드 "관망" 선택. 주가 하락 추세에도 매수 편향.

**원인**:
1. `seed_parser.py`의 "애널리스트" 롤이 과도하게 낙관적 요약 생성
2. `bias_val` 범위가 너무 좁음 (`-0.1 ~ +0.1`)
3. 에이전트 system_prompt에 중립성 강제 지시 없음

**해결 (3파일 동시 수정)**:
- `seed_parser.py`: 롤 → "냉철한 리스크 분석가", 하락 추세 시 negative 강제
- `base_agent.py`: `bias_val` 범위 → `-0.25 ~ +0.25`, `base_tendency` 필드 추가, system_prompt 강화
- `aggregator.py`: net(매수% - 매도%) 기반으로만 판정, KOSPI 가중치 적용

---

### 트러블 7: 라운드 1~3 결정이 모두 동일

**문제**: 라운드마다 결정이 변하지 않아 사회적 상호작용 의미 없음.

**원인**:
1. `social_context`가 "개인투자자: 주로 관망" 수준의 너무 약한 텍스트
2. 에이전트가 자신의 직전 라운드 결정을 프롬프트에서 받지 못함
3. `agent_memory.get_recent()`가 `simulation_id` 컬럼을 반환하지 않아 현재 시뮬레이션 기록 조회 실패

**해결 (3파일 수정)**:
- `interaction.py`: 이모지+수치 기반 강한 군중 압력 신호, 기관/단타 강한 방향 시 ⚠️ 표시
- `base_agent.py`: 프롬프트에 "나의 직전 라운드 결정" 섹션 추가, 라운드 번호 헤더 `=== 라운드 N ===` 명시
- `agent_memory.py`: `get_recent()` 반환값에 `simulation_id` 컬럼 추가

---

### 트러블 8: pykrx ticker 형식 문제 (참고 기록)

**문제**: `get_market_ohlcv()` 빈 DataFrame.

**원인**: ticker `"000660"`이 int `660`으로 들어올 경우 6자리 패딩 없이 실패.

**해결**: `str(ticker).zfill(6)` 안전 처리. (이후 API 자체를 교체했으므로 참고용)

---

### 트러블 9: Streamlit 바 차트 UI 이슈

**문제**: 정확도 바 차트 너비 좁고 레이블 겹침.

**해결**: `width=0.55`, `bargap=0.35`, zeroline 파란색 강조, 높이 동적 계산(`max(300, n*50)`), `ticksuffix="%"` 적용.

### 트러블 10: 대시보드 리팩토링 후 `run_meta` 잔존 참조 오류

**문제**: `get_latest_run_per_ticker()` 도입 후 대시보드 실행 시 `NameError: name 'run_meta' is not defined`.

```
File "dashboard/app.py", line 91
    "1일정확도": run_meta.get("accuracy_1d"),
NameError: name 'run_meta' is not defined
```

**원인**: `list_runs()` + `load_run()` 루프에서 `get_latest_run_per_ticker()`로 교체하면서 `run_meta`를 `run`으로 바꿨는데, 루프 내부 딕셔너리 값 참조 3곳(`accuracy_1d`, `start_date`, `end_date`, `run_id`)이 미처 교체되지 않고 남았다.

**해결**: `run_meta.get(...)` → `run.get(...)` 전수 교체. `get_latest_run_per_ticker()`가 이미 전체 run JSON을 반환하므로 메타 딕셔너리 없이 `run`에서 직접 꺼낼 수 있다.

---

### 트러블 11: `ImportError: cannot import name 'get_latest_run_per_ticker'`

**문제**: 대시보드 실행 시 import 오류.

```
ImportError: cannot import name 'get_latest_run_per_ticker' from 'db.store'
```

**원인**: 서버(Claude)에서 수정한 `store.py`가 로컬 파일에 반영되지 않은 상태로 대시보드를 실행.

**해결**: 수정된 `db/store.py`를 로컬에 덮어쓰기. ZIP 파일 내 최신 버전으로 교체하거나, `store.py`에 `list_runs(latest_only=False)` + `get_latest_run_per_ticker()` 두 함수를 직접 추가.

### 트러블 12: 공공데이터 주가 API `srtnCd` 파라미터 오용

**문제**: `srtnCd=000660`으로 요청했는데 전체 종목 46,088건이 반환됨.

```
[Price] 종목코드(000660)로 조회
[Price] 총 46088건 → 461페이지 조회
```

**원인**: `srtnCd`는 API **응답 JSON의 필드명**이고, 요청 파라미터는 `likeSrtnCd`다.
필터가 무시된 채 전체 종목 데이터가 반환됨.

**해결**: `params["srtnCd"]` → `params["likeSrtnCd"]`로 교정. `mrktCls` 파라미터도 불필요하여 제거.

---

### 트러블 13: 주가 API `numOfRows=100` 고정으로 데이터 잘림

**문제**: 날짜 범위가 길면 100건 이후 데이터가 누락됨.

**원인**: `numOfRows=100` 고정이라 50 영업일 이상 범위 조회 시 초과분 손실.

**해결**: 1페이지 응답에서 `totalCount` 확인 후 초과 시 자동 페이지네이션.

```python
total_count = int(body.get("totalCount", 0))
if total_count > num_of_rows:
    for page in range(2, math.ceil(total_count / num_of_rows) + 1):
        # 추가 페이지 조회 및 합산
```

---

### 트러블 14: 뉴스 API가 항상 오늘 기준 최신 기사를 반환

**문제**: 2025-03-10 시뮬레이션인데 2026-03-16 기사가 들어옴. 날짜별로 같은 뉴스 반복.

**원인**: 네이버 뉴스 API는 `sort=date`로 최신 N건만 반환. 날짜 필터 파라미터가 없어서
과거 날짜 시뮬레이션에서도 오늘 기준 최신 기사가 들어갔다.

**해결**:
- 7일 이내 → API + `pubDate` 필터로 해당 날짜 기사 선별
- 7일 초과 → 크롤링 (`ds`/`de` 날짜 파라미터로 정확히 수집)
- `sort=sim` (정확도순), 검색어 `"{종목명} 주식"` 으로 변경
- **시뮬레이션 당일 제외, -1일 ~ -7일 기사만 사용** (미래 정보 유입 차단)

---

### 트러블 15: 공시/뉴스 없을 때 에이전트가 없는 정보를 근거로 reason 생성

**문제**: 공시 0건, 뉴스 0건인데 에이전트 reason에 "하락 추세와 부정적 공시/뉴스 absence"가 출력됨.

**원인**: `_get_decision_constraint()`에 "뉴스가 부정적이면 매도나 관망이 자연스러운 반응이다" 같은
문구가 데이터 유무와 무관하게 항상 LLM에게 전달됨. LLM이 없는 정보를 전제로 추론.

**해결**:
- `engine.py`: 공시/뉴스 0건 시 `"⚠️ 오늘은 수집된 공시와 뉴스가 없습니다. 주가 데이터만으로 판단하세요."` 명시
- `base_agent.py`: constraint 문구를 "주어진 정보에 부정적 신호가 있으면" / "정보가 없으면 관망" 조건부 표현으로 교체

---

## 8. 향후 개선 방향

**완료된 항목**
- ✅ 에이전트 확신도(confidence) 히스토그램 + 타입별 분석
- ✅ 에이전트 발언 카드 (매수/매도/관망 대표 이유 텍스트)
- ✅ 예측 방향 vs 실제 주가 라인 차트 + 누적 비교
- ✅ 의견 불일치 지수(Disagreement Score) + 경고 배너
- ✅ 이슈 유형별 정확도 분석
- ✅ 백테스트 요약 페이지 (신뢰도 곡선, 히트맵)
- ✅ Stability Score (LLM 랜덤성 정량화)
- ✅ DB latest_only — 종목당 최신 실행만 로드
- ✅ 데이터 사전 일괄 수집 — API 호출 최소화 (종목당 3번)
- ✅ 뉴스 날짜 필터 — 당일 제외 -1~-7일, sort=sim, 검색어+주식
- ✅ likeSrtnCd 파라미터 교정 — 전체 종목 반환 버그 수정
- ✅ 주가 API 페이지네이션 — totalCount 기반 자동 처리
- ✅ 종목 간 에이전트 메모리 격리 (교차 오염 방지)
- ✅ _attention 필드 프롬프트 반영 — 에이전트 이질성 강화
- ✅ sentiment 중복 제거 — summary에 자연스럽게 통합
- ✅ 시뮬레이션 흐름 탭 (🧠) — 씨드→에이전트→예측 스토리 시각화
- ✅ 공시/뉴스 원문 seed 저장 (raw_articles, raw_disclosures)

**남은 항목**
- **뉴스 소스 강화**: BigKinds API (경제 카테고리 필터) 적용
- **에이전트 수 확장**: 20명 → 100명 (GPU 서버 환경)
- **실시간 모드**: 장중 30분 단위 자동 실행
- **OpenAI 전환 데모**: GPT-4o-mini vs phi4 정확도 비교

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| LLM | Ollama (phi4:latest) / OpenAI API |
| 언어 | Python 3.11 |
| 병렬 처리 | `concurrent.futures.ThreadPoolExecutor` |
| 에이전트 메모리 | SQLite (`sqlite3`) |
| 주가 데이터 | 한국 공공데이터포털 API |
| 공시 데이터 | DART 전자공시 API |
| 뉴스 | 네이버 검색 API |
| 대시보드 | Streamlit + Plotly |
| 결과 저장 | 파일 기반 JSON DB |
| 설정 관리 | `python-dotenv` |

---

## 참고 / 영감

- [OASIS: Open Agent Social Interaction Simulations](https://arxiv.org/abs/2411.11581)
- DART 전자공시시스템 API: https://opendart.fss.or.kr
- 공공데이터포털 주식 시세: https://www.data.go.kr

---

*Made with Ollama phi4 + Python — AI/데이터 직군 포트폴리오 프로젝트*

---

## 프로젝트 요약 (10줄)

AgentFlow는 LLM을 활용해 주식 시장 참여자의 집단 행동을 시뮬레이션하고 주가 방향을 예측하는 다중 에이전트 시스템이다.
기존 ML이 패턴 학습에 의존해 새 이벤트에 무력한 한계를 극복하고자, DART 공시·네이버 뉴스·공공데이터포털 주가를 실시간 수집해 LLM 씨드로 변환한다.
데이터 수집은 종목당 API 3번(DART/뉴스/주가 각 1회) 사전 일괄 수집 후 날짜 루프에서 dict 조회만 하여 API 호출을 최소화한다.
뉴스는 시뮬레이션 당일을 제외한 -1일~-7일 기사만 사용하고, `sort=sim`(정확도순)으로 주식 관련 기사를 선별한다.
개인·기관·단타·가치투자자 4종 페르소나 20명이 각자 편향값·주의집중요소·SQLite 기억을 갖고 독립 판단 후 군중 압력 신호를 보며 재판단한다.
집계 시 HHI 기반 Disagreement Score와 Stability Score로 예측 신뢰도를 수치화하고, 불일치가 높으면 경고 배너를 표시한다.
대시보드는 전체 비교/종목 상세/백테스트/🧠시뮬레이션 흐름 4개 뷰로 구성되며, 시뮬레이션 흐름 탭에서 씨드→에이전트→예측 과정을 스토리텔링으로 보여준다.
srtnCd(응답 필드)와 likeSrtnCd(요청 파라미터) 혼동, 뉴스 날짜 필터 부재, 에이전트 메모리 교차 오염 등 15개 트러블슈팅 이력을 모두 기록했다.
DB는 ticker당 최신 실행 1건만 로드하며, 멀티 종목 배치 실행 시 종목 전환마다 에이전트 메모리를 초기화해 종목 간 결정 교차 오염을 방지한다.
로컬 Ollama(phi4)와 OpenAI API를 `.env` 한 줄로 전환하는 추상화 레이어로 개발·데모 환경을 유연하게 전환할 수 있다.