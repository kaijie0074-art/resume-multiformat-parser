"""版面感知：双栏检测与阅读顺序重排。

方法源头：pdfplumber 社区对双栏分离的讨论（jsvine/pdfplumber#1247，按词 x 坐标
间隙找分界）与 PP-StructureV3 的"版面先于文字"思想（见 docs/open-source-references.md）。
本项目实现为轻量版：只在"词坐标"层做几何判断，不跑版面模型。

阈值常量单位与依据（评审意见 #1）：
- COLUMN_GAP_RATIO 0.06：栏间空带宽度占页宽比例。低于 6% 的空隙（词间距级别）
  不构成栏分界；设计模板的栏间距通常 >= 页宽的 8%。
- MIN_COLUMN_WORDS_RATIO 0.25：两侧词数各需占总词数的 25% 以上，
  防把"右对齐的日期列"误判成第二栏。
- HEADER_Y_RATIO 0.15：页顶 15% 区域视为页眉带，横跨分界线的词若落在
  页眉带内，豁免切分（评审意见 #2：通栏姓名/联系方式不该被切进某一栏）。
"""

from __future__ import annotations

COLUMN_GAP_RATIO = 0.06
MIN_COLUMN_WORDS_RATIO = 0.25
HEADER_Y_RATIO = 0.15
LINE_TOLERANCE = 3.0  # 行聚类 y 容差（pt），同一视觉行的词 y 差小于此值


def detect_column_split(words, page_width: float, page_height: float):
    """在页面中部寻找竖向空带作为栏分界线。

    Returns:
        (split_x, header_words, left_words, right_words) 或 None（单栏）。
    """
    if not words or page_width <= 0:
        return None
    left = [w for w in words if w[2] <= page_width * 0.5]
    right = [w for w in words if w[0] >= page_width * 0.5]
    total = len(words)
    # 两侧词量门槛：防止"主栏+页边注"被当双栏
    if len(left) < total * MIN_COLUMN_WORDS_RATIO or len(right) < total * MIN_COLUMN_WORDS_RATIO:
        return None

    gap_min, gap_max = page_width * 0.30, page_width * 0.70
    split_x = None
    # 候选分界：从左栏最大 x1 到右栏最小 x0 的空带
    left_edge = max((w[2] for w in left), default=0)
    right_edge = min((w[0] for w in right), default=page_width)
    if gap_min <= (left_edge + right_edge) / 2 <= gap_max and right_edge - left_edge >= page_width * COLUMN_GAP_RATIO:
        split_x = (left_edge + right_edge) / 2

    if split_x is None:
        return None

    # 分流：横跨分界线的词 → 页眉带内豁免为通栏，否则并入较近一侧
    header_y = page_height * HEADER_Y_RATIO
    header_words, l, r = [], [], []
    for w in words:
        crosses = w[0] < split_x < w[2]
        if crosses:
            if w[1] < header_y:
                header_words.append(w)  # 页眉通栏（姓名/联系方式），不切分
            elif w[2] - split_x >= split_x - w[0]:
                r.append(w)
            else:
                l.append(w)
        elif w[2] <= split_x:
            l.append(w)
        else:
            r.append(w)
    return split_x, header_words, l, r


def _words_to_lines(words) -> list[str]:
    """词 → 视觉行：按 y 容差聚类后行内按 x 排序。"""
    if not words:
        return []
    lines: list[tuple[float, list]] = []
    for w in sorted(words, key=lambda t: (t[1], t[0])):
        placed = False
        for ly, bucket in lines:
            if abs(w[1] - ly) <= LINE_TOLERANCE:
                bucket.append(w)
                placed = True
                break
        if not placed:
            lines.append((w[1], [w]))
    out = []
    for _, bucket in sorted(lines, key=lambda t: t[0]):
        out.append(" ".join(w[4] for w in sorted(bucket, key=lambda t: t[0])))
    return out


def reorder_page(words, page_width: float, page_height: float) -> str:
    """单页阅读顺序重排：单栏直接行聚类；双栏先左后右；页眉通栏置顶。"""
    split = detect_column_split(words, page_width, page_height)
    if split is None:
        return "\n".join(_words_to_lines(words))
    _, header_words, left_words, right_words = split
    parts = []
    header_lines = _words_to_lines(header_words)
    if header_lines:
        parts.append("\n".join(header_lines))
    parts.append("\n".join(_words_to_lines(left_words)))
    parts.append("\n".join(_words_to_lines(right_words)))
    return "\n".join(p for p in parts if p.strip())


def layout_text(pdf_bytes: bytes) -> str:
    """全文重排入口：逐页检测分栏并按阅读顺序拼接。"""
    import fitz

    out = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
            out.append(reorder_page(words, page.rect.width, page.rect.height))
    return "\n".join(out)
