#!/usr/bin/env python3
"""工件自检：evidence 指标、语料数量、真值齐、无 TODO 残留。"""
from __future__ import annotations

import json
import math
import re
import sys
corpus_only = "--corpus-only" in sys.argv

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fail = False

ev = ROOT / "evidence" / "latest-run.json"
if corpus_only:
    pass  # CI 语料一致性阶段只查语料/真值/残留
elif not ev.exists():
    print("缺 evidence/latest-run.json"); fail = True
else:
    d = json.loads(ev.read_text(encoding="utf-8"))
    # 分组下限：与 tests/test_parser.py 的阈值一致
    floors = {"single": 0.95, "two-col": 0.95, "scanned": 0.85, "docx": 0.95}
    for g, floor in floors.items():
        got = d[g]["hardened_f1"]
        if not got >= floor:
            print(f"{g} 加固 F1={got} < {floor}"); fail = True
    if d["scanned"]["baseline_f1"] != 0.0:
        print("图片型基线 F1 应为 0（空文本层复现）"); fail = True
    print("evidence 指标达标:", {g: d[g]["hardened_f1"] for g in floors})

corpus = list((ROOT / "evals" / "corpus").iterdir())
gt = list((ROOT / "evals" / "ground_truth").iterdir())
if len(corpus) != 35 or len(gt) != 35:
    print(f"语料/真值数量异常: {len(corpus)}/{len(gt)} != 35"); fail = True

for py in (ROOT / "resume_parser").rglob("*.py"):
    if re.search(r"TODO|FIXME", py.read_text(encoding="utf-8")):
        print(f"{py} 存在 TODO/FIXME"); fail = True

print("check_artifacts:", "PASS" if not fail else "FAIL")
sys.exit(1 if fail else 0)
