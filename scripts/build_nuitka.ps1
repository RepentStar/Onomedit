# Nuitka 打包脚本（Windows）：产物 dist\onomedit.exe（单文件）
# 在 uv 环境中打包：nuitka/zstandard 为 dev 依赖（uv sync 后即可用）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Nuitka 打包开始 =="

uv run python -m nuitka `
    --onefile `
    --assume-yes-for-downloads `
    --enable-plugin=tk-inter `
    --include-package=onomedit `
    --include-package=ttkbootstrap `
    --include-package-data=ttkbootstrap `
    --include-package=tkinterdnd2 `
    --include-package-data=tkinterdnd2 `
    --include-package=PIL `
    --windows-console-mode=force `
    --output-dir=dist `
    --output-filename=onomedit.exe `
    scripts/nuitka_entry.py

if ($LASTEXITCODE -ne 0) { throw "Nuitka 打包失败" }

Write-Host ""
Write-Host "打包完成: dist\onomedit.exe"
