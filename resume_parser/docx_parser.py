"""docx 抽取：段落 + 表格（含合并单元格展开），按文档流顺序。"""

from __future__ import annotations

import io

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def extract_docx(docx_bytes: bytes) -> str:
    """按文档流顺序输出段落与表格文本。

    合并单元格：python-docx 的 table.rows 遍历对合并单元格会重复返回同一 cell，
    这里按 (行,列) 去重后拼接，避免重复文本。
    """
    doc = Document(io.BytesIO(docx_bytes))
    parts: list[str] = []

    def iter_block_items(parent):
        from docx.oxml.ns import qn
        for child in parent.element.body.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                parts.append(text)
        else:  # Table
            seen = set()
            for row in block.rows:
                cells = []
                for cell in row.cells:
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    t = cell.text.strip().replace("\n", " ")
                    if t:
                        cells.append(t)
                if cells:
                    parts.append(" | ".join(cells))
    return "\n".join(parts)
