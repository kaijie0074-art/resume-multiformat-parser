"""Q6：形近字 × 字号能力曲线——小字号中文识别上限的受控实验。

生成含 20 组形近字对的卡片图（每行"基准字 形近字"逐字画），字号 12/16/20/24/28px，
整卡 150dpi 等效渲染（与生产路径同构：PNG 直接进 VLM）。
度量：每字号的字符正确率（2 模型对比），定位翻转阈值。

真值 = 绘制的字符串本身（绘制端确定，无 OCR 歧义）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.generate_corpus import _load_cjk_font
from evals.research import metrics
from evals.research.vlm_probe import EVID, transcribe

from PIL import Image, ImageDraw

# 20 组高频形近字对（简历语域常见 + 通用）
PAIRS = [
    "姝妹", "己已", "未末", "拔拨", "沐沭", "土士", "日曰", "干千",
    "企业", "使便", "体休", "加办", "历厉", "汇报", "名各", "折拆",
    "招聘", "技术", "职员", "管理",
]

PROMPT = (
    "逐字转写图中每一行的两个汉字，每行输出两个字符，行与行之间换行。"
    "不要加空格、标点或解释，只输出汉字本身。"
)


def render_card(font_px: int) -> bytes:
    import io

    cjk = _load_cjk_font()
    font = cjk(font_px)
    lh = font_px * 3
    img = Image.new("RGB", (6 * font_px + 80, lh * len(PAIRS) + 40), "white")
    d = ImageDraw.Draw(img)
    for i, pair in enumerate(PAIRS):
        y = 20 + i * lh
        d.text((40, y), pair[0], fill="black", font=font)
        d.text((40 + font_px * 3, y), pair[1], fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    results = {}
    for model in ("glm-4v-flash", "glm-5.3-flash"):
        for px in (12, 16, 20, 24, 28):
            png = render_card(px)
            text = transcribe(png, model=model, stem=f"pairs{px}", dpi=0, tag="q6",
                              prompt=PROMPT, timeout=300)
            truth = "\n".join(PAIRS)
            # 汉字级准确率（忽略空白/换行形态）
            pred_chars = [c for c in text if "\u4e00" <= c <= "\u9fa5"]
            true_chars = [c for c in truth if "\u4e00" <= c <= "\u9fa5"]
            n = len(true_chars)
            correct = sum(1 for i, c in enumerate(pred_chars[:n]) if c == true_chars[i])
            acc = correct / n if n else 0.0
            per_char = [f"{true_chars[i]}→{pred_chars[i] if i < len(pred_chars) else '∅'}"
                        for i in range(n) if i >= len(pred_chars) or pred_chars[i] != true_chars[i]]
            results[f"{model}@{px}"] = {"acc": round(acc, 3), "errors": per_char}
            print(f"{model}@{px}px: acc={acc:.3f} errors={per_char[:8]}{'…' if len(per_char) > 8 else ''}")
    out = EVID / "q6_confusable_chars.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
