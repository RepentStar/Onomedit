# Rust 发布物端到端验证。测试只调用已构建的 exe，不依赖 Python 或开发环境入口。
[CmdletBinding()]
param(
    [string]$FullExecutable = (Join-Path $PSScriptRoot "..\target\release\onomedit.exe"),
    [string]$CliExecutable = (Join-Path $PSScriptRoot "..\target\release\onomedit-cli.exe")
)

$ErrorActionPreference = "Stop"

function Resolve-Executable([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "发布物不存在: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    $output = & $Executable @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "命令失败 ($LASTEXITCODE): $Executable $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return $output
}

$full = Resolve-Executable $FullExecutable
$cli = Resolve-Executable $CliExecutable
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("onomedit_release_e2e_" + [guid]::NewGuid().ToString("N"))
$previousAppData = $env:APPDATA

New-Item -ItemType Directory -Path $tempRoot | Out-Null
$env:APPDATA = Join-Path $tempRoot "appdata"

try {
    Write-Host "== 发布物 smoke =="
    Invoke-Checked $full @("version") | Out-Host
    Invoke-Checked $full @("help", "rename") | Out-Null
    Invoke-Checked $cli @("version") | Out-Host
    Invoke-Checked $cli @("help", "rename") | Out-Null

    $source = Join-Path $tempRoot "a.txt"
    $renamed = Join-Path $tempRoot "renamed.txt"
    [IO.File]::WriteAllText($source, "payload", [Text.UTF8Encoding]::new($false))

    Write-Host "== 隔离配置 =="
    Invoke-Checked $cli @("config", "set", "open_editor", "false") | Out-Null
    Invoke-Checked $cli @("config", "set", "expand_subdirs", "false") | Out-Null
    Invoke-Checked $cli @("config", "set", "exclude.hidden", "false") | Out-Null
    $rules = '[{"scope":"stem","kind":"replace","find":"a","replace":"renamed"}]'
    Invoke-Checked $cli @("config", "set", "auto_rules", $rules) | Out-Null
    $config = Invoke-Checked $cli @("config")
    if (($config -join "`n") -notmatch '"auto_rules"') {
        throw "config 输出缺少 auto_rules"
    }

    Write-Host "== rename / history / restore =="
    Invoke-Checked $cli @("rename", $source, "--no-editor") | Out-Host
    if ((Test-Path -LiteralPath $source) -or -not (Test-Path -LiteralPath $renamed)) {
        throw "rename 后文件树不符合预期"
    }

    $history = Invoke-Checked $cli @("history")
    if (($history -join "`n") -notmatch [regex]::Escape($renamed)) {
        throw "history 缺少重命名目标"
    }

    Invoke-Checked $cli @("restore") | Out-Host
    if (-not (Test-Path -LiteralPath $source) -or (Test-Path -LiteralPath $renamed)) {
        throw "restore 后文件树不符合预期"
    }

    Write-Host "== dry-run =="
    Invoke-Checked $cli @("rename", $source, "--no-editor", "--dry-run") | Out-Host
    if (-not (Test-Path -LiteralPath $source) -or (Test-Path -LiteralPath $renamed)) {
        throw "dry-run 修改了文件树"
    }

    Write-Host "Rust 发布物 E2E 全部通过"
}
finally {
    if ($null -eq $previousAppData) {
        Remove-Item Env:APPDATA -ErrorAction SilentlyContinue
    }
    else {
        $env:APPDATA = $previousAppData
    }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
