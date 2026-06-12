"""로컬 E2E용 Flask 세션 쿠키 발급 헬퍼.

로컬 dev 서버(FLASK_SECRET_KEY 동일 프로세스 환경)에서만 유효 — 라이브 키는 모름.
테스트 사용자(e2e-local@test.com)를 users.db에 생성하고 서명된 session 쿠키를 출력한다.

사용: venv\\Scripts\\python.exe tests\\mint_session.py  →  stdout = 쿠키 값 한 줄
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app                      # noqa: E402
from modules.auth_manager import get_or_create_user   # noqa: E402
from flask.sessions import SecureCookieSessionInterface  # noqa: E402

user = get_or_create_user("e2e-local", "e2e-local@test.com", "E2E로컬", "")
serializer = SecureCookieSessionInterface().get_signing_serializer(app)
print(serializer.dumps({"user_id": user["id"]}))
