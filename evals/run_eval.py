"""字段级 F1 评估器：对 35 份语料跑基线/加固两版，按输入类别分组出表。

口径（docs/design.md 评估节）：
- 标量字段（name/phone/email）：精确匹配
- 结构化字段：work=(company, date_range, description) 三元组、education=(school, degree, date_range)
  三元组、certificates 集合——三元组任一分量错即整条错（下游 LLM 结构化的真实形态）
- 报告含"错误模式分类"列（评审意见 #5）：哪个字段类别错最多
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resume_parser.ocr_backend import RecordedOcrBackend
from resume_parser.service import parse, parse_baseline

GROUPS = {"single": "单栏文本 PDF", "two-col": "双栏文本 PDF", "scanned": "图片型 PDF", "docx": "docx 表格"}


def _pred_triples(result):
    works = {(w.company, w.date_range, w.description) for w in result.fields.work_experiences}
    edus = {(e.school, e.degree, e.date_range) for e in result.fields.educations}
    certs = set(result.fields.certificates)
    scalars = {
        "name": result.fields.name,
        "phone": result.fields.phone,
        "email": result.fields.email,
    }
    return scalars, works, edus, certs


def _true_triples(gt: dict):
    works = set()
    # 真值 works：profile_text 里的 desc 全文（生成器唯一来源）
    gt_w = gt.get("_works") or []
    for w in gt_w:
        works.add((w["company"], w["date"], w["desc"]))
    edus = {(gt["schools"][0], gt["degrees"][0], gt["date_ranges_edu"])} if gt.get("date_ranges_edu") else set()
    certs = set(gt["certificates"])
    scalars = {"name": gt["name"], "phone": gt["phone"], "email": gt["email"]}
    return scalars, works, edus, certs

def _norm(v) -> str:
    """标点归一化：OCR 输出的全角/半角标点形态不可控，匹配口径必须容错。"""
    import unicodedata

    if v is None:
        return ""
    s = unicodedata.normalize("NFKC", str(v))
    return (s.replace("，", ",").replace("：", ":").replace("（", "(")
             .replace("）", ")").replace("、", ",").strip())


def _norm_tuple(t):
    return tuple(_norm(x) for x in t)


def _norm_set(s: set):
    return {_norm_tuple(t) if isinstance(t, tuple) else _norm(t) for t in s}


def score_group(stems: list[str], corpus: Path, gt_dir: Path, ocr: RecordedOcrBackend, mode: str):
    """返回 (micro-F1, 错误模式计数 dict, 每份明细)。"""
    tp = fp = fn = 0
    error_modes: dict[str, int] = {}
    details = []
    for stem in stems:
        ext = ".docx" if stem.startswith("docx") else ".pdf"
        path = corpus / f"{stem}{ext}"
        if mode == "baseline":
            r = parse_baseline(path)
        else:
            r = parse(path, ocr=ocr)
        gt = json.loads((gt_dir / f"{stem}.json").read_text(encoding="utf-8"))

        p_scalar, p_works, p_edus, p_certs = _pred_triples(r)
        t_scalar, t_works, t_edus, t_certs = _true_triples(gt)
        p_scalar = {k: _norm(v) for k, v in p_scalar.items()}
        t_scalar = {k: _norm(v) for k, v in t_scalar.items()}
        p_works, p_edus, p_certs = _norm_set(p_works), _norm_set(p_edus), _norm_set(p_certs)
        t_works, t_edus, t_certs = _norm_set(t_works), _norm_set(t_edus), _norm_set(t_certs)

        for k, tv in t_scalar.items():
            if p_scalar.get(k) == tv:
                tp += 1
            else:
                fn += 1
                error_modes[k] = error_modes.get(k, 0) + 1
        for pv in p_scalar.values():
            if pv and pv not in t_scalar.values():
                fp += 1
                error_modes["scalar_extra"] = error_modes.get("scalar_extra", 0) + 1

        for group_name, p_set, t_set in (
            ("work", p_works, t_works), ("education", p_edus, t_edus), ("certificates", p_certs, t_certs)
        ):
            for tv in t_set:
                if tv in p_set:
                    tp += 1
                else:
                    fn += 1
                    error_modes[group_name] = error_modes.get(group_name, 0) + 1
            for pv in p_set - t_set:
                fp += 1
                error_modes[f"{group_name}_fp"] = error_modes.get(f"{group_name}_fp", 0) + 1
        details.append((stem, tp))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return f1, precision, recall, error_modes


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    corpus = root / "evals" / "corpus"
    gt_dir = root / "evals" / "ground_truth"
    ocr = RecordedOcrBackend(root / "evals" / "ocr_fixtures")

    files = sorted(corpus.iterdir())
    stems = [f.stem for f in files]
    if len(stems) != 35:
        print(f"语料数量异常: {len(stems)} != 35，先跑 evals/generate_corpus.py")
        sys.exit(1)

    # ground truth 需要补充 _works 与 date_ranges_edu（生成器写入）
    lines = ["# 字段级 F1 评估报告（run_eval.py 自动生成）", ""]
    lines.append("| 输入类别 | 样本 | 基线 P | 基线 R | 基线 F1 | 加固 P | 加固 R | 加固 F1 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    summary = {}
    for prefix, label in GROUPS.items():
        group_stems = [s for s in stems if s.startswith(prefix)]
        bf1, bp, br, _ = score_group(group_stems, corpus, gt_dir, ocr, "baseline")
        hf1, hp, hr, hem = score_group(group_stems, corpus, gt_dir, ocr, "hardened")
        lines.append(f"| {label} | {len(group_stems)} | {bp:.2f} | {br:.2f} | {bf1:.2f} | {hp:.2f} | {hr:.2f} | {hf1:.2f} |")
        summary[prefix] = {"baseline_f1": round(bf1, 3), "hardened_f1": round(hf1, 3),
                           "hardened_error_modes": hem}
    lines.append("")
    lines.append("## 错误模式分类（加固版，评审意见 #5）")
    lines.append("")
    lines.append("| 类别 | 模式 | 计数 |")
    lines.append("|---|---|---|")
    for prefix, label in GROUPS.items():
        for mode, n in sorted(summary[prefix]["hardened_error_modes"].items()):
            lines.append(f"| {label} | {mode} | {n} |")

    report = "\n".join(lines) + "\n"
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "eval-report.md").write_text(report, encoding="utf-8")
    (evidence / "latest-run.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(report)
    print(f"已写入 {evidence}/eval-report.md 与 latest-run.json")


if __name__ == "__main__":
    main()
