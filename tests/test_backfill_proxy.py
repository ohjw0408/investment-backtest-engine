"""백필 프록시 매핑 가드 — 2026-07-21 QQQ=^GSPC 사고 재발 방지.

사고 요약: us_etf_list.csv의 category가 대부분 "US Equity - Large Cap Blend"(yfinance
원문)라 QQQ·QQQM·중국/브라질/인도 ETF가 전부 ^GSPC로 백필됐고, 1928년 S&P500이
"나스닥100 과거"로 둔갑했다(QQQ 합성비중 76%, 1년 손실확률 26.7% vs 실제 17.4%).
"""
import pytest

from modules.backfill_engine import ETF_PROXY_OVERRIDE, US_CATEGORY_MAP


def test_blend_bucket_refuses_backfill():
    """yfinance 쓰레기통 카테고리는 프록시를 주면 안 된다(오분류 대량 유입 경로)."""
    assert US_CATEGORY_MAP["US Equity - Large Cap Blend"] is None


@pytest.mark.parametrize("code,proxy", [
    ("QQQ", "^NDX"),
    ("QQQM", "^NDX"),
    ("IWM", "^RUT"),
    ("SOXX", "^SOX"),
    ("EWY", "KS200"),
    ("INDA", "^NSEI"),
    ("FXI", "^HSCE"),
    ("SPY", "^GSPC"),
])
def test_known_etfs_map_to_their_own_index(code, proxy):
    assert ETF_PROXY_OVERRIDE[code] == proxy


@pytest.mark.parametrize("code", [
    "EEM", "EFA", "VEA", "EWZ", "EWA", "ARGT", "KWEB",
    "XLE", "XLF", "XLI", "XLV", "KRE", "IBB", "XBI",
])
def test_etfs_without_matching_index_refuse_backfill(code):
    """맞는 지수가 없으면 백필 거부. 틀린 프록시보다 백필 없음이 낫다."""
    assert ETF_PROXY_OVERRIDE[code] is None


def test_no_non_sp500_etf_falls_back_to_sp500():
    """S&P500을 추종하지 않는 종목이 ^GSPC 프록시를 갖지 않는다."""
    sp500_family = {"SPY", "IVV", "VOO", "VTI", "RSP"}
    offenders = [c for c, p in ETF_PROXY_OVERRIDE.items()
                 if p == "^GSPC" and c not in sp500_family]
    assert offenders == []
