import os
import requests
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


class NewsCollector:
    """
    뉴스 수집기
    - 실시간 모드 (오늘 날짜): 네이버 검색 API — 최근 1주일 뉴스
    - 백테스팅 모드 (과거 날짜): 뉴스 수집 스킵, DART 공시만 활용
    """

    NAVER_API_URL = "https://openapi.naver.com/v1/search/news.json"
    HEADERS_CRAWL = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def get_news_by_keyword(
        self, keyword: str, target_date: str, days: int = 3, max_articles: int = 10
    ) -> list[dict]:
        """
        target_date 당일은 제외하고, -1일 ~ -7일 사이 기사만 수집.
        검색어: '{keyword} 주식' (주식 관련 뉴스 집중)
        sort: sim (정확도순)
        """
        # 검색어에 '주식' 추가
        query = f"{keyword} 주식"

        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        days_ago  = (datetime.now() - target_dt).days

        client_id     = os.getenv("NAVER_CLIENT_ID")
        client_secret = os.getenv("NAVER_CLIENT_SECRET")

        if client_id and client_secret:
            articles = self._fetch_naver_api(
                client_id, client_secret, query, max_articles,
                target_date=target_date,
            )
            if articles:
                return articles
            print(f"[News] API 결과 없음({target_date}) — 크롤링 폴백")

        return self._fetch_naver_crawl(query, target_date, days, max_articles)

    # ── 네이버 검색 API (최신 뉴스) ───────────────────────────
    def _fetch_naver_api(
        self, client_id: str, client_secret: str, keyword: str, max_articles: int,
        target_date: str = None,  # 필터 기준일 (YYYY-MM-DD)
    ) -> list[dict]:
        headers = {
            "X-Naver-Client-Id":     client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {
            "query":   keyword,
            "display": 100,   # 넉넉하게 받아서 날짜 필터 후 max_articles개 반환
            "start":   1,
            "sort":    "sim",  # 정확도순
        }

        # 필터 기준: target_date 당일 제외, -1일 ~ -7일 사이 기사만
        from datetime import datetime, timedelta
        if target_date:
            base_dt  = datetime.strptime(target_date, "%Y-%m-%d")
            end_dt   = base_dt - timedelta(days=1)   # 전일까지 (당일 제외)
            start_dt = base_dt - timedelta(days=7)   # 7일 전부터
        else:
            end_dt   = datetime.now() - timedelta(days=1)
            start_dt = end_dt - timedelta(days=6)

        try:
            resp = requests.get(self.NAVER_API_URL, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("items", [])

            articles = []
            for item in items:
                pub_date = self._parse_pub_date(item.get("pubDate", ""))

                # pubDate 기준: start_dt(-7일) <= 기사날짜 <= end_dt(-1일)
                # 당일(target_date) 기사는 포함하지 않음
                if pub_date:
                    if not (start_dt.date() <= pub_date.date() <= end_dt.date()):
                        continue

                title = BeautifulSoup(item.get("title", ""), "html.parser").get_text()
                desc  = BeautifulSoup(item.get("description", ""), "html.parser").get_text()
                articles.append({
                    "title":       title,
                    "description": desc[:300],
                    "press":       item.get("originallink", "").split("/")[2] if item.get("originallink") else "",
                    "date":        pub_date.strftime("%Y-%m-%d") if pub_date else "",
                    "url":         item.get("link", ""),
                    "source":      "naver_api",
                })

                if len(articles) >= max_articles:
                    break

            print(f"[News] 네이버 API '{keyword}' ({target_date} 기준 -1~-7일) {len(articles)}건 수집")
            return articles

        except Exception as e:
            print(f"[News] 네이버 API 실패: {e}")
            return []

    def _parse_pub_date(self, date_str: str) -> datetime | None:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str).replace(tzinfo=None)
        except Exception:
            return None

    # ── 크롤링 폴백 ──────────────────────────────────────────
    def _fetch_naver_crawl(
        self, keyword: str, target_date: str, days: int, max_articles: int
    ) -> list[dict]:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        ds = (dt - timedelta(days=days)).strftime("%Y.%m.%d")
        de = (dt + timedelta(days=1)).strftime("%Y.%m.%d")

        params = {
            "where": "news", "query": keyword,
            "sm": "tab_opt", "sort": 1,
            "ds": ds, "de": de,
            "nso": f"so:dd,p:from{ds.replace('.','')},to{de.replace('.','')}"
        }

        try:
            res  = requests.get(
                "https://search.naver.com/search.naver",
                params=params, headers=self.HEADERS_CRAWL, timeout=10
            )
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select(".news_area")[:max_articles]

            articles = []
            for item in items:
                title_tag = item.select_one(".news_tit")
                desc_tag  = item.select_one(".dsc_txt_wrap")
                press_tag = item.select_one(".press")
                date_tag  = item.select_one(".info_group span.info")
                if not title_tag:
                    continue
                articles.append({
                    "title":       title_tag.get_text(strip=True),
                    "description": desc_tag.get_text(strip=True) if desc_tag else "",
                    "press":       press_tag.get_text(strip=True) if press_tag else "",
                    "date":        date_tag.get_text(strip=True) if date_tag else "",
                    "url":         title_tag.get("href", ""),
                    "source":      "naver_crawl",
                })
                time.sleep(0.1)

            print(f"[News] 크롤링 '{keyword}' {len(articles)}건 수집 완료")
            return articles

        except Exception as e:
            print(f"[News] 크롤링 실패: {e}")
            return []

    def format_for_seed(self, articles: list[dict]) -> str:
        if not articles:
            return "관련 뉴스 없음 (DART 공시 기반으로 분석)"
        lines = []
        for i, a in enumerate(articles, 1):
            lines.append(f"[뉴스 {i}] {a['title']} ({a['press']} {a['date']})")
            if a["description"]:
                lines.append(f"  {a['description'][:200]}")
            lines.append("")
        return "\n".join(lines)

    def get_news_range(
        self, keyword: str, start_date: str, end_date: str, max_per_day: int = 10
    ) -> dict[str, list[dict]]:
        """
        날짜 범위 전체 뉴스를 수집 후 날짜별로 분류해 반환.
        반환: {시뮬레이션날짜(YYYY-MM-DD): [기사 리스트]}

        각 시뮬레이션 날짜에는 해당일 제외, -1일 ~ -7일 사이 기사 할당.
        검색어: '{keyword} 주식', sort: sim(정확도순)
        """
        from datetime import datetime, timedelta

        query    = f"{keyword} 주식"
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")

        result: dict[str, list[dict]] = {}

        client_id     = self._get_env("NAVER_CLIENT_ID")
        client_secret = self._get_env("NAVER_CLIENT_SECRET")

        if client_id and client_secret:
            articles = self._fetch_naver_api(
                client_id, client_secret, query,
                max_articles=100,
                target_date=end_date,
            )
            sim_dt = start_dt
            while sim_dt <= end_dt:
                sim_date   = sim_dt.strftime("%Y-%m-%d")
                news_end   = sim_dt - timedelta(days=1)
                news_start = sim_dt - timedelta(days=7)
                day_arts   = [
                    a for a in articles
                    if a.get("date") and
                    news_start.strftime("%Y-%m-%d") <= a["date"] <= news_end.strftime("%Y-%m-%d")
                ]
                if day_arts:
                    result[sim_date] = day_arts[:max_per_day]
                sim_dt += timedelta(days=1)
            print(f"[News] API 범위 수집 '{query}' {start_date}~{end_date}: "
                  f"총 {sum(len(v) for v in result.values())}건 / {len(result)}일치")
        else:
            cur = start_dt
            while cur <= end_dt:
                sim_date  = cur.strftime("%Y-%m-%d")
                news_end  = (cur - timedelta(days=1)).strftime("%Y-%m-%d")
                arts = self._fetch_naver_crawl(query, news_end, days=7, max_articles=max_per_day)
                if arts:
                    result[sim_date] = arts
                cur += timedelta(days=1)
            print(f"[News] 크롤링 범위 수집 '{query}' {start_date}~{end_date}: "
                  f"{len(result)}일치 완료")

        return result

    def _get_env(self, key: str) -> str:
        import os
        return os.getenv(key, "")