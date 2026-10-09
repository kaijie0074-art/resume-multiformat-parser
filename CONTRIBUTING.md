# 贡献指南

## 跑测试

```bash
pip install pymupdf python-docx pytest reportlab pillow
python3 -m pytest tests/ -q
```

17 用例是合并门槛，其中 3 条"缺陷复现断言"不许删（它们固化基线缺陷的存在性）。

## 新增输入形态

线上 needs_manual 样本 → `evals/generate_corpus.py` 加生成分支 → `run_eval.py` 阈值表加组 → PR 贴前后 F1 报告。

## 改阈值/常量

layout.py / confidence.py / text_layer.py 的常量必须带依据注释，且 `test_阈值常量可追溯` 同步更新——常量断言是防"无意识漂移"的钉子。

## 分支与提交

- `main` 受保护；`fix/<编号>-<slug>` / `feat/<slug>`
- commit：`feat|fix|test|docs: 中文摘要`
