"""Q7：两个收尾探针。

(a) 上下文效应：孤立的"冯静姝"卡片（22px，无 妹 相邻）两模型是否仍错？
    ——区分"形近字相邻干扰"与"字级识别混淆"
(b) 工程解法探测：scanned-10 页顶条（姓名区）裁剪 + 2x 放大重转写，
    4v-flash 能否救回 姝？（若能 → 分区放大二次通过是可行工程对策；
    若不能 → 4v 档模型上限，需升档 5.3）
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.generate_corpus import _load_cjk_font
from evals.research.vlm_probe import EVID, render_page, transcribe

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
NAME_PROMPT = "逐字转写图片中的姓名文字，只输出汉字本身。"
STRIP_PROMPT = "逐字转写这页简历顶部区域的全部文字，保持阅读顺序，不要补全或纠正。"


def name_card() -> bytes:
    cjk = _load_cjk_font()
    img = Image.new("RGB", (400, 120), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 40), "冯静姝", fill="black", font=cjk(22))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def top_strip(stem: str, zoom: float = 2.0) -> bytes:
    png = render_page(ROOT / "evals" / "corpus" / f"{stem}.pdf", 150)
    img = Image.open(io.BytesIO(png))
    w, h = img.size
    strip = img.crop((0, 0, w, int(h * 0.12)))  # 顶部 12%：姓名+联系方式区
    strip = strip.resize((int(strip.width * zoom), int(strip.height * zoom)), Image.LANCZOS)
    buf = io.BytesIO()
    strip.save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    results = {}
    for model in ("glm-4v-flash", "glm-5.3-flash"):
        t = transcribe(name_card(), model=model, stem="namecard", dpi=0, tag="q7a",
                       prompt=NAME_PROMPT, timeout=300)
        results[f"namecard|{model}"] = t
        print(f"(a) 孤立姓名卡 {model}: {t!r}  姝正确={'姝' in t}")
    for model in ("glm-4v-flash", "glm-5.3-flash"):
        t = transcribe(top_strip("scanned-10"), model=model, stem="scanned-10", dpi=150,
                       tag="q7b-strip2x", prompt=STRIP_PROMPT, timeout=300)
        results[f"strip2x|{model}"] = t
        print(f"(b) 顶条2x放大 {model}: {t.splitlines()[:2]!r}  姝正确={'姝' in t}")
    (EVID / "q7_context_zoom.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {EVID / 'q7_context_zoom.json'}")


if __name__ == "__main__":
    main()
