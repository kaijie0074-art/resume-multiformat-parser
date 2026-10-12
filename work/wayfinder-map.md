# wayfinder-map：resume-multiformat-parser

| # | 里程碑 | 判据 | 完成 | 证据 |
|---|---|---|---|---|
| 1 | 基线复现 | 三类输入缺陷可量化 | ✅ 10-10 | 回归记录（0.78 / 0.00） |
| 2 | 开源调研 | 路由架构有上游依据 | ✅ 10-11 | open-source-references.md |
| 3 | 路由+重排+OCR 位 | 双栏/图片型路径全通 | ✅ 10-12 | test_parser 17 用例 |
| 4 | 评估器 | 分组 F1 + 错误模式 | ✅ 10-12 | evidence/eval-report.md |
| 5 | 评审迭代 | 6+1 意见落地 | ✅ 10-13 | docs/reviews/ |
| 6 | 验收合并 | 清单 9/9 过 | ✅ 10-13 | docs/acceptance.md |

## 过程缺陷台账

1. reportlab 默认字体无中文（语料文本层空）→ CID 注册
2. 双栏语料绘制太友好（基线也能对）→ 按视觉行序交错
3. 日期正则尾空格 → strip
4. OCR 劣化打断 ASCII → 仅汉字间
5. 评估不容错全半角 → NFKC 归一化

## 剩余风险（v1.1）

- 三栏/杂志版面（边界已声明）
- 真实 PaddleOCR 接入后的噪声分布校准
