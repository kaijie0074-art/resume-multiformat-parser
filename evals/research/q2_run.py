"""Q2 执行：难版面语料 → VLM 转写 → 字段 F1 + 失败模式分析。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.research import metrics
from evals.research.vlm_probe import EVID, render_page, transcribe

MODEL = "glm-4v-flash"
DPI = 150
CORPUS = EVID / "corpus-hard"
GT_HARD = EVID / "gt-hard"


def main() -> None:
    results = {}
    for pdf in sorted(CORPUS.glob("*.pdf")):
        stem = pdf.stem
        gt = json.loads((GT_HARD / f"{stem}.json").read_text(encoding="utf-8"))
        text = transcribe(render_page(pdf, DPI), model=MODEL, stem=stem, dpi=DPI, tag="q2")
        (EVID / "q2_transcripts").mkdir(exist_ok=True)
        (EVID / "q2_transcripts" / f"{stem}.txt").write_text(text, encoding="utf-8")
        f1, modes = metrics.fields_f1(text, gt)
        cer = metrics.cer(text, metrics.gt_page_text(gt))
        results[stem] = {"f1": round(f1, 3), "cer": round(cer, 4), "modes": modes}
        print(f"{stem}: F1={f1:.3f} CER={cer:.4f} modes={modes}")
    (EVID / "q2_hard_layouts.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {EVID / 'q2_hard_layouts.json'}")


if __name__ == "__main__":
    main()
