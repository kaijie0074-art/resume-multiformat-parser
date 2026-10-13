# 真实 VLM 端到端评估实跑记录 · 2026-10-13（语料修复修订版）

## 本轮修复：图片型语料与真值系统性不匹配（真缺陷）

**诊断链**（全部实测，非猜测）：

1. 图片型 R 恒低（0.29–0.32）且转写出现 `XXXXXXXXXX`、标签有值无
2. 嵌入位图经独立视觉通道复核：**"姓名："等标签后本来就是空的**——语料图片里根本没有中文值可转写
3. 根因定位到 `evals/generate_corpus.py`：`gen_scanned` 依赖 `/System/Library/Fonts/PingFang.ttc`，加载失败时**静默 fallback 到 `ImageFont.load_default()`（无 CJK 字形）**——中文值全部没画上图；而 ground_truth 从数据字典生成，与图片脱节
4. 本机实测 `PingFang.ttc` 无法被 PIL 打开（cannot open resource），但 Hiragino/STHeiti/Arial Unicode 等 6 个 CJK 字体可用

**修复**（两层）：

- `generate_corpus.py`：CJK 字体候选列表（PingFang→Hiragino→STHeiti→Arial Unicode→Songti）+ 全部失败时**显式 RuntimeError**（拒绝静默生成残缺语料）
- `resume_parser/ocr_backend.py`：`VlmOcrBackend` 增加豆腐块守卫——转写含 ≥10 个 `□`/`U+FFFD` 时升档 180dpi 重试一次自愈（应对端点图片预处理非确定），择优保留

## 修复前后实测（全量 35 语料，模型 glm-4v-flash）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 图片型 F1（基线→加固） | 0.00 → 0.43 | 0.00 → **0.78** |
| 图片型 R | 0.29 | **0.78** |
| 双栏 / 单栏 / docx | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00（不受影响） |

- 真值种子稳定：重生成 35 份 ground_truth 与库内**字节级一致**，仅 scanned 图片渲染修复
- 剩余 0.22 损失的错误模式：work 三元组转写噪声（措辞/标点差异 15 例）、name 1 例、scalar_extra 1 例——正常 OCR 噪声范畴，无系统性丢失
- 首轮记录的"Coding Plan 端点图片预处理非确定"结论维持（同图两次结果可不同）——豆腐块守卫即为其工程对策

## 离线回归

`pytest tests/` 16 passed 1 skipped（VLM live 部分 env-gated）；`check_artifacts --corpus-only` PASS。
