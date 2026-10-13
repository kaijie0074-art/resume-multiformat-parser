# 修复引用（问题 → 实现 → 测试对照）

| 问题编号 | 故障 | 修复模块 | commit 主题 | 测试 |
|---|---|---|---|---|
| RPI-001-a | 不区分输入类型 | `router.py`（kind/text_layer/layout + reason 可解释路由） | feat: 可解释路由 | `test_路由_*` 4 用例 |
| RPI-001-b | 双栏交错 | `layout.py`（x0 间隙分界 + 先左后右重排 + 页眉通栏豁免） | feat: 版面感知重排 | `test_双栏_公司A职责不串到公司B`、`test_双栏_页眉通栏不被切分_评审2` |
| RPI-001-c | 朴素邻近启发式错挂 | `fields.py` v1.0.0（标题过滤 + 二次出现回填；naive 参数保留基线行为） | fix: 经历块启发式 | `test_双栏_基线线性抽取职责错挂_复现缺陷` |
| RPI-002-a | 图片型静默失败 | `router.route_pdf` 文本层判空（<40 字符） | feat: 文本层判空 | `test_图片型_基线空文本全空_复现缺陷` |
| RPI-002-b | 无 OCR 显式失败 | `ocr_backend.py`（三实现同接口；未配置抛含配置指引的错误） | feat: OCR 后端抽象 | `test_图片型_无OCR后端显式失败不编造` |
| RPI-002-c | OCR 回放确定性 | `RecordedOcrBackend` + evals/ocr_fixtures（固定种子劣化） | test: OCR 回放 | `test_图片型_OCR回放抽出全部字段` |
| RPI-003 | docx 表格粉碎/重复 | `docx_parser.py`（文档流顺序 + 合并单元格按 tc 去重） | fix: docx 去重 | `test_docx_合并单元格不重复`、`test_docx_表格与段落字段齐` |
| RPI-通用 | 缺失字段无信号 | `confidence.py`（来源层置信度 + needs_manual + warnings） | feat: 置信度与回退 | `test_缺失字段needs_manual与告警`、`test_置信度_来源层与启发式折扣` |
| L 回归 | 无评估 | `evals/run_eval.py`（35 语料分组 F1 + 错误模式分类）+ 阈值测试 | feat: 字段级评估 | `test_全语料分组F1达标`、`test_基线在图片型上F1为零` |

## 过程缺陷（修复中实测发现，回归记录留档）

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | reportlab 默认字体不支持中文（语料文本层为空） | 注册 STSong-Light CID 字体 |
| 2 | 双栏语料按"先整左栏后整右栏"绘制——不足以复现交错缺陷 | 改为按视觉行序交错绘制（对齐真实模板内容流） |
| 3 | 日期区间正则 group() 带尾随空格 → 三元组全错 | 统一 strip() |
| 4 | OCR 劣化打断 ASCII（电话/邮箱匹配失败） | 劣化只作用于汉字间 |
| 5 | 评估口径不容错全角/半角标点 | 比较前 NFKC + 标点归一化 |

## PR 索引

- PR #1（fix/multiformat → main）：承载上表全部修复；评审见 docs/reviews/。
