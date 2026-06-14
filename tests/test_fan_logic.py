"""
경험적 부채꼴 백엔드 순수함수 검증 — yearly_trajectory + _build_fan.
실행: python tests/test_fan_logic.py  (또는 pytest tests/test_fan_logic.py)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from modules.multi_account_common import yearly_trajectory
from calculator_logic import _build_fan

_p = _f = 0
def ok(name, cond):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name)
    else:    _f += 1; print("FAIL  " + name)


# ── yearly_trajectory ──
# 3년 일별 history, portfolio_value 선형 증가. 시작 2020-01-01.
dates = pd.date_range("2020-01-01", "2023-01-01", freq="D")
pv = [1000 + i for i in range(len(dates))]   # 단조 증가
hist = pd.DataFrame({"date": dates, "portfolio_value": pv})

traj = yearly_trajectory(hist, 3)
ok("길이 = years+1", len(traj) == 4)
ok("offset0 = 시작값", traj[0] == 1000.0)
# 1년차 = 2021-01-01 이하 마지막. 2020 윤년 366일 → 인덱스 366 = 2021-01-01 값 1366
ok("1년차 = 1년 경과 값", traj[1] == pv[366])
ok("단조 증가 궤적", traj[0] < traj[1] < traj[2] < traj[3])

# final_value 오버라이드 — 마지막점만 교체
traj2 = yearly_trajectory(hist, 3, final_value=99999.0)
ok("final_value가 마지막점 교체", traj2[-1] == 99999.0 and traj2[0] == traj[0])

# 빈 history
ok("빈 history → []", yearly_trajectory(pd.DataFrame(), 3) == [])


# ── _build_fan ──
# 5개 윈도우, 각 연차 궤적(years=2 → 길이3). 값을 일부러 분산.
cases = [
    {"_yearly": [100, 110, 120]},
    {"_yearly": [100, 120, 160]},
    {"_yearly": [100, 90,  80]},
    {"_yearly": [100, 130, 200]},
    {"_yearly": [100, 105, 115]},
]
fan = _build_fan(cases, years=2)
ok("fan 생성됨", fan is not None)
ok("axis = 0..years", fan["axis"] == [0, 1, 2])
ok("percentiles = p1..p99 (99개)", fan["percentiles"] == list(range(1, 100)) and len(fan["bands"]) == 99)
ok("bands 각 행 길이 = years+1", all(len(row) == 3 for row in fan["bands"]))
# year0 전부 100 → 모든 퍼센틸 100 (밴드 폭 0, 부채꼴 시작점)
ok("year0 모든 퍼센틸 = 100", all(row[0] == 100 for row in fan["bands"]))
# p50(인덱스 49) year2 = median([120,160,80,200,115]) = 120
p50_idx = fan["percentiles"].index(50)
ok("p50 year2 = median 120", fan["bands"][p50_idx][2] == 120)
# 단조: 낮은 퍼센틸 ≤ 높은 퍼센틸 (year2)
col = [row[2] for row in fan["bands"]]
ok("퍼센틸 단조 증가", all(col[i] <= col[i+1] for i in range(len(col)-1)))

# 표본 부족(<5) → None
ok("표본<5 → None", _build_fan(cases[:4], years=2) is None)
# _yearly 길이 불일치 윈도우 제외
bad = cases + [{"_yearly": [100, 110]}]   # 길이 2 (years+1=3 아님)
fan_bad = _build_fan(bad, years=2)
ok("길이 불일치 윈도우 제외(n=5)", fan_bad["n"] == 5)

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
