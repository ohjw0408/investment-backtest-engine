# Phase 3: 서버 배포 계획
# Vultr Ubuntu 22.04 기준

## 서버 정보
- IP: 216.128.152.205
- User: root
- OS: Ubuntu 22.04

## 완료 조건
- [ ] 서버에 Python, Redis, Nginx 설치
- [ ] GitHub에서 코드 clone
- [ ] 가상환경 설정 및 패키지 설치
- [ ] Gunicorn systemd 서비스 등록
- [ ] Celery systemd 서비스 등록
- [ ] Nginx 설정
- [ ] 브라우저에서 http://216.128.152.205 접속 확인

---

## Step 1: 서버 기본 설정

```bash
# 서버 접속
ssh root@216.128.152.205

# 패키지 업데이트
apt update && apt upgrade -y

# 필수 패키지 설치
apt install -y python3.11 python3.11-venv python3-pip git nginx redis-server

# Redis 자동 시작 설정
systemctl enable redis-server
systemctl start redis-server

# Redis 동작 확인
redis-cli ping  # PONG 나오면 정상
```

---

## Step 2: 앱 배포

```bash
# 프로젝트 디렉토리로 이동
cd /root

# GitHub에서 clone (본인 repo 주소로 변경)
git clone https://github.com/<유저명>/<레포명>.git
cd <레포명>

# 가상환경 생성 및 활성화
python3.11 -m venv venv
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt
pip install gunicorn

# 로그 디렉토리 생성
mkdir -p /root/logs
```

---

## Step 3: 환경변수 설정

```bash
# .env 파일 생성 (로컬 .env 내용 붙여넣기)
nano .env
```

---

## Step 4: Gunicorn 설정

**gunicorn.conf.py** 생성:
```python
bind = "127.0.0.1:5000"
workers = 2
worker_class = "sync"
timeout = 30
keepalive = 2
errorlog = "/root/logs/gunicorn_error.log"
accesslog = "/root/logs/gunicorn_access.log"
loglevel = "info"
preload_app = True
```

---

## Step 5: systemd 서비스 등록

**/etc/systemd/system/domino.service**
```ini
[Unit]
Description=Money Milestone Flask App
After=network.target

[Service]
User=root
WorkingDirectory=/root/<레포명>
Environment="PATH=/root/<레포명>/venv/bin"
ExecStart=/root/<레포명>/venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**/etc/systemd/system/domino-celery.service**
```ini
[Unit]
Description=Money Milestone Celery Worker
After=network.target redis.service

[Service]
User=root
WorkingDirectory=/root/<레포명>
Environment="PATH=/root/<레포명>/venv/bin"
ExecStart=/root/<레포명>/venv/bin/celery -A celery_app worker --loglevel=info --concurrency=1 --logfile=/root/logs/celery.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 등록 및 시작
systemctl daemon-reload
systemctl enable domino domino-celery
systemctl start domino domino-celery

# 상태 확인
systemctl status domino
systemctl status domino-celery
```

---

## Step 6: Nginx 설정

**/etc/nginx/sites-available/domino**
```nginx
server {
    listen 80;
    server_name 216.128.152.205;

    location /static/ {
        alias /root/<레포명>/static/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }
}
```

```bash
# Nginx 설정 활성화
ln -s /etc/nginx/sites-available/domino /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default  # 기본 페이지 제거
nginx -t  # 설정 오류 확인
systemctl restart nginx
```

---

## Step 7: 방화벽 설정

```bash
# Vultr는 기본적으로 포트 열려있지만 확인
ufw allow 80
ufw allow 443
ufw allow 22
```

---

## Step 8: 배포 스크립트 (deploy.sh)

로컬에서 실행하는 배포 자동화 스크립트:

```bash
#!/bin/bash
set -e

SERVER="root@216.128.152.205"
APP_DIR="/root/<레포명>"

echo "🚀 배포 시작..."

ssh $SERVER << 'REMOTE'
    cd /root/<레포명>
    git pull origin main
    source venv/bin/activate
    pip install -r requirements.txt -q
    systemctl restart domino
    systemctl restart domino-celery
    echo "✅ 배포 완료"
REMOTE
```

로컬에서 사용:
```bash
bash deploy.sh
```

---

## 확인 방법

```bash
# 서비스 상태
systemctl status domino
systemctl status domino-celery

# 로그 확인
tail -f /root/logs/gunicorn_error.log
tail -f /root/logs/celery.log

# Nginx 로그
tail -f /var/log/nginx/error.log
```

브라우저에서 http://216.128.152.205 접속해서 앱 뜨면 성공.

---

## 주의사항
- <레포명>은 실제 GitHub 레포 이름으로 교체
- .env 파일은 git에 올리면 안 됨 (.gitignore 확인)
- 1 vCPU라서 Celery concurrency=1로 설정