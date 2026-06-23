"""
push_sender.py
────────────────────────────────────────────────────────────────────────────────
FCM HTTP v1 푸시 전송. google-auth로 서비스계정 OAuth2 토큰 발급 후 REST 전송.

서비스계정 키 경로 = 환경변수 FCM_SERVICE_ACCOUNT_FILE (서버 파일, git 미추적).
키 없음/google-auth 미설치 시 자동 비활성(no-op) — 인앱 알림은 영향 없음.

Celery 워커(별 프로세스)에서 호출 — Flask app import 없이 동작.
"""

import os
import json
import threading

import requests

_CREDS_ENV = "FCM_SERVICE_ACCOUNT_FILE"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TIMEOUT = 10

_lock = threading.Lock()
_state = {"creds": None, "project_id": None, "loaded": False, "ok": False}


def _load():
    """서비스계정 1회 로드. 성공 여부 캐시."""
    if _state["loaded"]:
        return _state["ok"]
    _state["loaded"] = True
    path = os.environ.get(_CREDS_ENV)
    if not path or not os.path.exists(path):
        return False
    try:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(path, scopes=[_SCOPE])
        with open(path, encoding="utf-8") as f:
            project_id = json.load(f).get("project_id")
        _state["creds"] = creds
        _state["project_id"] = project_id
        _state["ok"] = bool(project_id)
    except Exception as e:
        print(f"[push_sender] 초기화 실패: {e}")
        _state["ok"] = False
    return _state["ok"]


def enabled():
    """푸시 전송 가능 여부(키+라이브러리 준비됨)."""
    return _load()


def _access_token():
    from google.auth.transport.requests import Request
    creds = _state["creds"]
    if not creds.valid:
        creds.refresh(Request())
    return creds.token


def send(token, title, body, data=None):
    """단일 토큰 전송. 반환: 'ok' | 'unregistered'(토큰 삭제 대상) | 'error'."""
    if not _load():
        return "error"
    message = {"message": {"token": token, "notification": {"title": title, "body": body}}}
    if data:
        message["message"]["data"] = {k: str(v) for k, v in data.items()}
    url = f"https://fcm.googleapis.com/v1/projects/{_state['project_id']}/messages:send"
    try:
        with _lock:
            access = _access_token()
        r = requests.post(
            url, json=message,
            headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            return "ok"
        status = ""
        try:
            status = (r.json().get("error", {}) or {}).get("status", "")
        except Exception:
            pass
        if r.status_code == 404 or status in ("NOT_FOUND", "UNREGISTERED"):
            return "unregistered"
        print(f"[push_sender] 전송 실패 {r.status_code} {status}: {r.text[:200]}")
        return "error"
    except Exception as e:
        print(f"[push_sender] 예외: {e}")
        return "error"


def send_to_user(user_id, title, body, data=None):
    """user의 전 기기에 전송. 죽은 토큰은 정리. 성공 건수 반환."""
    if not _load():
        return 0
    from modules.alerts import alert_store
    sent = 0
    for t in alert_store.get_device_tokens(user_id):
        res = send(t["token"], title, body, data)
        if res == "ok":
            sent += 1
        elif res == "unregistered":
            alert_store.delete_device_token(t["token"])
    return sent
