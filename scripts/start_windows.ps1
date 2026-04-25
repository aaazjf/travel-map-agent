$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

Write-Host "[1/3] 安装依赖..."
pip install -r requirements.txt

if (!(Test-Path -LiteralPath ".env")) {
  Write-Host "[2/3] 检测到缺少 .env，正在从 .env.example 创建..."
  Copy-Item -LiteralPath ".env.example" -Destination ".env"
} else {
  Write-Host "[2/3] .env 已存在，跳过创建"
}

Write-Host "[3/3] 启动 Streamlit..."
streamlit run streamlit_app.py
