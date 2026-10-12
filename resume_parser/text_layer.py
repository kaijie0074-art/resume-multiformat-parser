"""文本层判定与抽取（router 的探测基础）。"""

from __future__ import annotations

import fitz  # PyMuPDF

# 判空阈值依据（评审意见 #4）：中文简历正文最少也含姓名+联系方式+一段经历，
# 40 个字符以下的"文本层"只可能是水印/页脚残留，不能当作可解析文本层。
TEXT_LAYER_MIN_CHARS = 40


def linear_text(pdf_bytes: bytes) -> str:
    """基线抽取：按 PDF 内容流顺序线性拼接（无版面感知）。

    这正是 v0.1.0 的行为：双栏模板会左右交错，图片型返回空串。
    """
    out = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            out.append(page.get_text("text"))
    return "\n".join(out)


def has_text_layer(pdf_bytes: bytes, min_chars: int = TEXT_LAYER_MIN_CHARS) -> bool:
    """判定是否存在可用文本层（字符数 >= 阈值）。"""
    return len(linear_text(pdf_bytes).strip()) >= min_chars


def page_words(pdf_bytes: bytes):
    """结构化词坐标（版面重排用）：yield (page_index, [(x0,y0,x1,y1,word), ...])。"""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
            yield i, words
