"""总入口：parse(path) -> ParseResult。

用法：
    from resume_parser.service import parse
    result = parse("evals/corpus/two-col-01.pdf")
    result.fields.name, result.needs_manual, result.warnings
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import confidence as conf_mod
from . import docx_parser, fields as fields_mod, layout, router, text_layer
from .fields import Fields
from .ocr_backend import OcrBackend


@dataclass
class ParseResult:
    fields: Fields
    confidence: dict[str, float] = field(default_factory=dict)
    needs_manual: bool = False
    warnings: list[str] = field(default_factory=list)
    route: dict[str, str] = field(default_factory=dict)
    source: str = ""


def parse(path: str | Path, ocr: OcrBackend | None = None) -> ParseResult:
    path = Path(path)
    data = path.read_bytes()
    stem = path.stem
    decision = router.route(path.name, pdf_bytes=data if path.suffix.lower() == ".pdf" else None)

    if decision.kind == "docx":
        text = docx_parser.extract_docx(data)
        source = "docx"
    elif decision.text_layer:
        text = layout.layout_text(data)  # 版面感知重排（单栏=行聚类，双栏=先左后右）
        source = "layout"
    else:
        if ocr is None:
            from .ocr_backend import OcrNotConfiguredError

            raise OcrNotConfiguredError(
                "图片型 PDF 需要 OCR 后端（未配置时拒绝静默继续，防下游 LLM 编造）。"
                "演练环境传入 RecordedOcrBackend(eval/ocr_fixtures)；"
                "生产配置 RESUME_PARSER_PADDLE_URL 或 RESUME_PARSER_VLM_*。"
            )
        text = ocr.extract(data, stem=stem)
        source = "ocr"

    fields = fields_mod.extract_fields(text)
    c = conf_mod.assess(fields, source=source, route_reason=decision.reason)

    return ParseResult(
        fields=fields,
        confidence=c.values,
        needs_manual=c.needs_manual,
        warnings=c.warnings,
        route={"kind": decision.kind, "text_layer": str(decision.text_layer).lower(),
               "layout": decision.layout, "reason": decision.reason},
        source=source,
    )


def parse_baseline(path: str | Path) -> ParseResult:
    """基线（v0.1.0 行为）：线性抽取，无路由无重排无 OCR——用于对照复现。"""
    path = Path(path)
    data = path.read_bytes()
    if path.suffix.lower() == ".docx":
        text = docx_parser.extract_docx(data)
        source = "docx"
    else:
        text = text_layer.linear_text(data)  # 双栏交错 / 图片型空串，正是基线缺陷
        source = "text"
    fields = fields_mod.extract_fields(text, naive=True)
    c = conf_mod.assess(fields, source=source)
    return ParseResult(fields=fields, confidence=c.values, needs_manual=c.needs_manual,
                       warnings=c.warnings, route={"kind": "baseline"}, source=source)
