"""
푸시 알림 선택 동의 검증.
실행: python tests/test_push_consent.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0


def ok(name, cond):
    global _p, _f
    if cond:
        _p += 1
        print("PASS  " + name)
    else:
        _f += 1
        print("FAIL  " + name)


import modules.auth_manager as am

am.DB_PATH = Path(tempfile.mkdtemp()) / "t_users.db"
am._conn = None
am.init_db()

from modules.alerts import alert_store

alert_store.init_alerts_db()

user = am.get_or_create_user("push-test", "push@test.local", "push", "")
uid = user["id"]
am.set_user_consent(uid)

ok("기본값: 푸시 동의 없음", am.has_push_consent(uid) is False)
ok("동의 전 토큰 직접 등록 차단", alert_store.register_device_token(uid, "tok0", "android") is False)
ok("동의 전 토큰 조회 비어 있음", alert_store.get_device_tokens(uid) == [])

am.set_push_consent(uid, True)
ok("푸시 동의 저장", am.has_push_consent(uid) is True)
ok("동의 후 토큰 등록", alert_store.register_device_token(uid, "tok1", "android") is True)
ok("동의 후 토큰 조회", alert_store.get_device_tokens(uid)[0]["token"] == "tok1")

am.set_push_consent(uid, False)
ok("철회 후 토큰 비활성", alert_store.has_device_tokens(uid) is False)
ok("철회 후 전송 대상 없음", alert_store.get_device_tokens(uid) == [])

import app as appmod

appmod.app.config["TESTING"] = True
cl = appmod.app.test_client()
with cl.session_transaction() as s:
    s["user_id"] = uid

r = cl.get("/api/push/status")
j = r.get_json()
ok("API status 기본 OFF", r.status_code == 200 and j["consented"] is False and j["enabled"] is False)

r = cl.post("/api/push/register", json={"token": "tok2", "platform": "android"})
ok("API 동의 전 register 403", r.status_code == 403)

r = cl.post("/api/push/consent", json={"enabled": True})
ok("API 푸시 동의 ON", r.status_code == 200 and r.get_json()["consented"] is True)

r = cl.post("/api/push/register", json={"token": "tok2", "platform": "android"})
ok("API 동의 후 register OK", r.status_code == 200 and r.get_json()["ok"] is True)

r = cl.get("/api/push/status")
j = r.get_json()
ok("API register 후 enabled", r.status_code == 200 and j["consented"] is True and j["enabled"] is True)

r = cl.post("/api/push/disable")
ok("API disable OK", r.status_code == 200 and r.get_json()["ok"] is True)

r = cl.get("/api/push/status")
j = r.get_json()
ok("API disable 후 OFF", r.status_code == 200 and j["consented"] is False and j["enabled"] is False)

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
