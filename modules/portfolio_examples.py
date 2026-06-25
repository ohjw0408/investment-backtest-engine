"""포트폴리오 예시(추천 템플릿) 로더 — data/meta/portfolio_examples.json 읽기.
region(us|kr) · category(defensive|hedge|aggressive|dividend) 조회. 페이지·핸드오프 공용."""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "meta", "portfolio_examples.json")
_cache = None

REGION_LABELS = {"us": "🇺🇸 미국", "kr": "🇰🇷 한국"}
CATEGORY_LABELS = {
    "defensive": "🛡️ 방어형", "hedge": "🥇 헷지형", "aggressive": "🚀 공격형", "dividend": "💵 배당형",
}
CATEGORY_ORDER = ["defensive", "hedge", "dividend", "aggressive"]


def _load():
    global _cache
    if _cache is None:
        with open(_PATH, encoding="utf-8") as f:
            _cache = json.load(f).get("strategies", [])
    return _cache


def list_examples(region=None, category=None):
    out = _load()
    if region:
        out = [s for s in out if s.get("region") == region]
    if category:
        out = [s for s in out if s.get("category") == category]
    return out


def get_example(slug):
    return next((s for s in _load() if s.get("slug") == slug), None)


def grouped(region):
    """지역의 전략을 category 순서대로 묶음 → [(category, label, [strategies])]."""
    out = []
    for cat in CATEGORY_ORDER:
        items = list_examples(region=region, category=cat)
        if items:
            out.append((cat, CATEGORY_LABELS[cat], items))
    return out
