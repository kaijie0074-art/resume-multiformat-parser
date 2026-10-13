"""Q1：work desc 转写噪声分解（15 例失配从哪来，归一化能吃掉几个点）。

方法：10 份图片型语料 @150dpi / glm-4v-flash 逐字转写（缓存），
按公司名对齐 pred/gt work 三元组，对 desc 做层次化差异分类：
exact / ws_only / punct_ws_only / digit_err / cjk_wording / mixed / lost。
另记录公司名/日期是否转写正确（结构性失配）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.research import metrics
from evals.research.vlm_probe import EVID, render_page, transcribe
from evals.run_eval import _norm

MODEL = "glm-4v-flash"
DPI = 150


def main() -> None:
    corpus = Path(__file__).resolve().parents[2] / "evals" / "corpus"
    stems = sorted(f.stem for f in corpus.glob("scanned-*.pdf"))
    rows = []
    for stem in stems:
        gt = metrics.load_gt(stem)
        text = transcribe(render_page(corpus / f"{stem}.pdf", DPI),
                          model=MODEL, stem=stem, dpi=DPI, tag="q1")
        from resume_parser import fields as fields_mod
        f = fields_mod.extract_fields(text)
        pred_by_company = {}
        for w in f.work_experiences:
            pred_by_company[_norm(w.company)] = w
        # 公司名带内部空格时 ORG_RE 可能失配 → 也记录原始转写中的行
        for tw in gt["_works"]:
            key = _norm(tw["company"])
            pw = pred_by_company.get(key)
            rec = {
                "stem": stem,
                "company": tw["company"],
                "company_found": pw is not None,
                "date_ok": bool(pw and _norm(pw.date_range) == _norm(tw["date"])),
                "desc_diff": metrics.classify_desc_diff(pw.description if pw else None, tw["desc"]),
            }
            rows.append(rec)
        # 转写原文落盘（证据）
        (EVID / "q1_transcripts").mkdir(parents=True, exist_ok=True)
        (EVID / "q1_transcripts" / f"{stem}.txt").write_text(text, encoding="utf-8")

    # 汇总
    cls_count: dict[str, int] = {}
    for r in rows:
        cls_count[r["desc_diff"]["cls"]] = cls_count.get(r["desc_diff"]["cls"], 0) + 1
    company_missed = [r["company"] for r in rows if not r["company_found"]]
    date_missed = sum(1 for r in rows if r["company_found"] and not r["date_ok"])
    summary = {
        "model": MODEL, "dpi": DPI, "n_works": len(rows),
        "desc_class_counts": cls_count,
        "company_not_matched": company_missed,
        "company_matched_but_date_wrong": date_missed,
        "nonexact": [r for r in rows if r["desc_diff"]["cls"] != "exact"],
    }
    out = EVID / "q1_noise_breakdown.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("model", "dpi", "n_works", "desc_class_counts",
                                              "company_not_matched",
                                              "company_matched_but_date_wrong")},
                     ensure_ascii=False, indent=1))
    for r in summary["nonexact"]:
        d = r["desc_diff"]
        print(f"[{d['cls']:>14}] {r['stem']} {r['company'][:6]}… "
              f"true={d.get('true')!r} pred={d.get('pred')!r}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
