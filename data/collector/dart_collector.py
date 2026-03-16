import requests
import os
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dotenv import load_dotenv
import warnings
from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

load_dotenv()

DART_API_KEY = os.getenv("DART_API_KEY", "")
DART_BASE_URL = "https://opendart.fss.or.kr/api"


class DartCollector:
    """
    DART 전자공시 수집기
    고유번호 ZIP 다운로드 → 회사명 검색 → 공시 목록 조회
    """

    def __init__(self):
        self.api_key = DART_API_KEY
        if not self.api_key:
            raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        self._corp_code_cache: dict[str, str] = {}

    def _load_corp_codes(self) -> dict[str, str]:
        """DART 전체 고유번호 목록 ZIP 다운로드 → 파싱"""
        if self._corp_code_cache:
            return self._corp_code_cache

        print("[DART] 고유번호 목록 다운로드 중...")
        url = f"{DART_BASE_URL}/corpCode.xml"
        params = {"crtfc_key": self.api_key}
        res = requests.get(url, params=params, timeout=30)

        if res.status_code != 200:
            raise RuntimeError(f"고유번호 다운로드 실패: HTTP {res.status_code}")

        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xml_filename = [f for f in z.namelist() if f.endswith(".xml")][0]
            xml_content = z.read(xml_filename)

        root = ET.fromstring(xml_content)
        corp_map = {}
        for item in root.findall("list"):
            corp_name = item.findtext("corp_name", "").strip()
            corp_code = item.findtext("corp_code", "").strip()
            stock_code = item.findtext("stock_code", "").strip()
            if corp_name and corp_code:
                corp_map[corp_name] = corp_code
                if stock_code:
                    corp_map[stock_code] = corp_code

        self._corp_code_cache = corp_map
        print(f"[DART] 고유번호 {len(corp_map)}건 로드 완료")
        return corp_map

    def get_company_code(self, corp_name: str) -> str:
        """회사명 또는 종목코드로 DART 고유번호 조회"""
        corp_map = self._load_corp_codes()

        if corp_name in corp_map:
            return corp_map[corp_name]

        matches = [name for name in corp_map if corp_name in name]
        if matches:
            matched = matches[0]
            print(f"[DART] '{corp_name}' → '{matched}' 으로 매칭")
            return corp_map[matched]

        raise ValueError(f"회사를 찾을 수 없습니다: {corp_name}")

    def get_disclosures(
        self, corp_code: str, start_date: str, end_date: str, pblntf_ty: str = "B"
    ) -> list[dict]:
        """공시 목록 조회 (start_date, end_date: YYYYMMDD)"""
        url = f"{DART_BASE_URL}/list.json"
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bgn_de": start_date,
            "end_de": end_date,
            "pblntf_ty": pblntf_ty,
            "page_count": 20,
        }
        res = requests.get(url, params=params, timeout=15)
        data = res.json()

        if data.get("status") != "000":
            print(f"[DART] 공시 없음 또는 오류: {data.get('message')}")
            return []

        return data.get("list", [])

    def get_disclosure_text(self, rcept_no: str) -> str:
        """공시 원문 텍스트 추출"""
        try:
            url = f"{DART_BASE_URL}/document.xml"
            params = {"crtfc_key": self.api_key, "rcept_no": rcept_no}
            res = requests.get(url, params=params, timeout=20)

            from bs4 import BeautifulSoup
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                xml_file = [f for f in z.namelist() if f.endswith(".xml")][0]
                xml_content = z.read(xml_file).decode("utf-8", errors="ignore")

            # XML 파서 명시적으로 지정해서 경고 제거
            soup = BeautifulSoup(xml_content, features="xml")
            text = soup.get_text(separator="\n", strip=True)
            return text[:3000]
        except Exception as e:
            print(f"[DART] 원문 추출 실패 ({rcept_no}): {e}")
            return ""

    def get_recent_major_disclosures(
        self, corp_name: str, issue_date: str, days_before: int = 5
    ) -> list[dict]:
        """
        이슈 발생일 기준 직전 N일의 공시 수집
        days_before 기본값을 3→5로 늘려서 공시 포착률 향상
        """
        dt = datetime.strptime(issue_date, "%Y-%m-%d")
        start = (dt - timedelta(days=days_before)).strftime("%Y%m%d")
        end = dt.strftime("%Y%m%d")

        corp_code = self.get_company_code(corp_name)
        print(f"[DART] {corp_name} corp_code={corp_code}")

        disclosures = []
        for ptype in ["B", "A", "C"]:  # 주요사항, 정기공시, 발행공시 모두 조회
            disclosures += self.get_disclosures(corp_code, start, end, pblntf_ty=ptype)

        disclosures = disclosures[:5]

        results = []
        for d in disclosures:
            text = self.get_disclosure_text(d["rcept_no"])
            results.append({
                "rcept_no": d["rcept_no"],
                "corp_name": d["corp_name"],
                "report_nm": d["report_nm"],
                "rcept_dt": d["rcept_dt"],
                "text": text,
            })

        print(f"[DART] {corp_name} 공시 {len(results)}건 수집 완료")
        return results

    def get_disclosures_range(
        self, corp_name: str, start_date: str, end_date: str
    ) -> dict[str, list[dict]]:
        """
        날짜 범위 전체 공시를 한 번에 수집 후 날짜별로 분류해 반환.
        반환: {날짜(YYYY-MM-DD): [공시 리스트]}

        공시는 rcept_dt 기준으로 해당일에 분류하되,
        시뮬레이션 날짜 기준 -5일까지 포함 (공시 간격 고려).
        """
        from datetime import datetime, timedelta

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")

        # 전체 범위에서 -5일 여유 포함해 한 번에 수집
        fetch_start = (start_dt - timedelta(days=5)).strftime("%Y%m%d")
        fetch_end   = end_dt.strftime("%Y%m%d")

        corp_code = self.get_company_code(corp_name)
        print(f"[DART] 범위 수집 {corp_name} ({fetch_start}~{fetch_end})")

        raw_disclosures = []
        for ptype in ["B", "A", "C"]:
            raw_disclosures += self.get_disclosures(corp_code, fetch_start, fetch_end, pblntf_ty=ptype)

        # 원문 텍스트 수집 (최대 20건)
        enriched = []
        for d in raw_disclosures[:20]:
            text = self.get_disclosure_text(d["rcept_no"])
            enriched.append({
                "rcept_no":  d["rcept_no"],
                "corp_name": d["corp_name"],
                "report_nm": d["report_nm"],
                "rcept_dt":  d["rcept_dt"],   # YYYYMMDD
                "text":      text,
            })

        print(f"[DART] 범위 수집 완료: {len(enriched)}건")

        # 시뮬레이션 날짜별로 분류
        # 각 시뮬레이션 날짜에는 그 날짜 -5일 ~ 당일 공시를 할당
        result: dict[str, list[dict]] = {}
        cur = start_dt
        while cur <= end_dt:
            date_str    = cur.strftime("%Y-%m-%d")
            cutoff_from = (cur - timedelta(days=5)).strftime("%Y%m%d")
            cutoff_to   = cur.strftime("%Y%m%d")

            day_discs = [
                d for d in enriched
                if cutoff_from <= d["rcept_dt"] <= cutoff_to
            ]
            result[date_str] = day_discs[:5]  # 날짜당 최대 5건
            cur += timedelta(days=1)

        return result