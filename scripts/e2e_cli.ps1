# CLI 端到端验证：隔离配置 → 设置假编辑器 → rename → history → restore
$ErrorActionPreference = "Stop"
$root = "D:\git\Onomedit"
$tmp = Join-Path $env:TEMP ("onomedit_e2e_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
$env:APPDATA = (Join-Path $tmp "appdata")  # 隔离配置，避免污染真实 %APPDATA%
Write-Host "== 临时目录: $tmp"

Set-Content -Path (Join-Path $tmp "a.txt") -Value "1" -Encoding utf8
Set-Content -Path (Join-Path $tmp "b.txt") -Value "2" -Encoding utf8
Set-Content -Path (Join-Path $tmp "c.txt") -Value "3" -Encoding utf8

Push-Location $root
try {
    # 1. 配置假编辑器：把临时文件第 1 行（a.txt 的 stem "a"）改为 renamed
    uv run onomedit config set-editor "python D:\git\Onomedit\tests\fakeditor.py set 1 renamed"
    if ($LASTEXITCODE -ne 0) { throw "set-editor 失败" }

    # 2. rename：拉起假编辑器 → 保存 → 重命名
    Write-Host "== rename =="
    uv run onomedit rename (Join-Path $tmp "a.txt")
    if ($LASTEXITCODE -ne 0) { throw "rename 失败" }
    if (-not (Test-Path (Join-Path $tmp "renamed.txt"))) { throw "renamed.txt 未生成" }
    if (Test-Path (Join-Path $tmp "a.txt")) { throw "a.txt 应已被改名" }

    # 3. history 应包含 a -> renamed
    Write-Host "== history =="
    $hist = uv run onomedit history
    if ($LASTEXITCODE -ne 0) { throw "history 失败" }
    $hist
    if ($hist -notmatch "renamed") { throw "history 缺少 renamed 记录" }

    # 4. restore 恢复上次
    Write-Host "== restore =="
    uv run onomedit restore
    if ($LASTEXITCODE -ne 0) { throw "restore 失败" }
    if (-not (Test-Path (Join-Path $tmp "a.txt"))) { throw "恢复后 a.txt 应存在" }

    # 5. dry-run 通配符预览（不执行）
    Write-Host "== dry-run =="
    uv run onomedit rename (Join-Path $tmp "*.txt") --dry-run --timeout 5
    if ($LASTEXITCODE -ne 0) { throw "dry-run 失败" }

    # 6. config 查看
    Write-Host "== config =="
    uv run onomedit config | Select-Object -First 5

    Write-Host ""
    Write-Host "E2E CLI 全部通过 ✔"
}
finally {
    Pop-Location
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
