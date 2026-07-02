#!/usr/bin/env python3
"""SQLite 온라인 백업 스크립트 (서버 배포본: /root/ops/db_backup.py).

sqlite3 backup API 사용 — 쓰기 중에도 안전한 스냅샷(WAL 호환). 파일 cp 금지.
cron 설치: /etc/cron.d/moneymilestone-backup (deploy/moneymilestone-backup.cron 참조)

  daily  : users.db (매일 04:10 UTC, 30일 보존)
  weekly : price_daily.db + index_master.db (일요일 04:30 UTC, 4주 보존)

산출: /root/backups/{daily,weekly}/<name>_YYYYMMDD.db.gz
오너 PC가 scp로 pull(tools/backup_pull.ps1). 서버 = 1차, PC = 오프박스 2차.
"""
import gzip
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

REPO = Path("/root/investment-backtest-engine")
BACKUP_ROOT = Path("/root/backups")

TARGETS = {
    "daily": [
        (REPO / "data/private/users.db", "users", 30),      # (원본, 이름, 보존일수)
    ],
    "weekly": [
        (REPO / "data/price_cache/price_daily.db", "price_daily", 35),
        (REPO / "data/meta/index_master.db", "index_master", 35),
    ],
}


def backup_one(src: Path, name: str, out_dir: Path) -> Path:
    """sqlite3 backup API로 스냅샷 → gzip. 임시파일 경유로 부분 파일 잔존 방지."""
    stamp = date.today().strftime("%Y%m%d")
    dest = out_dir / f"{name}_{stamp}.db.gz"
    if dest.exists():  # 같은 날 재실행 멱등
        return dest
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False, dir=out_dir) as tf:
        tmp = Path(tf.name)
    try:
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(tmp)
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()
        with open(tmp, "rb") as f_in, gzip.open(dest, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def rotate(out_dir: Path, name: str, keep_days: int) -> None:
    cutoff = datetime.now().timestamp() - keep_days * 86400
    for p in out_dir.glob(f"{name}_*.db.gz"):
        if p.stat().st_mtime < cutoff:
            p.unlink()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode not in TARGETS:
        print(f"usage: db_backup.py [daily|weekly]", file=sys.stderr)
        return 2
    out_dir = BACKUP_ROOT / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for src, name, keep in TARGETS[mode]:
        if not src.exists():
            print(f"[backup] SKIP missing {src}", file=sys.stderr)
            failures += 1
            continue
        try:
            dest = backup_one(src, name, out_dir)
            rotate(out_dir, name, keep)
            print(f"[backup] OK {dest} ({dest.stat().st_size} bytes)")
        except Exception as e:  # cron 로그(journald/mail)로 노출
            print(f"[backup] FAIL {name}: {e}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
