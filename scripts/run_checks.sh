#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "运行 memory eval..."
python evals/memory_eval.py

echo "运行 week4 regression..."
python evals/week4_regression.py

echo "全部检查完成。"
