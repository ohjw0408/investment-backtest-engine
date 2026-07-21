# prod gunicorn 설정. 2026-07-21까지 서버에만 있고 repo에는 없었다.
#
# ⚠️ 이 파일은 이제 repo가 단일 진실원천이다. 배포가 `git reset --hard`를 돌리므로
#    prod에서 직접 고치면 다음 배포에 되돌아간다. 변경은 push로만.
#
# ⚠️ timeout은 코드와 물려 있다. 요청 경로에서 외부 API를 부르는 곳
#    (`app.py::_live_asset_prices`의 KRX 호출 등)은 이 값보다 확실히 짧은
#    예산을 써야 한다. 넘기면 worker가 SIGKILL되고 nginx가 500을 낸다.
#    2026-07-21 "내 자산 0원" 장애가 정확히 이것 — KRX 30s × 2시장 = 60s > 30s.
#    지금 KRX 예산은 (3s connect, 6s read) × 2 = 최대 18s.
#
# workers=2 는 1 vCPU / 4GB 기준.

bind = "127.0.0.1:5000"
workers = 2
worker_class = "sync"
timeout = 30
keepalive = 2
errorlog = "/root/logs/gunicorn_error.log"
accesslog = "/root/logs/gunicorn_access.log"
loglevel = "info"
preload_app = True
