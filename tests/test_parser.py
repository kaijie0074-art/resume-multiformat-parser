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


def test_评分归一化_空白与全角标点形态不敏感():
    """Q1 实验结论：VLM 转写在 CJK-数字边界丢空格（16/16 失配为纯空格差异），
    匹配口径必须忽略空白形态，否则把测量噪声当成模型错误。"""
    sys.path.insert(0, str(ROOT / "evals"))
    from run_eval import _norm

    assert _norm("参与订单系统开发，日均处理 3000 单") == _norm("参与订单系统开发,日均处理3000单")
    assert _norm("电话：138 0000 0000") == _norm("电话:13800000000")
    assert _norm("、") == _norm(",")
    assert _norm(None) == ""


def test_抽取_markdown表格行_职责与公司同行的兜底():
    """Q2 实验结论：VLM 对表格版面输出 markdown 行（| 公司 | 时间 | 职责 |），
    邻近行无 desc 时必须从当前行单元格兜底，否则三元组丢失。"""
    from resume_parser.fields import extract_fields

    text = (
        "实习经历\n"
        "| 公司 | 时间 | 职责 |\n"
        "|------|------|------|\n"
        "| 汀洲网络科技有限公司 | 2025.03-2025.08 | 维护200个用户社群，月均转化150单 |\n"
        "技能证书 计算机二级\n"
    )
    f = extract_fields(text)
    assert len(f.work_experiences) == 1
    w = f.work_experiences[0]
    assert w.company == "汀洲网络科技有限公司"
    assert w.date_range == "2025.03-2025.08"
    assert w.description == "维护200个用户社群，月均转化150单"


def test_抽取_三栏竖排教育块_日期窗口放宽到三行():
    """Q2 实验结论：三栏版面教育信息竖排三行（学校/学历/时间各一行），
    日期窗口 i+2 漏掉第三行日期致 education 三元组失配。"""
    from resume_parser.fields import extract_fields

    text = "教育经历\n沪江大学\n本科\n2022.09-2026.06\n技能证书\n普通话二甲\n"
    f = extract_fields(text)
    assert len(f.educations) == 1
    e = f.educations[0]
    assert (e.school, e.degree, e.date_range) == ("沪江大学", "本科", "2022.09-2026.06")


def test_VLM标量放大复读_开启后条带文本前置(monkeypatch):
    """Q7/Q8 实验结论：整页渲染下形近字姓名（冯静姝→妹）双模型都可能读错，
    顶部条带 2x 放大复读可救回。开启 RESUME_PARSER_VLM_SCALAR_ZOOM 后
    条带高分辨率文本必须前置（extract_fields 取首个匹配 → 复读结果优先）。"""
    from resume_parser.fields import extract_fields
    from resume_parser.ocr_backend import VlmOcrBackend

    monkeypatch.setenv("RESUME_PARSER_VLM_API_KEY", "k")
    monkeypatch.setenv("RESUME_PARSER_VLM_URL", "http://x")
    monkeypatch.setenv("RESUME_PARSER_VLM_SCALAR_ZOOM", "1")

    def fake_transcribe(self, image_png, prompt=None):
        # 条带图（宽 > 2×高 的横条）返回高分辨率复读；整页图返回带形近字错误的转写
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(image_png))
        if img.width > 2 * img.height:
            return "冯静姝\n电话 13800000009"
        return "冯静妹\n电话 13800000009 邮箱 user9@example.com\n实习经历\n…"

    monkeypatch.setattr(VlmOcrBackend, "_transcribe_page", fake_transcribe)
    backend = VlmOcrBackend()
    assert backend.scalar_zoom is True
    pdf = (CORPUS / "scanned-10.pdf").read_bytes()
    text = backend.extract(pdf, stem="scanned-10")
    assert text.startswith("冯静姝"), "条带复读文本必须前置"
    f = extract_fields(text)
    assert f.name == "冯静姝", "放大复读后姓名必须取高分辨率结果"


def test_VLM标量放大复读_默认关闭不增加调用(monkeypatch):
    """默认（未设 env）不开条带复读：行为与旧版一致，每页只 1 次转写。"""
    from resume_parser.ocr_backend import VlmOcrBackend

    monkeypatch.setenv("RESUME_PARSER_VLM_API_KEY", "k")
    monkeypatch.setenv("RESUME_PARSER_VLM_URL", "http://x")
    monkeypatch.delenv("RESUME_PARSER_VLM_SCALAR_ZOOM", raising=False)

    calls = []

    def fake_transcribe(self, image_png, prompt=None):
        calls.append(image_png)
        return "冯静妹"

    monkeypatch.setattr(VlmOcrBackend, "_transcribe_page", fake_transcribe)
    backend = VlmOcrBackend()
    assert backend.scalar_zoom is False
    text = backend.extract((CORPUS / "scanned-10.pdf").read_bytes(), stem="scanned-10")
    assert text == "冯静妹"
    assert len(calls) == 1, "默认不开启：单页单次调用"
