import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"


def get_price_data(itms_nm: str, base_date: str, days_before: int = 5, days_after: int = 22,
                   ticker: str = None) -> pd.DataFrame:
    """
    ticker(종목코드)가 있으면 srtnCd로 정확히 조회.
    없으면 likeItmsNm 부분일치 사용 (fallback).
    """
    service_key = os.getenv("DATA_GO_KR_API_KEY")
    if not service_key:
        print("[Price] DATA_GO_KR_API_KEY 없음 — .env 확인 필요")
        return pd.DataFrame()

    base_dt  = datetime.strptime(base_date, "%Y-%m-%d")
    start_dt = base_dt - timedelta(days=days_before + 7)   # 주말 여유
    end_dt   = base_dt + timedelta(days=days_after + 7)

    # ✅ 날짜는 반드시 YYYYMMDD 형식 (하이픈 없음)
    params = {
        "serviceKey": service_key,
        "numOfRows":  100,
        "pageNo":     1,
        "resultType": "json",
        "beginBasDt": start_dt.strftime("%Y%m%d"),
        "endBasDt":   end_dt.strftime("%Y%m%d"),
    }

    # ✅ 종목코드 → likeSrtnCd 파라미터 사용
    # ✅ 종목명 → likeItmsNm 파라미터 사용 (fallback)
    if ticker:
        params["likeSrtnCd"] = str(ticker).zfill(6)
        print(f"[Price] likeSrtnCd({params['likeSrtnCd']})로 조회")
    else:
        params["likeItmsNm"] = itms_nm
        print(f"[Price] likeItmsNm({itms_nm})으로 조회 (ticker 없음)")

    try:
        # ── 1페이지 먼저 조회해서 totalCount 확인 ──────────────
        resp = requests.get(BASE_URL, params=params, timeout=15)
        data = resp.json()
        body = data["response"]["body"]

        total_count = int(body.get("totalCount", 0))
        items = body.get("items", "")

        if not items or items == "" or total_count == 0:
            print("[Price] 조회 결과 없음")
            return pd.DataFrame()

        item_list = items["item"]
        if isinstance(item_list, dict):
            item_list = [item_list]

        # ── totalCount > numOfRows 이면 페이지네이션 ───────────
        num_of_rows = params["numOfRows"]
        if total_count > num_of_rows:
            import math
            total_pages = math.ceil(total_count / num_of_rows)
            print(f"[Price] 총 {total_count}건 → {total_pages}페이지 조회")
            for page in range(2, total_pages + 1):
                paged_params = {**params, "pageNo": page}
                resp2 = requests.get(BASE_URL, params=paged_params, timeout=15)
                data2 = resp2.json()
                items2 = data2["response"]["body"].get("items", "")
                if items2 and items2 != "":
                    extra = items2["item"]
                    if isinstance(extra, dict):
                        extra = [extra]
                    item_list.extend(extra)

        print(f"[Price] 공공데이터 API 성공: 총 {len(item_list)}건")

    except Exception as e:
        print(f"[Price] API 호출 실패: {e}")
        return pd.DataFrame()

    rows = []
    for item in item_list:
        rows.append({
            "날짜":    pd.Timestamp(item["basDt"]),
            "종가":    int(item["clpr"]),
            "시가":    int(item["mkp"]),
            "고가":    int(item["hipr"]),
            "저가":    int(item["lopr"]),
            "거래량":  int(item["trqu"]),
            "등락률":  float(item["fltRt"]),
            "종목코드": item["srtnCd"],
        })

    df = pd.DataFrame(rows).set_index("날짜").sort_index()
    if not df.empty:
        print(f"[Price] 날짜 범위: {df.index[0].date()} ~ {df.index[-1].date()}")
    return df


def build_market_context(itms_nm: str, base_date: str, ticker: str = None) -> dict:
    """시뮬레이션 컨텍스트 + 검증용 실제 등락률"""
    df = get_price_data(itms_nm, base_date, ticker=ticker)
    if df.empty:
        print("[Price] 주가 데이터 없음 — 빈 컨텍스트로 진행")
        return {}

    base_dt = pd.Timestamp(base_date)
    past    = df[df.index <= base_dt]
    future  = df[df.index >  base_dt]

    if past.empty:
        return {}

    current_price = float(past["종가"].iloc[-1])
    price_5d_ago  = float(past["종가"].iloc[-5]) if len(past) >= 5 else float(past["종가"].iloc[0])
    change_5d_pct = (current_price - price_5d_ago) / price_5d_ago * 100
    trend = "상승" if change_5d_pct > 1 else "하락" if change_5d_pct < -1 else "보합"

    def future_change(days):
        sl = future.head(days)
        if sl.empty:
            return None
        return round((float(sl["종가"].iloc[-1]) - current_price) / current_price * 100, 2)

    return {
        "current_price":       current_price,
        "price_change_5d_pct": round(change_5d_pct, 2),
        "trend":               trend,
        "actual_1d_pct":       future_change(1),
        "actual_5d_pct":       future_change(5),
        "actual_20d_pct":      future_change(20),
    }


def build_market_context_range(
    itms_nm: str, start_date: str, end_date: str, ticker: str = None
) -> dict[str, dict]:
    """
    날짜 범위 전체 주가를 한 번에 수집 후 날짜별 market_context 딕셔너리로 반환.
    반환: {날짜(YYYY-MM-DD): market_context_dict}

    단일 API 호출로 전체 범위를 처리.
    """
    from datetime import datetime, timedelta
    import pandas as pd

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")

    df = get_price_data(itms_nm, start_date,
                        days_before=15, days_after=35,
                        ticker=ticker)

    if df.empty:
        print("[Price] 범위 주가 데이터 없음")
        return {}

    result: dict[str, dict] = {}
    cur = start_dt
    while cur <= end_dt:
        base_dt = pd.Timestamp(cur)
        past    = df[df.index <= base_dt]
        future  = df[df.index >  base_dt]

        if past.empty:
            cur += timedelta(days=1)
            continue

        current_price = float(past["종가"].iloc[-1])
        price_5d_ago  = float(past["종가"].iloc[-5]) if len(past) >= 5 else float(past["종가"].iloc[0])
        change_5d_pct = (current_price - price_5d_ago) / price_5d_ago * 100
        trend = "상승" if change_5d_pct > 1 else "하락" if change_5d_pct < -1 else "보합"

        def future_change(days):
            sl = future.head(days)
            if sl.empty:
                return None
            return round((float(sl["종가"].iloc[-1]) - current_price) / current_price * 100, 2)

        result[cur.strftime("%Y-%m-%d")] = {
            "current_price":       current_price,
            "price_change_5d_pct": round(change_5d_pct, 2),
            "trend":               trend,
            "actual_1d_pct":       future_change(1),
            "actual_5d_pct":       future_change(5),
            "actual_20d_pct":      future_change(20),
        }
        cur += timedelta(days=1)

    print(f"[Price] 범위 market_context 생성: {len(result)}일치")
    return result