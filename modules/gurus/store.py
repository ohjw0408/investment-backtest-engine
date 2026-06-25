"""guru_holdings.db 읽기 — 목록/상세 조회. 페이지·홈카드 공용."""
import os
import sqlite3

_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "data", "meta", "guru_holdings.db")


def _conn():
    con = sqlite3.connect(_DB)
    con.row_factory = sqlite3.Row
    return con


_Q = {"03": "1분기", "06": "2분기", "09": "3분기", "12": "4분기"}


def period_label(period):
    """'2026-03-31' → '2026년 1분기'."""
    if not period or len(period) < 7:
        return period or ""
    y, m = period[:4], period[5:7]
    return f"{y}년 {_Q.get(m, m + '월')}"


def available():
    return os.path.exists(_DB)


def list_gurus(top=4):
    """stale 아닌 대가 목록(stance 순). 각자 상위 top개 커버 보유 동봉(미니바용)."""
    if not available():
        return []
    con = _conn()
    gurus = con.execute(
        "SELECT g.*, f.filed FROM gurus g LEFT JOIN filings f ON g.cik=f.cik "
        "WHERE g.stale=0 ORDER BY g.stance"
    ).fetchall()
    out = []
    for g in gurus:
        tops = con.execute(
            "SELECT ticker, name, weight FROM holdings "
            "WHERE cik=? AND covered=1 ORDER BY rank LIMIT ?", (g["cik"], top)
        ).fetchall()
        out.append({
            "slug": g["slug"], "name": g["name"], "fund": g["fund"],
            "stance": g["stance"], "stance_label": g["stance_label"],
            "monogram": g["monogram"], "period": g["latest_period"],
            "period_label": period_label(g["latest_period"]), "filed": g["filed"],
            "top": [{"ticker": t["ticker"], "name": t["name"],
                     "weight": round(t["weight"] * 100, 1)} for t in tops],
        })
    con.close()
    return out


def get_guru(slug, limit=25):
    """대가 상세 — 메타 + 커버 보유 상위 limit개(비중 재정규화)."""
    if not available():
        return None
    con = _conn()
    g = con.execute(
        "SELECT g.*, f.filed, f.accession FROM gurus g LEFT JOIN filings f ON g.cik=f.cik "
        "WHERE g.slug=?", (slug,)
    ).fetchone()
    if not g:
        con.close()
        return None
    rows = con.execute(
        "SELECT rank, ticker, name, shares, value, weight, covered "
        "FROM holdings WHERE cik=? ORDER BY rank", (g["cik"],)
    ).fetchall()
    con.close()
    covered = [r for r in rows if r["covered"]]
    cov_total = sum(r["weight"] for r in covered) or 1.0
    holdings = []
    for r in covered[:limit]:
        holdings.append({
            "rank": r["rank"], "ticker": r["ticker"], "name": r["name"],
            "weight": round(r["weight"] * 100, 1),
            "weight_norm": round(r["weight"] / cov_total * 100, 1),
        })
    return {
        "slug": g["slug"], "name": g["name"], "fund": g["fund"],
        "stance": g["stance"], "stance_label": g["stance_label"], "monogram": g["monogram"],
        "period": g["latest_period"], "period_label": period_label(g["latest_period"]),
        "filed": g["filed"],
        "n_total": len(rows), "n_covered": len(covered),
        "covered_weight": round(cov_total * 100, 1),
        "holdings": holdings,
    }
