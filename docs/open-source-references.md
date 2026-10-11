# 开源调研引用

> 调研日期：2026-10-11。引用公开机制作为选型依据，不声称任何上游项目存在本项目缺陷。

| 项目 | 链接 | 机制一句话 | 本项目借鉴点 | 采用与否 |
|---|---|---|---|---|
| PaddleOCR / PP-StructureV3 | https://github.com/PaddlePaddle/PaddleOCR | 版面感知文档解析管线（版面区域检测→按区域恢复阅读顺序→OCR/表格/公式分支） | **"版面先于文字"思想**：layout.py 的栏检测与阅读顺序重排是该思想在词坐标层的轻量实现 | 未直接部署（需 Python AI 服务+模型资产）：演练以 RecordedOcrBackend 等价回放其输出位；生产走 PaddleOcrBackend 桩 |
| PyMuPDF | https://github.com/pymupdf/PyMuPDF | PDF 结构化访问（文本层抽取、词坐标 get_text("words")、页面渲染） | 文本层判空（router 的探测基础）与词坐标 API（layout.py 全部几何计算的数据源） | 直接采用 |
| pdfplumber | https://github.com/jsvine/pdfplumber | 词/字符坐标 API + 表格抽取；其 discussion #1247 即"按 x0 间隙分离双栏" | **双栏检测方法源头**：x0 间隙找分界线 | 方法借鉴；运行时未引依赖（PyMuPDF 已覆盖词坐标，少一个 3MB+ 依赖） |
| docling | https://github.com/docling-project/docling | 文档解析框架：带坐标的统一文档模型 + 表格结构识别 | 统一中间表示（词/行/块带 bbox）的架构参照 | 未采用：重型框架（含模型），单文件解析路径用不到其 80% 能力 |
| OpenResume | https://github.com/xitanggg/OpenResume | 开源简历构建器+解析器（ATS 友好） | **字段口径参照**：name/phone/email/education/experience 的结构定义 | 口径参照，未引代码（其解析面向自家模板格式） |
| Apache POI HWPF | https://poi.apache.org/ | Java 生态 Word 解析；HWPF 对 .doc 老格式表格支持残缺 | **为什么只支持 .docx**：.doc 老格式跨行合并单元格抽取错误率高（问题报告 RPI-003 的背景），明确拒绝并提示转换 | 背景参照：路由层对 .doc 显式 ValueError 拒绝 |
| tesseract / PaddleOCR 引擎 | https://github.com/tesseract-ocr/tesseract | 传统 OCR | 未采用：中文简历版面+表格场景下传统 OCR 管线维护成本高于版面感知方案 | — |

## 结论

解析问题的解空间是**路由**，不是单选：

```
上传 → 判文本层（PyMuPDF 试抽，<40 字符 → 图片型）
  ├─ 有文本层 + 单栏 → 词坐标行聚类直接抽
  ├─ 有文本层 + 双栏 → x0 间隙分界 → 先左后右重排（+页眉通栏豁免）
  ├─ 无文本层 → OCR 后端（回放/Paddle/VLM 三实现同接口）
  └─ .docx → 段落+表格流；.doc → 显式拒绝
       ↓
  字段抽取（规则）→ 缺失=None+降置信 → needs_manual 回退用户手动补
```

PP-StructureV3 类方案是这条路由的"重炮位"（全版面模型），本项目在"一人团队第一周"的约束下先用几何层解决 80% 主流输入（双栏+扫描件路由），重炮位留了标准接口（OcrBackend）。
