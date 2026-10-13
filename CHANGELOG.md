# CHANGELOG

## [1.1.0] - 2026-10-13

移除全部模拟元素，OCR 路径接真实后端。

- 删除 `RecordedOcrBackend` 与 `evals/ocr_fixtures/` 回放语料及 `generate_corpus.py` 的 OCR 噪声劣化生成
- `VlmOcrBackend` 从未实现桩改为真实实现：PyMuPDF 页级渲染 → OpenAI 兼容多模态 `/chat/completions` 转写（`RESUME_PARSER_VLM_API_KEY`/`RESUME_PARSER_VLM_URL`/`RESUME_PARSER_VLM_MODEL`）
- `run_eval.py` 按环境变量选择真实后端；未配置时图片型组显式跳过并在报告标注
- 图片型字段抽取测试改为 env-gated live 测试；路由判空改为直测 router，离线可跑

## [1.0.0] - 2026-10-13

合并 PR #1（fix/multiformat → main），负责人验收通过。

### 修复（相对 v0.1.0-baseline）

- **路由层**：可解释决策（kind/text_layer/layout/reason）；.doc 显式拒绝
- **双栏重排**：词坐标 x0 间隙分界 + 先左后右 + 页眉通栏豁免——双栏 F1 0.78 → 1.00
- **图片型路径**：文本层判空（<40 字符）→ OcrBackend；未配置显式失败（防下游 LLM 编造）——F1 0.00 → 0.92
- **docx**：文档流顺序 + 合并单元格去重
- **字段层**：v1.0.0 启发式（标题过滤 + 二次回填），naive 参数保留基线行为
- **置信度**：来源层先验 + needs_manual + warnings
- **评估**：35 语料分组 F1 + 错误模式分类 + 标点归一化口径

### 评审与验收

- 6 条意见采纳、1 条部分采纳（双栏几何法 vs 版面模型的边界折中）
- 5 个过程实测缺陷留档（回归记录）
- 17 测试全绿；CI 上线

## [0.1.0-baseline] - 2026-10-09

初始实现：线性抽取 + 朴素邻近启发式。

**已知缺陷**（RPI-001/002/003）：双栏 F1 0.78（职责错挂）、图片型 F1 0.00（空文本静默失败）、docx 合并单元格重复风险。
