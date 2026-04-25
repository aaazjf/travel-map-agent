$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

Write-Host "运行 memory eval..."
python evals/memory_eval.py

Write-Host "运行 week4 regression..."
python evals/week4_regression.py

Write-Host "全部检查完成。"
