"""SEC EDGAR 13F-HR fetch + 정보테이블 파싱.

퍼블릭 도메인(미국 정부 공문서). API 키 불필요 — User-Agent 헤더만 필수(SEC 규정).
값(value) 단위는 보고서에 따라 천$/달러 혼재하나 비중 계산은 단위 무관(상쇄).
"""
import re
import time
import requests
import xml.etree.ElementTree as ET

USER_AGENT = "MoneyMilestone research ohjw0408@gmail.com"
_HEAD = {"User-Agent": USER_AGENT}
_TIMEOUT = 25


def _get(url, as_json=False):
    r = requests.get(url, headers=_HEAD, timeout=_TIMEOUT)
    r.raise_for_status()
    time.sleep(0.15)  # SEC fair-access (<10 req/s)
    return r.json() if as_json else r.text


def get_latest_13f(cik):
    """최신 13F-HR 메타 반환: dict(period, filed, accession) 또는 None."""
    cik10 = str(int(cik)).zfill(10)
    j = _get(f"https://data.sec.gov/submissions/CIK{cik10}.json", as_json=True)
    rec = j.get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    for i, f in enumerate(forms):
        if f.startswith("13F-HR"):  # 13F-HR and 13F-HR/A (amendment)
            return {
                "name": j.get("name"),
                "form": f,
                "period": rec["reportDate"][i],
                "filed": rec["filingDate"][i],
                "accession": rec["accessionNumber"][i],
            }
    return None


def _info_table_url(cik, accession):
    """필링 디렉터리에서 정보테이블 XML URL 탐색."""
    acc_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}"
    idx = _get(f"{base}/index.json", as_json=True)
    items = idx.get("directory", {}).get("item", [])
    xmls = [it["name"] for it in items if it["name"].lower().endswith(".xml")]
    # primary_doc.xml = 표지(cover). 정보테이블은 그 외 xml 중 informationTable 포함분.
    candidates = [n for n in xmls if "primary_doc" not in n.lower()]
    for name in candidates + xmls:
        url = f"{base}/{name}"
        txt = _get(url)
        if "infoTable" in txt or "informationTable" in txt:
            return url, txt
    return None, None


def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def parse_info_table(xml_text):
    """정보테이블 XML → 보유 리스트. 콜/풋 옵션 행은 제외(롱 보통주만)."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    holdings = []
    for el in root.iter():
        if _strip_ns(el.tag) != "infoTable":
            continue
        rec = {}
        for child in el.iter():
            tag = _strip_ns(child.tag)
            if tag in ("nameOfIssuer", "titleOfClass", "cusip", "value", "putCall"):
                rec[tag] = (child.text or "").strip()
            elif tag == "sshPrnamt":
                rec["shares"] = (child.text or "").strip()
        # 옵션(put/call) 행 제외 — 롱 보통주 포지션만
        if rec.get("putCall"):
            continue
        cusip = rec.get("cusip", "")
        if not cusip:
            continue
        try:
            value = float(rec.get("value", "0") or 0)
        except ValueError:
            value = 0.0
        try:
            shares = float(rec.get("shares", "0") or 0)
        except ValueError:
            shares = 0.0
        holdings.append({
            "cusip": cusip.upper(),
            "name": rec.get("nameOfIssuer", ""),
            "title": rec.get("titleOfClass", ""),
            "value": value,
            "shares": shares,
        })
    return holdings


def fetch_holdings(cik, accession):
    """CIK+accession → 동일 CUSIP 합산 보유 리스트(value 내림차순)."""
    _, txt = _info_table_url(cik, accession)
    if not txt:
        return []
    rows = parse_info_table(txt)
    # 같은 CUSIP 여러 행(클래스/계정 분리) 합산
    agg = {}
    for r in rows:
        k = r["cusip"]
        if k not in agg:
            agg[k] = dict(r)
        else:
            agg[k]["value"] += r["value"]
            agg[k]["shares"] += r["shares"]
    out = sorted(agg.values(), key=lambda x: x["value"], reverse=True)
    return out
