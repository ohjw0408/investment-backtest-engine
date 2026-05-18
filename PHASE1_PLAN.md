# Phase 1: 비동기 처리 구현 계획
# 타임아웃 해결 + 실시간 진행 상황 표시

## 목표
- 시뮬 요청을 비동기로 처리해서 타임아웃 문제 해결
- 사용자에게 대기 순서, 진행률 %, 예상 시간 실시간 표시

## 완료 조건
- [ ] celery_app.py 생성
- [ ] tasks.py 생성 (진행률 콜백 포함)
- [ ] app.py에 /api/calculator/submit, /api/task/<id> 추가
- [ ] accumulation_analyzer.py에 progress_callback 파라미터 추가
- [ ] calculator.js 폴링 + 진행 상황 UI 추가
- [ ] 로컬 테스트 성공 확인

---

## Step 1: 패키지 설치

```bash
pip install celery redis
pip freeze > requirements.txt
```

---

## Step 2: celery_app.py 생성 (프로젝트 루트)

```python
from celery import Celery

celery = Celery(
    'domino',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0',
    broker_connection_retry_on_startup=True,
)

celery.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_time_limit=600,        # 최대 10분
    task_soft_time_limit=540,   # 9분 후 경고
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=10,
)
```

---

## Step 3: accumulation_analyzer.py 수정

`_run_rolling()` 메서드에 progress_callback 추가.
각 롤링 케이스 완료 후 콜백 호출.

```python
# __init__에 추가
def __init__(
    self,
    ...
    progress_callback=None,   # 추가
):
    ...
    self.progress_callback = progress_callback

# _run_rolling() 내부 루프에서 각 케이스 완료 후 추가
cases.append(metrics)

if self.progress_callback:
    self.progress_callback(
        current=run_id,
        total=total_cases,   # 미리 계산한 예상 총 케이스 수
        elapsed=time.time() - start_time,
    )
```

total_cases 계산:
```python
# data_start ~ data_end 기간에서 step_months 간격으로 몇 개 나오는지 미리 계산
from dateutil.relativedelta import relativedelta
def _estimate_total_cases(self) -> int:
    cur = self.data_start
    count = 0
    while True:
        end = cur + relativedelta(years=self.accumulation_years)
        if end > self.data_end:
            break
        count += 1
        cur += relativedelta(months=self.step_months)
    return max(count, 1)
```

---

## Step 4: tasks.py 생성 (프로젝트 루트)

```python
import time
import redis
from celery_app import celery

r = redis.Redis(host='localhost', port=6379, db=0)

def get_queue_position(task_id: str) -> int:
    """현재 큐에서 내 태스크 앞에 몇 개 있는지."""
    try:
        queue = r.lrange('celery', 0, -1)
        for i, item in enumerate(queue):
            if task_id.encode() in item:
                return i
        return 0
    except Exception:
        return 0


@celery.task(bind=True)
def run_simulation_task(self, payload: dict) -> dict:
    """
    투자 계산기 시뮬레이션 비동기 태스크.
    진행 상황을 실시간으로 업데이트.
    """
    start_time = time.time()

    def progress_callback(current: int, total: int, elapsed: float):
        eta = (elapsed / current * (total - current)) if current > 0 else None
        self.update_state(
            state='PROGRESS',
            meta={
                'current':   current,
                'total':     total,
                'percent':   round(current / total * 100),
                'elapsed':   round(elapsed),
                'eta':       round(eta) if eta else None,
                'queue_pos': 0,   # 실행 중이면 대기 없음
            }
        )

    try:
        # app.py의 핵심 로직 호출
        # (app.py에서 _run_calculator_logic 함수로 분리 필요 - Step 5 참고)
        from app import _run_calculator_logic
        result = _run_calculator_logic(payload, progress_callback=progress_callback)
        return {'status': 'SUCCESS', 'result': result}

    except Exception as e:
        import traceback
        return {
            'status': 'FAILURE',
            'error': str(e),
            'traceback': traceback.format_exc(),
        }
```

