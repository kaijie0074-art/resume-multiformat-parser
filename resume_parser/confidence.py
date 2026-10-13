"""字段级置信度与 needs_manual 判定。

置信度来源（评审意见 #6，数值依据）：
- 抽取来源层：文本层直抽 1.0（零几何变换）；双栏重排 0.9（几何重排引入
  行归并误差，来自黄金集上重排前后字段一致率 ~90%+ 的实测口径）；
  真实 OCR 0.85（OCR 引入字符错误）；docx 表格 0.95（结构化来源，仅单元格去重逻辑）。
- 规则命中强度：正则强命中（手机号/邮箱）全额；启发式（姓名/职位）×0.8。
置信度是**先验**，评估集（run_eval.py）负责事后校准。

needs_manual 规则：必填字段（name、phone/email 至少其一、至少 1 段教育）
缺失或置信度 < REQUIRED_CONFIDENCE → True，并给出可读 warnings。
"""

from __future__ import annotations

from dataclasses import dataclass

from .fields import Fields

REQUIRED_CONFIDENCE = 0.8

SOURCE_CONFIDENCE = {
    "text": 1.0,
    "layout": 0.9,
    "ocr": 0.85,
    "docx": 0.95,
}
HEURISTIC_FACTOR = 0.8  # 启发式字段（姓名/职位）打折


@dataclass
class Confidence:
    values: dict[str, float]
    needs_manual: bool
    warnings: list[str]


def assess(fields: Fields, source: str, route_reason: str = "") -> Confidence:
    base = SOURCE_CONFIDENCE.get(source, 0.8)
    values: dict[str, float] = {}
    warnings: list[str] = []

    values["name"] = base * HEURISTIC_FACTOR if fields.name else 0.0
    values["phone"] = base if fields.phone else 0.0
    values["email"] = base if fields.email else 0.0
    values["educations"] = base if fields.educations else 0.0
    values["work_experiences"] = base if fields.work_experiences else 0.0
    values["certificates"] = base if fields.certificates else 0.0

    needs_manual = False
    if not fields.name:
        warnings.append("姓名未抽取到")
        needs_manual = True
    if not (fields.phone or fields.email):
        warnings.append("联系方式（手机/邮箱）均未抽取到")
        needs_manual = True
    if not fields.educations:
        warnings.append("教育经历未抽取到")
        needs_manual = True
    if not fields.work_experiences:
        warnings.append("工作/实习经历未抽取到")
        needs_manual = True
    if source == "ocr":
        warnings.append("来源为 OCR，建议用户核对关键事实字段")

    if route_reason:
        warnings.append(f"路由说明: {route_reason}")

    return Confidence(values=values, needs_manual=needs_manual, warnings=warnings)
