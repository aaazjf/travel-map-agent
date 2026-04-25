#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/3] 安装依赖..."
pip install -r requirements.txt

if [ ! -f ".env" ]; then
  echo "[2/3] 检测到缺少 .env，正在从 .env.example 创建..."
  cp .env.example .env
else
  echo "[2/3] .env 已存在，跳过创建"
fi

echo "[3/3] 启动 Streamlit..."
streamlit run streamlit_app.py
