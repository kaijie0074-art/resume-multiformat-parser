"""Q3：DPI-质量曲线（120→240）——渲染分辨率对转写质量/字段 F1 的边际收益。

5 份图片型语料（含 scanned-10 的"姝/妹"形近字案例）× 5 档 DPI。
指标：CER（vs GT 页面文本重建）+ 字段 F1（run_eval 同口径）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.research import metrics
from evals.research.vlm_probe import EVID, render_page, transcribe

MODEL = "glm-4v-flash"
DPIS = [120, 150, 180, 220, 240]
STEMS = ["scanned-01", "scanned-05", "scanned-08", "scanned-09", "scanned-10"]


def main() -> None:
    corpus = Path(__file__).resolve().parents[2] / "evals" / "corpus"
    results = {}
    for dpi in DPIS:
        for stem in STEMS:
            gt = metrics.load_gt(stem)
            text = transcribe(render_page(corpus / f"{stem}.pdf", dpi),
                              model=MODEL, stem=stem, dpi=dpi, tag="q3")
            f1, modes = metrics.fields_f1(text, gt)
            cer = metrics.cer(text, metrics.gt_page_text(gt))
            results[f"{stem}@{dpi}"] = {"f1": round(f1, 3), "cer": round(cer, 4), "modes": modes}
            print(f"{stem}@{dpi}: F1={f1:.3f} CER={cer:.4f} modes={modes}")
    # 按 DPI 聚合
    agg = {}
    for dpi in DPIS:
        vals = [results[f"{s}@{dpi}"] for s in STEMS]
        agg[dpi] = {"mean_f1": round(sum(v["f1"] for v in vals) / len(vals), 3),
                    "mean_cer": round(sum(v["cer"] for v in vals) / len(vals), 4)}
    results["_agg_by_dpi"] = agg
    out = EVID / "q3_dpi_curve.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(agg, ensure_ascii=False, indent=1))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
