"""端到端与分层测试。覆盖场景说明见 docs/test-coverage.md。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from resume_parser.ocr_backend import OcrNotConfiguredError, pick_configured_backend  # noqa: E402
from resume_parser.service import parse, parse_baseline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "evals" / "corpus"
REAL_OCR = pick_configured_backend()
requires_ocr = pytest.mark.skipif(
    REAL_OCR is None, reason="需要真实 OCR 后端（RESUME_PARSER_PADDLE_URL 或 RESUME_PARSER_VLM_*）"
)


# ---------- 路由 ----------

def test_路由_单栏文本PDF():
    r = parse(CORPUS / "single-01.pdf")
    assert r.route["kind"] == "pdf" and r.route["text_layer"] == "true" and r.route["layout"] == "single"


def test_路由_双栏文本PDF():
    r = parse(CORPUS / "two-col-01.pdf")
    assert r.route["layout"] == "multi", r.route["reason"]


def test_路由_图片型PDF判空文本层():
    from resume_parser import router

    d = router.route("scanned-01.pdf", pdf_bytes=(CORPUS / "scanned-01.pdf").read_bytes())
    assert d.text_layer is False and d.kind == "pdf"


def test_路由_不支持类型显式拒绝():
    from resume_parser import router
    with pytest.raises(ValueError, match="doc"):
        router.route("resume.doc")


# ---------- 双栏重排：职责不串公司（RPI-001 核心断言） ----------

def test_双栏_公司A职责不串到公司B():
    r = parse(CORPUS / "two-col-01.pdf")
    gt = json.loads((ROOT / "evals" / "ground_truth" / "two-col-01.json").read_text(encoding="utf-8"))
    by_company = {w.company: w.description for w in r.fields.work_experiences}
    for true_w in gt["_works"]:
        got = by_company.get(true_w["company"])
        assert got == true_w["desc"], f"{true_w['company']} 职责串线: got={got!r} want={true_w['desc']!r}"


def test_双栏_基线线性抽取职责错挂_复现缺陷():
    """v0.1.0 基线在交错文本上 desc 错挂——这条测试固化缺陷的存在（修复前必挂）。"""
    r = parse_baseline(CORPUS / "two-col-01.pdf")
    gt = json.loads((ROOT / "evals" / "ground_truth" / "two-col-01.json").read_text(encoding="utf-8"))
    by_company = {w.company: w.description for w in r.fields.work_experiences}
    wrong = [w["company"] for w in gt["_works"] if by_company.get(w["company"]) != w["desc"]]
    assert wrong, "基线居然全对——交错缺陷未复现，评估口径可能失真"


def test_双栏_页眉通栏不被切分_评审2():
    """两层断言：真实语料姓名完整保留在重排文本顶部；合成词横跨分界且在页眉带时归通栏。"""
    from resume_parser import layout, layout as layout_mod

    # 真实语料：姓名完整出现在版面重排文本的前几行（不被吞、不重复）
    text = layout.layout_text((CORPUS / "two-col-01.pdf").read_bytes())
    assert "王思远" in "\n".join(text.splitlines()[:3]), text.splitlines()[:3]

    # 合成用例：横跨分界线的词落在页眉带 → 豁免切分、归入通栏
    words = [
        (40, 20, 560, 40, "通栏姓名"),      # y=20 < 页眉带(0.15*800=120) 且横跨 split≈300
        (50, 200, 280, 220, "左栏词一"),
        (320, 200, 560, 220, "右栏词一"),
        (50, 240, 280, 260, "左栏词二"),
        (320, 240, 560, 260, "右栏词二"),
    ]
    split = layout_mod.detect_column_split(words, 600, 800)
    assert split is not None
    _, header_words, left, right = split
    assert "通栏姓名" in " ".join(w[4] for w in header_words)
    assert len(left) == 2 and len(right) == 2

# ---------- 图片型：真实 OCR 与显式失败 ----------

@requires_ocr
def test_图片型_真实OCR抽出全部字段():
    r = parse(CORPUS / "scanned-01.pdf", ocr=REAL_OCR)
    assert r.source == "ocr" and r.route["text_layer"] == "false"
    gt = json.loads((ROOT / "evals" / "ground_truth" / "scanned-01.json").read_text(encoding="utf-8"))
    assert r.fields.name == gt["name"]
    assert r.fields.phone == gt["phone"]
    assert r.fields.email == gt["email"]
    assert [e.school for e in r.fields.educations] == gt["schools"]


def test_图片型_无OCR后端显式失败不编造():
    with pytest.raises(OcrNotConfiguredError, match="拒绝静默"):
        parse(CORPUS / "scanned-01.pdf", ocr=None)


def test_图片型_基线空文本全空_复现缺陷():
    r = parse_baseline(CORPUS / "scanned-01.pdf")
    assert r.fields.name is None and not r.fields.work_experiences, "基线应抽不出任何字段（空文本层）"


# ---------- docx ----------

def test_docx_合并单元格不重复():
    r = parse(CORPUS / "docx-01.docx")
    schools = [e.school for e in r.fields.educations]
    assert schools == ["沪江大学"], "合并单元格的学校应只出现一次"


def test_docx_表格与段落字段齐():
    r = parse(CORPUS / "docx-01.docx")
    assert r.fields.name == "王思远"
    assert len(r.fields.work_experiences) >= 1


# ---------- 缺失与置信度 ----------

def test_缺失字段needs_manual与告警():
    from resume_parser import confidence as conf_mod
    from resume_parser.fields import Fields

    c = conf_mod.assess(Fields(), source="layout")
    assert c.needs_manual
    assert any("姓名" in w for w in c.warnings)


def test_置信度_来源层与启发式折扣():
    from resume_parser import confidence as conf_mod
    from resume_parser.fields import Education, Fields, WorkExperience

    full = Fields(name="张三", phone="13800000000", email="a@b.c",
                  educations=[Education(school="某大学")],
                  work_experiences=[WorkExperience(company="某公司")])
    for source, expect in (("text", 1.0), ("layout", 0.9), ("ocr", 0.85), ("docx", 0.95)):
        c = conf_mod.assess(full, source=source)
        assert abs(c.values["phone"] - expect) < 1e-9
        assert c.values["name"] == pytest.approx(expect * 0.8)  # 启发式字段打折


def test_阈值常量可追溯_评审1_4_6():
    from resume_parser import layout as layout_mod
    from resume_parser import text_layer

    assert layout_mod.COLUMN_GAP_RATIO == 0.06  # 注释含单位与依据
    assert layout_mod.HEADER_Y_RATIO == 0.15
    assert text_layer.TEXT_LAYER_MIN_CHARS == 40  # 依据注释见 text_layer.py
    from resume_parser import confidence as conf_mod
    assert conf_mod.SOURCE_CONFIDENCE["ocr"] == 0.85  # 依据注释见 confidence.py


# ---------- 分组 F1 阈值（回归闸门） ----------

def test_全语料分组F1达标():
    sys.path.insert(0, str(ROOT / "evals"))
    from run_eval import score_group

    gt_dir = ROOT / "evals" / "ground_truth"
    thresholds = {"single": 0.95, "two-col": 0.95, "scanned": 0.85, "docx": 0.95}
    stems = [p.stem for p in CORPUS.iterdir()]
    for prefix, floor in thresholds.items():
        group = [s for s in stems if s.startswith(prefix)]
        if prefix == "scanned" and REAL_OCR is None:
            continue  # 真实 OCR 后端未配置，图片型组不参与离线阈值回归
        f1, p, r, _ = score_group(group, CORPUS, gt_dir, REAL_OCR, "hardened")
        assert f1 >= floor, f"{prefix} F1={f1:.2f} < {floor}"


def test_基线在图片型上F1为零():
    sys.path.insert(0, str(ROOT / "evals"))
    from run_eval import score_group

    stems = [p.stem for p in CORPUS.iterdir() if p.stem.startswith("scanned")]
    f1, *_ = score_group(stems, CORPUS, ROOT / "evals" / "ground_truth", None, "baseline")
    assert f1 == 0.0, "图片型基线必须抽不出字段（空文本层静默失败是 RPI-002 根源）"
