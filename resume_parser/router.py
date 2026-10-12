"""路由：按输入类型与文本层状态决策抽取路径。

决策树（docs/design.md）：
    .docx → docx 路径
    .pdf → 文本层试抽（字符 < 40）→ 图片型 → OCR 后端（未配置则显式失败）
         → 有文本层 → 版面检测（双栏重排 / 单栏直接）
"""

from __future__ import annotations

from dataclasses import dataclass

from . import text_layer


@dataclass
class RouteDecision:
    kind: str            # pdf / docx
    text_layer: bool     # pdf 是否有可用文本层
    layout: str          # single / multi / n.a.
    reason: str          # 可解释路由原因


def route_pdf(pdf_bytes: bytes) -> RouteDecision:
    linear = text_layer.linear_text(pdf_bytes)
    n = len(linear.strip())
    if n < text_layer.TEXT_LAYER_MIN_CHARS:
        return RouteDecision(
            kind="pdf", text_layer=False, layout="n.a.",
            reason=f"文本层字符数 {n} < {text_layer.TEXT_LAYER_MIN_CHARS}，判定图片型/扫描件 → OCR 路径",
        )
    from . import layout as layout_mod

    import fitz

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        first = doc[0]
        words = [(w[0], w[1], w[2], w[3], w[4]) for w in first.get_text("words")]
        multi = layout_mod.detect_column_split(words, first.rect.width, first.rect.height) is not None
    return RouteDecision(
        kind="pdf", text_layer=True, layout="multi" if multi else "single",
        reason=("检测到双栏分界 → 版面重排" if multi else "单栏 → 直接行聚类"),
    )


def route(filename: str, pdf_bytes: bytes | None = None) -> RouteDecision:
    if filename.lower().endswith(".docx"):
        return RouteDecision(kind="docx", text_layer=True, layout="n.a.", reason="docx 结构化抽取（段落+表格）")
    if filename.lower().endswith(".pdf"):
        if pdf_bytes is None:
            raise ValueError("pdf 路由需要 pdf_bytes")
        return route_pdf(pdf_bytes)
    raise ValueError(f"不支持的输入类型: {filename}。当前支持 .pdf/.docx（.doc 老格式见 docs/design.md 拒绝理由）")
