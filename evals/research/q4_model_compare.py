"""Q4：glm-4v-flash vs glm-5.3-flash 多模态对比（同图同 prompt）。

指标：字段 F1 / CER / 延迟 / 豆腐块。glm-5.3-flash 为 reasoning 输出（慢，超时 300s）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.research import metrics
from evals.research.vlm_probe import EVID, call_log_stats, render_page, transcribe

DPIS = [150]
STEMS = ["scanned-01", "scanned-05", "scanned-08", "scanned-09", "scanned-10"]
MODELS = ["glm-4v-flash", "glm-5.3-flash"]


def main() -> None:
    corpus = Path(__file__).resolve().parents[2] / "evals" / "corpus"
    results = {}
    for model in MODELS:
        for stem in STEMS:
            gt = metrics.load_gt(stem)
            text = transcribe(render_page(corpus / f"{stem}.pdf", 150),
                              model=model, stem=stem, dpi=150, tag="q4", timeout=300)
            f1, modes = metrics.fields_f1(text, gt)
            cer = metrics.cer(text, metrics.gt_page_text(gt))
            tofu = text.count("\u25a1") + text.count("\ufffd")
            results[f"{stem}|{model}"] = {"f1": round(f1, 3), "cer": round(cer, 4),
                                          "tofu": tofu, "modes": modes}
            print(f"{stem}|{model}: F1={f1:.3f} CER={cer:.4f} tofu={tofu} modes={modes}")
    # 延迟从调用日志取
    lat: dict[str, list] = {}
    if (EVID / "calls.jsonl").exists():
        for ln in (EVID / "calls.jsonl").read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("tag") == "q4":
                lat.setdefault(r["model"], []).append(r["latency_s"])
    agg = {}
    for model in MODELS:
        vals = [results[f"{s}|{model}"] for s in STEMS]
        agg[model] = {"mean_f1": round(sum(v["f1"] for v in vals) / len(vals), 3),
                      "mean_cer": round(sum(v["cer"] for v in vals) / len(vals), 4),
                      "mean_latency_s": round(sum(lat.get(model, [0])) / max(len(lat.get(model, [1])), 1), 1)}
    results["_agg"] = agg
    out = EVID / "q4_model_compare.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(agg, ensure_ascii=False, indent=1))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