---

## Step 5: app.py 수정

### 5-1. calculator_run 핵심 로직을 함수로 분리

기존 `/api/calculator/run` 안의 로직을 `_run_calculator_logic()` 함수로 분리.
progress_callback 파라미터 추가해서 AccumulationAnalyzer에 전달.

```python
def _run_calculator_logic(body: dict, progress_callback=None) -> dict:
    """
    calculator_run의 핵심 로직.
    동기(직접 호출) / 비동기(Celery 태스크) 모두 사용.
    """
    # 기존 calculator_run 내부 로직 그대로 이동
    # AccumulationAnalyzer 생성 시 progress_callback 전달
    analyzer = AccumulationAnalyzer(
        ...
        progress_callback=progress_callback,
    )
    ...
    return result_dict
```

### 5-2. 새 엔드포인트 추가

```python
@app.route('/api/calculator/submit', methods=['POST'])
def calculator_submit():
    """비동기 시뮬 요청 → 태스크 ID 반환."""
    from tasks import run_simulation_task
    payload = request.get_json()
    task = run_simulation_task.delay(payload)
    return jsonify({'task_id': task.id, 'status': 'PENDING'})


@app.route('/api/task/<task_id>', methods=['GET'])
def task_status(task_id: str):
    """태스크 상태 조회 (프론트에서 폴링)."""
    from celery_app import celery as celery_app
    from tasks import get_queue_position

    task = celery_app.AsyncResult(task_id)

    if task.state == 'PENDING':
        queue_pos = get_queue_position(task_id)
        return jsonify({
            'status':    'PENDING',
            'queue_pos': queue_pos,
            'percent':   0,
        })

    elif task.state == 'PROGRESS':
        meta = task.info or {}
        return jsonify({
            'status':  'PROGRESS',
            'percent': meta.get('percent', 0),
            'current': meta.get('current', 0),
            'total':   meta.get('total', 0),
            'elapsed': meta.get('elapsed', 0),
            'eta':     meta.get('eta'),
        })

    elif task.state == 'SUCCESS':
        return jsonify({
            'status': 'SUCCESS',
            'result': task.result.get('result'),
        })

    else:  # FAILURE
        return jsonify({
            'status': 'FAILURE',
            'error':  str(task.info),
        })
```

### 5-3. 기존 /api/calculator/run 유지

기존 엔드포인트는 그대로 두되, 내부에서 `_run_calculator_logic` 호출하도록만 변경.
(하위 호환성 유지)

---

## Step 6: calculator.js 수정

`runCalculator()` 함수를 비동기 폴링 방식으로 교체.

