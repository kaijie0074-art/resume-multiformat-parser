"""Q2：更难版面语料（三栏 / 表格密集 / 图标标签）——版面复杂度上限探测。

生成 6 份图片型 PDF（无文本层）+ 真值（复用 scanned 语料 profile，绘制顺序不同）：
- threecol-0X：三栏布局（左联系/中教育证书/右实习）
- table-0X：边框表格密集版面（教育表 + 经历表）
- icons-0X：图标替代文字标签（图标化联系方式 + 图标化段头）

输出 evidence/research-20261014/corpus-hard/ 与 gt-hard/。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.generate_corpus import _load_cjk_font, _register_cn_font
from evals.research.metrics import GT_DIR

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

EVID = Path(__file__).resolve().parents[2] / "evidence" / "research-20261014"
OUT = EVID / "corpus-hard"
GT_OUT = EVID / "gt-hard"

PROFILE_MAP = {  # hard 语料 ← 原语料 profile（真值文本一致，仅版面不同）
    "threecol-01": "scanned-01", "threecol-02": "scanned-02",
    "table-01": "scanned-03", "table-02": "scanned-04",
    "icons-01": "scanned-05", "icons-02": "scanned-06",
}


def _profile(gt: dict) -> dict:
    return gt


def gen_threecol(path: Path, p: dict) -> None:
    """三栏：左（姓名+联系）/ 中（教育+证书）/ 右（实习经历）。"""
    _register_cn_font()
    img = Image.new("RGB", (1190, 1684), "white")
    d = ImageDraw.Draw(img)
    cjk = _load_cjk_font()
    font_big, font, font_small = cjk(30), cjk(20), cjk(18)
    # 左栏
    d.text((40, 60), p["name"], fill="black", font=cjk(34))
    y = 130
    d.text((40, y), "联系方式", fill="black", font=font_big); y += 44
    d.text((40, y), p["phone"], fill="black", font=font); y += 34
    d.text((40, y), p["email"], fill="black", font=font)
    # 中栏
    y = 60
    d.text((420, y), "教育经历", fill="black", font=font_big); y += 44
    d.text((420, y), p["schools"][0], fill="black", font=font); y += 34
    d.text((420, y), p["degrees"][0], fill="black", font=font); y += 34
    d.text((420, y), p["date_ranges_edu"], fill="black", font=font); y += 60
    d.text((420, y), "技能证书", fill="black", font=font_big); y += 44
    for c in p["certificates"]:
        d.text((420, y), c, fill="black", font=font_small); y += 32
    # 右栏
    y = 60
    d.text((820, y), "实习经历", fill="black", font=font_big); y += 44
    for w in p["_works"]:
        d.text((820, y), w["company"], fill="black", font=font); y += 32
        d.text((820, y), w["date"], fill="black", font=font_small); y += 30
        d.text((820, y), w["desc"], fill="black", font=font_small); y += 46
    _save(img, path)


def gen_table(path: Path, p: dict) -> None:
    """表格密集：教育表（3 列）+ 经历表（3 列，职责在格内）。"""
    _register_cn_font()
    img = Image.new("RGB", (1190, 1684), "white")
    d = ImageDraw.Draw(img)
    cjk = _load_cjk_font()
    font_big, font = cjk(30), cjk(20)
    d.text((50, 50), p["name"], fill="black", font=cjk(36))
    d.text((50, 110), f"{p['phone']}  {p['email']}", fill="black", font=font)

    def table(x0, y0, widths, rows, row_h=44):
        x1 = x0 + sum(widths)
        y1 = y0 + row_h * len(rows)
        d.rectangle([x0, y0, x1, y1], outline="black", width=2)
        cx = x0
        for w in widths[:-1]:
            cx += w
            d.line([cx, y0, cx, y1], fill="black", width=2)
        for i in range(1, len(rows)):
            yy = y0 + row_h * i
            d.line([x0, yy, x1, yy], fill="black", width=2)
        for r, row in enumerate(rows):
            cx = x0 + 8
            for cell, w in zip(row, widths):
                d.text((cx, y0 + row_h * r + 10), cell, fill="black", font=font)
                cx += w

    d.text((50, 170), "教育经历", fill="black", font=font_big)
    table(50, 220, [300, 200, 300], [["学校", "学历", "时间"],
                                      [p["schools"][0], p["degrees"][0], p["date_ranges_edu"]]])
    d.text((50, 360), "实习经历", fill="black", font=font_big)
    rows = [["公司", "时间", "职责"]]
    for w in p["_works"]:
        rows.append([w["company"], w["date"], w["desc"]])
    table(50, 410, [330, 260, 480], rows)
    d.text((50, 410 + 44 * (len(rows) + 1) + 30), "技能证书 " + "、".join(p["certificates"]),
           fill="black", font=font)
    _save(img, path)


def _icon_phone(d, x, y):
    d.rounded_rectangle([x, y, x + 18, y + 30], radius=5, outline="black", width=2)
    d.line([x + 6, y + 26, x + 12, y + 26], fill="black", width=2)


def _icon_mail(d, x, y):
    d.rectangle([x, y + 4, x + 30, y + 26], outline="black", width=2)
    d.line([x, y + 4, x + 15, y + 16], fill="black", width=2)
    d.line([x + 30, y + 4, x + 15, y + 16], fill="black", width=2)


def _icon_cap(d, x, y):
    d.polygon([(x, y + 12), (x + 16, y), (x + 32, y + 12)], outline="black", width=2)


def _icon_case(d, x, y):
    d.rectangle([x, y + 8, x + 32, y + 30], outline="black", width=2)
    d.rectangle([x + 10, y, x + 22, y + 8], outline="black", width=2)


def gen_icons(path: Path, p: dict) -> None:
    """图标标签：联系方式与段头全部图标化（无"电话/邮箱/教育经历/实习经历"文字标签）。"""
    _register_cn_font()
    img = Image.new("RGB", (1190, 1684), "white")
    d = ImageDraw.Draw(img)
    cjk = _load_cjk_font()
    font_big, font = cjk(30), cjk(20)
    d.text((50, 50), p["name"], fill="black", font=cjk(36))
    _icon_phone(d, 50, 120)
    d.text((92, 116), p["phone"], fill="black", font=font)
    _icon_mail(d, 50, 170)
    d.text((92, 166), p["email"], fill="black", font=font)
    _icon_cap(d, 50, 240)
    d.text((96, 232), p["schools"][0] + " " + p["degrees"][0] + " " + p["date_ranges_edu"],
           fill="black", font=font)
    _icon_case(d, 50, 330)
    y = 376
    for w in p["_works"]:
        d.text((60, y), w["company"] + " " + w["date"], fill="black", font=font); y += 34
        d.text((60, y), w["desc"], fill="black", font=font); y += 44
    d.text((50, y + 20), "技能证书 " + "、".join(p["certificates"]), fill="black", font=font)
    _save(img, path)


def _save(img: Image.Image, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    c.drawImage(ImageReader(img), 0, 0, width=595, height=842)
    c.save()


GENS = {"threecol": gen_threecol, "table": gen_table, "icons": gen_icons}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT_OUT.mkdir(parents=True, exist_ok=True)
    for stem, src in PROFILE_MAP.items():
        gt = json.loads((GT_DIR / f"{src}.json").read_text(encoding="utf-8"))
        p = _profile(gt)
        GENS[stem.rsplit("-", 1)[0]](OUT / f"{stem}.pdf", p)
        shutil.copy(GT_DIR / f"{src}.json", GT_OUT / f"{stem}.json")
        print(f"{stem}.pdf ← {src} profile")
    print(f"语料 → {OUT}\n真值 → {GT_OUT}")


if __name__ == "__main__":
    main()
