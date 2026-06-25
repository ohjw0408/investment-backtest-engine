"""투자 대가 레지스트리 — SEC 13F 제출 기관. CIK는 EDGAR 확인(2026-06-25).

stance = 낙관(1) → 비관(10) 스펙트럼 정렬순. 알려진 시장관/철학 기준이며
13F(미국 롱주식)가 보여주는 실제 포지션과 다를 수 있음(면책 UI 표기).
"""

GURUS = [
    # slug,        name,                   fund,                    cik,          stance, stance_label, monogram
    ("terry-smith",   "Terry Smith",          "Fundsmith LLP",         "0001569205", 1,  "강한 낙관", "TS"),
    ("bill-ackman",   "Bill Ackman",          "Pershing Square",       "0001336528", 2,  "낙관",      "BA"),
    ("li-lu",         "Li Lu",                "Himalaya Capital",      "0001709323", 3,  "낙관",      "LL"),
    ("david-tepper",  "David Tepper",         "Appaloosa",             "0001656456", 4,  "낙관·전술", "DT"),
    ("warren-buffett","Warren Buffett",       "Berkshire Hathaway",    "0001067983", 5,  "온건 낙관", "WB"),
    ("druckenmiller", "Stanley Druckenmiller","Duquesne Family Office","0001536411", 6,  "중립·유연", "SD"),
    ("howard-marks",  "Howard Marks",         "Oaktree Capital",       "0000949509", 7,  "신중",      "HM"),
    ("ray-dalio",     "Ray Dalio",            "Bridgewater",           "0001350694", 8,  "신중·매크로","RD"),
    ("seth-klarman",  "Seth Klarman",         "Baupost Group",         "0001061768", 9,  "비관",      "SK"),
    ("michael-burry", "Michael Burry",        "Scion Asset Mgmt",      "0001649339", 10, "강한 비관", "MB"),
]

# dict by cik for convenience
BY_CIK = {g[3]: g for g in GURUS}
