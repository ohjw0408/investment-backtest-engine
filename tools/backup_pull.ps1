# Money Milestone 백업 pull (오너 PC 오프박스 2차 백업)
# 서버 /root/backups/{daily,weekly}의 .gz 중 로컬에 없는 것만 scp로 내려받는다.
# 등록: Windows 작업 스케줄러 (tools/backup_pull_register.ps1 1회 실행)
# 로그: $LocalRoot\pull.log

$ErrorActionPreference = "Stop"

$Server    = "root@178.105.84.213"
$KeyPath   = Join-Path $env:USERPROFILE ".ssh\hetzner_ed25519"
$LocalRoot = Join-Path $env:USERPROFILE "MoneyMilestoneBackups"
$LogFile   = Join-Path $LocalRoot "pull.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Host $line
}

New-Item -ItemType Directory -Force -Path $LocalRoot | Out-Null

try {
    # 원격 파일 목록 (상대경로: daily/xxx.gz, weekly/xxx.gz)
    $remoteList = & ssh -i $KeyPath -o BatchMode=yes -o ConnectTimeout=15 $Server `
        "cd /root/backups && find daily weekly -name '*.db.gz' -type f"
    if ($LASTEXITCODE -ne 0) { throw "ssh list failed (exit $LASTEXITCODE)" }

    $pulled = 0
    foreach ($rel in $remoteList) {
        $rel = $rel.Trim()
        if (-not $rel) { continue }
        $localPath = Join-Path $LocalRoot ($rel -replace '/', '\')
        if (Test-Path $localPath) { continue }
        $localDir = Split-Path $localPath -Parent
        New-Item -ItemType Directory -Force -Path $localDir | Out-Null
        & scp -i $KeyPath -o BatchMode=yes -q "${Server}:/root/backups/$rel" $localPath
        if ($LASTEXITCODE -ne 0) { throw "scp failed: $rel" }
        Log "PULLED $rel ($((Get-Item $localPath).Length) bytes)"
        $pulled++
    }

    # 로컬 로테이션: 서버 보존(30/35일)보다 긴 90일 보존
    $cutoff = (Get-Date).AddDays(-90)
    Get-ChildItem -Path $LocalRoot -Recurse -Filter "*.db.gz" |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object { Log "ROTATE-DEL $($_.Name)"; Remove-Item $_.FullName -Force -Confirm:$false }

    Log "DONE pulled=$pulled"
    exit 0
}
catch {
    Log "FAIL $($_.Exception.Message)"
    exit 1
}
