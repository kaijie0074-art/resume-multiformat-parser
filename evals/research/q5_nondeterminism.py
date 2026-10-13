"""Q5：端点非确定性定量——同图同参数重复调用，转写稳定到什么程度？

scanned-10（含 姝/妹 形近字）@150dpi 重复 6 次（1 次复用 q3 缓存），度量：
- 转写两两是否完全一致（exact-match 率）
- 字段 F1 / CER 的分布（同一输入、同一模型、同一 prompt）
- 姝/妹 字的翻转率
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.research import metrics
from evals.research.vlm_probe import EVID, render_page, transcribe

MODEL = "glm-4v-flash"
STEM = "scanned-10"
N = 6


def main() -> None:
    corpus = Path(__file__).resolve().parents[2] / "evals" / "corpus"
    gt = metrics.load_gt(STEM)
    texts = []
    for rep in range(1, N + 1):
        text = transcribe(render_page(corpus / f"{STEM}.pdf", 150),
                          model=MODEL, stem=STEM, dpi=150, tag=f"q5-rep{rep}")
        texts.append(text)
        f1, modes = metrics.fields_f1(text, gt)
        cer = metrics.cer(text, metrics.gt_page_text(gt))
        print(f"rep{rep}: F1={f1:.3f} CER={cer:.4f} name={'冯静姝' if '冯静姝' in text else ('冯静妹' if '冯静妹' in text else '?')} modes={modes}")

    pairwise = sum(1 for i in range(N) for j in range(i + 1, N) if texts[i] == texts[j])
    total_pairs = N * (N - 1) // 2
    summary = {
        "model": MODEL, "stem": STEM, "dpi": 150, "n_reps": N,
        "exact_match_pairs": f"{pairwise}/{total_pairs}",
        "unique_transcripts": len(set(texts)),
        "name_outcomes": ["姝" if "冯静姝" in t else ("妹" if "冯静妹" in t else "?") for t in texts],
        "per_rep": [{"f1": round(metrics.fields_f1(t, gt)[0], 3),
                     "cer": round(metrics.cer(t, metrics.gt_page_text(gt)), 4)} for t in texts],
    }
    out = EVID / "q5_nondeterminism.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
