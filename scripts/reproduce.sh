#!/usr/bin/env bash
# 复现：基线 vs 加固的分组 F1 对比 + 测试
set -euo pipefail
cd "$(dirname "$0")/.."

echo "### 生成/校验语料（35 份，固定种子）"
python3 evals/generate_corpus.py

echo
echo "### 基线 vs 加固 分组 F1"
python3 evals/run_eval.py

echo
echo "### 全量测试"
python3 -m pytest tests/ -q
