"""attribution 엔진 결정론 검증. 실행: python tests/test_attribution.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from modules import attribution as at

_p = _f = 0
def ok(name, cond, extra=""):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name + (("  " + extra) if extra else ""))
    else:    _f += 1; print("FAIL  " + name + (("  " + extra) if extra else ""))


class FakeLoader:
    def __init__(self, series): self.series = series  # code -> [(date, close)]
    def get_price(self, code, start, end, apply_fx=True, allow_synthetic=False):
        s = self.series.get(str(code).upper())
        if s is None: return pd.DataFrame()
        return pd.DataFrame({"date": [d for d, _ in s], "close": [c for _, c in s]})


# DEF(방어주): 하락장에 덜 빠짐. GRW(성장주): 상승장 견인, 하락장 더 빠짐.
# 4일: d1 둘다 상승(상승장), d2 둘다 하락(하락장), d3 상승, d4 하락
D = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
GRW = [100, 110, 99, 108.9, 98.01]   # +10%, -10%, +10%, -10%
DEF = [100, 102, 100.98, 103.0, 101.97]  # +2%, -1%, +2%, -1%
loader = FakeLoader({"GRW": list(zip(D, GRW)), "DEF": list(zip(D, DEF))})
W = {"GRW": 50, "DEF": 50}

dates, series = at.aligned_series(loader, ["GRW", "DEF"], D[0], D[-1])
ok("aligned 5일", len(dates) == 5 and len(series) == 2)
pdates, rets = at.daily_returns(dates, series)
ok("일간수익 4개", len(pdates) == 4 and len(rets["GRW"]) == 4)
ok("GRW d1 +10%", abs(rets["GRW"][0] - 0.10) < 1e-9)

up, down, port = at.regime_masks(rets, W)
ok("상승장 2일·하락장 2일", len(up) == 2 and len(down) == 2)

up_c = at.contributions(rets, W, up)
down_c = at.contributions(rets, W, down)
# 상승장: GRW가 견인(더 많이 기여)
ok("상승 견인 = GRW", max(up_c, key=lambda c: up_c[c]) == "GRW")
# 하락장: DEF가 방어(덜 마이너스 = 기여 최대)
ok("하락 방어 = DEF", max(down_c, key=lambda c: down_c[c]) == "DEF",
   f"GRW={down_c['GRW']:.4f} DEF={down_c['DEF']:.4f}")
# 가법성: Σ기여 = 구간 포폴수익 합
psum_up = sum(port[t] for t in up)
ok("가법성(상승)", abs(sum(up_c.values()) - psum_up) < 1e-9)

reg = at.analyze_regime(loader, ["GRW", "DEF"], W, years=1)
ok("regime 요약 견인=GRW", reg["up_driver"]["code"] == "GRW")
ok("regime 요약 방어=DEF", reg["down_defender"]["code"] == "DEF")

win = at.analyze_window(loader, ["GRW", "DEF"], W, D[0], D[-1])
ok("window rows 2", len(win["rows"]) == 2)
ok("window 가법성", abs(sum(r["contrib"] for r in win["rows"]) - win["port_return"]) < 1e-6)

roll = at.analyze_rolling(loader, ["GRW", "DEF"], W, window_days=2, step=1, years=1)
ok("rolling windows>0", roll["windows"] > 0)
ok("rolling 구조(up/down mean)", "mean" in roll["up"]["GRW"] and "mean" in roll["down"]["DEF"])

# 빈 데이터 방어
ok("빈 종목 → None", at.analyze_window(FakeLoader({}), ["X"], {"X": 100}, D[0], D[-1]) is None)

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
