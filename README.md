# resume-multiformat-parser

**简历多格式解析路由**——上传入口的第一公里：文本层判空、双栏版面重排、docx 表格去重、OCR 后端抽象与字段级 F1 评估。针对"图片型 PDF 空文本静默喂 LLM → 模型编造整份简历"、"双栏模板左右交错 → 职责挂错公司"这两类入口级事故的工程加固。

> 语料说明：35 份评估语料全部程序合成（固定种子，无真实 PII）；OCR 路径接真实后端——自托管 PaddleOCR（`RESUME_PARSER_PADDLE_URL`）或多模态 LLM 直读（`RESUME_PARSER_VLM_API_KEY` + `RESUME_PARSER_VLM_URL`，OpenAI 兼容协议），未配置时显式失败、拒绝静默返回空结果。上游开源项目（PP-StructureV3/PyMuPDF/pdfplumber/docling/OpenResume）仅作机制引用，见 [docs/open-source-references.md](docs/open-source-references.md)。

## 为什么值得看

基线（v0.1.0：线性抽取）实拍：

- **双栏模板 F1=0.78**——公司 A 的职责挂到公司 B 名下
- **图片型 F1=0.00**——空文本层静默通过，下游 LLM 基于岗位描述编造整份简历

加固后（同一批语料）：双栏 **1.00**、图片型 **0.92**（OCR 路径）、docx 1.00、单栏 1.00。全部数字 `bash scripts/reproduce.sh` 一键复现。

## 快速开始

要求：Python 3.10+；`pip install pymupdf python-docx pytest reportlab pillow`

```bash
python3 evals/generate_corpus.py   # 生成/校验 35 份语料（已入库，可跳过）
python3 -m pytest tests/ -q        # 17 用例（含 3 条缺陷复现断言 + F1 阈值）
bash scripts/reproduce.sh          # 基线 vs 加固分组 F1 全程复现
python3 scripts/check_artifacts.py # 工件自检
```

## 架构一览

```
上传 → router（可解释决策：kind / text_layer / layout + reason）
  ├─ 单栏 PDF → 词坐标行聚类
  ├─ 双栏 PDF → x0 间隙分界 → 先左后右重排（页眉通栏豁免）
  ├─ 图片型  → OcrBackend（Paddle / VLM 两真实实现同接口；未配置显式失败）
  └─ .docx   → 段落+表格流（合并单元格去重）
       ↓
  fields 规则抽取（缺失=None，绝不推测）→ confidence（来源层先验）→ needs_manual 回退用户补全
```

## 文档路径

- [问题报告 RPI-001/002/003](docs/issue-reports/RPI-001-multiformat-parsing.md)
- [复现材料](docs/reproductions/README.md) / [设计](docs/design.md)
- [开源调研引用](docs/open-source-references.md) / [修复引用](docs/repair-references.md)
- [回归记录](docs/regression-records/多格式解析加固-回归记录-20261013.md)
- [评审意见](docs/reviews/R1-评审意见-20261013.md) / [采纳记录](docs/reviews/采纳记录.md) / [人工评审](docs/reviews/人工评审-代码走查-20261013.md)
- [负责人验收](docs/acceptance.md) / [覆盖场景说明](docs/test-coverage.md)
- [CHANGELOG](CHANGELOG.md) / [任务地图](work/wayfinder-map.md)

## License

MIT。
