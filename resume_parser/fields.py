"""字段抽取：规则驱动，缺失=None + 降置信度，绝不推测。

防线（对应问题报告 RPI-001/RPI-003）：
- 抽不到 → None（下游拿到 null 知道缺失，触发"回退让用户手动补"）
- 不根据上下文"补全"字段——那是下游 LLM 层的职责，且有 RPI-002 的编造风险
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTION_TITLE_RE = re.compile(r"(实习经历|工作经历|教育经历|技能证书|时间轴|教育|证书)")
PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
DATE_RANGE_RE = re.compile(
    r"(20\d{2})[./年]\s?(\d{1,2})\s?[月./-]?\s*[-—~至到]\s*(20\d{2})[./年]?\s?(\d{1,2})?\s?月?"
)
SCHOOL_RE = re.compile(r"([\u4e00-\u9fa5]{2,12}(?:大学|学院|学校|职业技术学院))")
DEGREE_RE = re.compile(r"(本科|大专|专科|硕士|博士|本科在读|专科在读)")
ORG_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,20}?(?:有限公司|集团|事务所|银行|研究院|公司))")
CERT_RE = re.compile(
    r"(CET-?4|CET-?6|CPA|PMP|FRM|CFA|司法考试|法律职业资格|教师资格证|计算机二级|计算机三级|普通话二甲|驾驶证)"
)


@dataclass
class Education:
    school: str | None = None
    degree: str | None = None
    date_range: str | None = None


@dataclass
class WorkExperience:
    company: str | None = None
    title: str | None = None
    date_range: str | None = None
    description: str | None = None


@dataclass
class Fields:
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    educations: list[Education] = field(default_factory=list)
    work_experiences: list[WorkExperience] = field(default_factory=list)
    certificates: list[str] = field(default_factory=list)


def extract_fields(text: str, naive: bool = False) -> Fields:
    """naive=True 为 v0.1.0 基线行为：无标题过滤、无二次回填（最朴素的邻近启发式）。"""
    f = Fields()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 姓名：首个长度 2-4 的纯中文短行（简历顶部惯例）
    for ln in lines[:6]:
        if 2 <= len(ln) <= 4 and re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", ln):
            f.name = ln
            break

    m = PHONE_RE.search(text)
    if m:
        f.phone = m.group().strip()
    m = EMAIL_RE.search(text)
    if m:
        f.email = m.group().strip()

    f.certificates = sorted(set(CERT_RE.findall(text)))

    # 教育/经历：逐行状态机。含学校词的行开教育段；含公司词的行开经历段。
    for i, ln in enumerate(lines):
        school = SCHOOL_RE.search(ln)
        if school and not any(e.school == school.group(1) for e in f.educations):
            edu = Education(school=school.group(1))
            ctx = " ".join(lines[i : i + 2])
            d = DEGREE_RE.search(ctx)
            if d:
                edu.degree = d.group().strip()
            dr = DATE_RANGE_RE.search(ctx)
            if dr:
                edu.date_range = dr.group().strip()
            f.educations.append(edu)
            continue
        org = ORG_RE.search(ln)
        if org:
            existing = next((w for w in f.work_experiences if w.company == org.group(1)), None)
            if existing is None:
                work = WorkExperience(company=org.group(1))
                _fill_work(work, lines, i, naive=naive)
                f.work_experiences.append(work)
            elif not naive:
                # v1.0.0：同一公司二次出现（双栏模板：左栏时间轴 + 右栏详情块），
                # 阅读顺序正确时右栏块邻近信息更完整 → 回填缺失/标题样的字段
                _fill_work(existing, lines, i, only_fill_gaps=True)

    return f

def _desc_candidate(lines: list[str], i: int, naive: bool = False) -> str | None:
    if naive:
        # v0.1.0：公司行后第一个非公司行（不做标题/日期过滤——交错时必错）
        for ln2 in lines[i + 1 : i + 4]:
            if not ORG_RE.search(ln2):
                return ln2
        return None
    for ln2 in lines[i + 1 : i + 4]:
        if ORG_RE.search(ln2) or SCHOOL_RE.search(ln2) or SECTION_TITLE_RE.search(ln2):
            continue
        if DATE_RANGE_RE.search(ln2) and len(ln2) <= 16:
            continue  # 纯日期行不是描述
        return ln2
    return None


def _fill_work(work: WorkExperience, lines: list[str], i: int,
               only_fill_gaps: bool = False, naive: bool = False) -> None:
    cur = lines[i]  # 当前行：详情块的公司行自带职位/时间轴行自带日期
    ctx = " ".join(lines[max(0, i - 1) : i + 3])
    dr = DATE_RANGE_RE.search(cur) or DATE_RANGE_RE.search(ctx)
    if dr and not work.date_range:
        work.date_range = dr.group().strip()
    t = re.search(
        r"(后端|前端|算法|产品|运营|数据|测试|开发|设计)(工程师|专员|经理|助理|实习生|分析师)?",
        cur,
    ) or re.search(
        r"(后端|前端|算法|产品|运营|数据|测试|开发|设计)(工程师|专员|经理|助理|实习生|分析师)?",
        ctx,
    )
    if t and (not work.title or only_fill_gaps):
        work.title = t.group().strip()
    cand = _desc_candidate(lines, i, naive=naive)
    if cand and (not only_fill_gaps or not work.description
                 or SECTION_TITLE_RE.search(work.description)):
        work.description = cand
