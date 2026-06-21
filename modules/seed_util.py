"""
seed_util.py
────────────────────────────────────────────────────────────────────────────────
프로세스 무관 결정적 시드.

내장 `hash(str)`은 PYTHONHASHSEED(미고정 시 프로세스마다 랜덤)에 의존 →
같은 입력이라도 worker 재시작/재실행마다 MC·가상데이터 시드가 달라져 결과가 흔들렸다.
md5 기반으로 고정해 같은 입력 → 항상 같은 시드 → 재현 가능(로컬=prod 일치).
"""

import hashlib


def stable_seed(s, mod: int = 2 ** 31) -> int:
    """문자열 s에서 결정적 정수 시드. mod로 범위 제한(기존 호출부 규약 유지)."""
    digest = hashlib.md5(str(s).encode("utf-8")).hexdigest()
    return int(digest, 16) % mod
