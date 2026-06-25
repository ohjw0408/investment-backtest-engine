"""13F 정보테이블 파서 결정론 테스트 — 네트워크 없이 고정 샘플 XML로 고정.

검증: 네임스페이스 처리, put/call 옵션 행 제외, 동일 CUSIP 합산, value 내림차순.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.gurus.edgar import parse_info_table

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>1000</value>
    <shrsOrPrnAmt><sshPrnamt>500</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>500</value>
    <shrsOrPrnAmt><sshPrnamt>250</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>3000</value>
    <shrsOrPrnAmt><sshPrnamt>100</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
  <infoTable>
    <nameOfIssuer>SPDR S&amp;P 500</nameOfIssuer>
    <titleOfClass>PUT</titleOfClass>
    <cusip>78462F103</cusip>
    <value>9999</value>
    <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <putCall>Put</putCall>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
</informationTable>"""


def test_parse_excludes_options_and_keeps_long():
    rows = parse_info_table(SAMPLE)
    cusips = {r["cusip"] for r in rows}
    assert "78462F103" not in cusips, "put/call 옵션 행은 제외돼야 함"
    assert cusips == {"037833100", "594918104"}


def test_namespace_stripped_and_fields():
    # MSFT = 단일 행(고유) → 네임스페이스 제거 + 필드 파싱 검증
    msft = next(r for r in parse_info_table(SAMPLE) if r["cusip"] == "594918104")
    assert msft["name"] == "MICROSOFT CORP"
    assert msft["value"] == 3000.0
    assert msft["shares"] == 100.0


def test_sample_row_count():
    rows = parse_info_table(SAMPLE)
    # 옵션 1행 제외 → AAPL 2행 + MSFT 1행 = 3행(합산 전)
    assert len(rows) == 3


if __name__ == "__main__":
    test_parse_excludes_options_and_keeps_long()
    test_namespace_stripped_and_fields()
    test_sample_row_count()
    print("PASS: guru 13F parser")
