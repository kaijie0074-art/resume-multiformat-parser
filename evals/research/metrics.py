"""研究指标：CER / 字段级 F1（基于转写文本）/ work-desc 噪声分类。

复用 evals/run_eval.py 的评分口径（_norm/_pred_triples/_true_triples），
保证研究数字与正式评估同一把尺子。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.run_eval import _norm, _norm_set, _pred_triples, _true_triples  # noqa: E402
from resume_parser import fields as fields_mod  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GT_DIR = ROOT / "evals" / "ground_truth"


# ---------------- 基础距离 ----------------

def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(pred: str, truth: str) -> float:
    """字符错误率（先做与评分口径一致的去空白归一，去掉行序无关的噪声）。"""
    p = "".join(_norm(pred).split())
    t = "".join(_norm(truth).split())
    if not t:
        return 0.0 if not p else 1.0
    return levenshtein(p, t) / len(t)


# ---------------- 字段级 F1（转写文本 → 抽取 → 评分） ----------------

class _Shim:
    """run_eval._pred_triples 只读 result.fields。"""
    def __init__(self, fields):
        self.fields = fields


def fields_f1(text: str, gt: dict, *, norm_set=_norm_set) -> tuple[float, dict]:
    """转写文本 → extract_fields → 与 run_eval 同口径 micro-F1。

    返回 (f1, error_modes)。
    """
    f = fields_mod.extract_fields(text)
    p_scalar, p_works, p_edus, p_certs = _pred_triples(_Shim(f))
    t_scalar, t_works, t_edus, t_certs = _true_triples(gt)
    p_scalar = {k: _norm(v) for k, v in p_scalar.items()}
    t_scalar = {k: _norm(v) for k, v in t_scalar.items()}
    p_works, p_edus, p_certs = norm_set(p_works), norm_set(p_edus), norm_set(p_certs)
    t_works, t_edus, t_certs = norm_set(t_works), norm_set(t_edus), norm_set(t_certs)

    tp = fp = fn = 0
    modes: dict[str, int] = {}
    for k, tv in t_scalar.items():
        if p_scalar.get(k) == tv:
            tp += 1
        else:
            fn += 1
            modes[k] = modes.get(k, 0) + 1
    for pv in p_scalar.values():
        if pv and pv not in t_scalar.values():
            fp += 1
            modes["scalar_extra"] = modes.get("scalar_extra", 0) + 1
    for name, ps, ts in (
        ("work", p_works, t_works),
        ("education", p_edus, t_edus),
        ("certificates", p_certs, t_certs),
    ):
        for tv in ts:
            if tv in ps:
                tp += 1
            else:
                fn += 1
                modes[name] = modes.get(name, 0) + 1
        for pv in ps - ts:
            fp += 1
            modes[f"{name}_fp"] = modes.get(f"{name}_fp", 0) + 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return f1, modes


def load_gt(stem: str) -> dict:
    return json.loads((GT_DIR / f"{stem}.json").read_text(encoding="utf-8"))


# ---------------- 图片型语料 GT 页面文本重建（CER 参照） ----------------

def gt_page_text(gt: dict) -> str:
    """按 gen_scanned 的绘制顺序重建整页文本（转写 CER 的参照）。"""
    lines = [gt["name"], f"电话 {gt['phone']}  邮箱 {gt['email']}", "教育经历",
             f"{gt['schools'][0]} {gt['degrees'][0]} {gt['date_ranges_edu']}", "实习经历"]
    for w in gt["_works"]:
        lines.append(f"{w['company']} 实习生 {w['date']}")
        lines.append(w["desc"])
    lines.append("技能证书 " + "、".join(gt["certificates"]))
    return "\n".join(lines)


# ---------------- work-desc 噪声层次分类 ----------------

_PUNCT = set("，。、：；！？,.:;!?()（）[]【】·-—~…\"'“”‘’|=+/\\*#@&%$^_<>`")


def _strip_ws(s: str) -> str:
    return "".join(s.split())


def _strip_punct_ws(s: str) -> str:
    return _strip_ws("".join(ch for ch in s if ch not in _PUNCT))


def classify_desc_diff(pred: str | None, truth: str | None) -> dict:
    """对单个 work desc 的 (预测, 真值) 做层次化差异分类。

    分类从轻到重：exact > ws_only > punct_ws_only > digit_err > cjk_wording > mixed / lost。
    """
    if pred is None:
        return {"cls": "lost", "dist": None, "true": truth}
    p, t = _norm(pred), _norm(truth or "")
    d = levenshtein(_strip_ws(p), _strip_ws(t))
    out = {"cls": "exact", "dist": d, "true": truth, "pred": pred}
    if p == t:
        return out
    if _strip_ws(p) == _strip_ws(t):
        out["cls"] = "ws_only"
        return out
    if _strip_punct_ws(p) == _strip_punct_ws(t):
        out["cls"] = "punct_ws_only"
        return out
    digits_p = "".join(ch for ch in _strip_punct_ws(p) if ch.isdigit())
    digits_t = "".join(ch for ch in _strip_punct_ws(t) if ch.isdigit())
    cjk_p = "".join(ch for ch in _strip_punct_ws(p) if "\u4e00" <= ch <= "\u9fa5")
    cjk_t = "".join(ch for ch in _strip_punct_ws(t) if "\u4e00" <= ch <= "\u9fa5")
    digit_bad = digits_p != digits_t
    cjk_bad = cjk_p != cjk_t
    if digit_bad and not cjk_bad:
        out["cls"] = "digit_err"
    elif cjk_bad and not digit_bad:
        out["cls"] = "cjk_wording"
        out["cjk_dist"] = levenshtein(cjk_p, cjk_t)
    else:
        out["cls"] = "mixed"
    return out