```javascript
async function runCalculator() {
    // 기존 validation 로직 유지 ...

    const btn = document.getElementById('runBtn');
    btn.disabled = true;

    showProgressUI();  // 진행 UI 표시

    try {
        // 1. 태스크 제출
        const submitRes = await fetch('/api/calculator/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const { task_id } = await submitRes.json();

        // 2. 폴링
        const result = await pollTask(task_id);

        // 3. 결과 렌더링
        hideProgressUI();
        renderResult(result, { years: payload.years });

    } catch (err) {
        hideProgressUI();
        alert('오류: ' + err.message);
    } finally {
        btn.disabled = false;
        document.getElementById('runBtnText').style.display = 'inline';
        document.getElementById('runBtnSpinner').style.display = 'none';
    }
}


async function pollTask(taskId, maxWait = 600000) {
    const start = Date.now();

    while (Date.now() - start < maxWait) {
        await new Promise(r => setTimeout(r, 1500));

        const res  = await fetch(`/api/task/${taskId}`);
        const data = await res.json();

        if (data.status === 'PENDING') {
            updateProgressUI({
                phase:    '대기 중',
                queuePos: data.queue_pos,
                percent:  0,
                eta:      null,
            });

        } else if (data.status === 'PROGRESS') {
            updateProgressUI({
                phase:   '계산 중',
                percent: data.percent,
                current: data.current,
                total:   data.total,
                elapsed: data.elapsed,
                eta:     data.eta,
            });

        } else if (data.status === 'SUCCESS') {
            return data.result;

        } else if (data.status === 'FAILURE') {
            throw new Error(data.error || '시뮬레이션 실패');
        }
    }
    throw new Error('시간 초과 (10분)');
}


// ── 진행 상황 UI ──────────────────────────────────────────
function showProgressUI() {
    document.getElementById('runBtnText').style.display    = 'none';
    document.getElementById('runBtnSpinner').style.display = 'inline';

    // 결과 패널에 진행 상황 오버레이 표시
    const empty = document.getElementById('resultEmpty');
    empty.style.display = 'flex';
    empty.innerHTML = `
        <div style="width:100%;padding:24px;">
            <div id="progressPhase"
                 style="font-size:0.9rem;color:var(--text-muted);margin-bottom:8px;">
                준비 중...
            </div>
            <div style="background:var(--border);border-radius:8px;height:8px;overflow:hidden;margin-bottom:8px;">
                <div id="progressBar"
                     style="background:var(--blue);height:100%;width:0%;transition:width 0.5s;border-radius:8px;">
                </div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:var(--text-muted);">
                <span id="progressDetail">계산 준비 중</span>
                <span id="progressEta"></span>
            </div>
        </div>`;
    document.getElementById('resultContent').style.display = 'none';
}

function updateProgressUI({ phase, queuePos, percent, current, total, elapsed, eta }) {
    const phaseEl  = document.getElementById('progressPhase');
    const barEl    = document.getElementById('progressBar');
    const detailEl = document.getElementById('progressDetail');
    const etaEl    = document.getElementById('progressEta');
    if (!phaseEl) return;

    if (queuePos > 0) {
        phaseEl.textContent  = `⏳ 대기 중 — 내 앞에 ${queuePos}개`;
        barEl.style.width    = '0%';
        detailEl.textContent = '이전 요청 처리 중...';
        etaEl.textContent    = '';
    } else {
        phaseEl.textContent  = `🔄 ${phase || '계산 중'} (${percent || 0}%)`;
        barEl.style.width    = `${percent || 0}%`;
        if (current && total) {
            detailEl.textContent = `${current} / ${total} 케이스`;
        }
        if (eta) {
            const m = Math.floor(eta / 60);
            const s = eta % 60;
            etaEl.textContent = m > 0
                ? `약 ${m}분 ${s}초 남음`
                : `약 ${s}초 남음`;
        }
    }
}

function hideProgressUI() {
    const empty = document.getElementById('resultEmpty');
    empty.style.display = 'none';
}
```

---

## Step 7: 로컬 테스트

### Windows (터미널 3개)

```bash
# 터미널 1: Redis 실행
# Redis 설치: https://github.com/microsoftarchive/redis/releases
redis-server

# 터미널 2: Celery worker 실행
# (venv 활성화 후)
celery -A celery_app worker --loglevel=info --concurrency=4 --pool=solo

# 터미널 3: Flask 실행
python app.py
```

### Mac / Linux

```bash
# 터미널 1
redis-server

# 터미널 2
celery -A celery_app worker --loglevel=info --concurrency=4

# 터미널 3
python app.py
```

### 테스트 확인 항목
- [ ] SPY 시뮬 실행 → 진행바 뜨는지
- [ ] 진행률 % 변하는지
- [ ] 예상 시간 표시되는지
- [ ] 여러 탭에서 동시 요청 시 대기 순서 표시되는지
- [ ] 결과 정상 렌더링되는지
- [ ] 기존 /api/calculator/run도 정상 동작하는지 (하위 호환)

---

## 주의 사항

- Windows에서 Celery 실행 시 `--pool=solo` 옵션 필요
- Redis가 없으면 `pip install redis` + Redis 서버 설치 필요
- tasks.py에서 `from app import _run_calculator_logic` 순환 참조 주의
  → app.py 대신 별도 calculator_logic.py로 분리하는 게 안전