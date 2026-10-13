"""OCR 后端抽象。

设计要点（docs/design.md）：图片型 PDF 必须走 OCR/多模态路径，且**未配置后端时
必须显式失败**——绝不允许"文本为空 → 当作空简历继续"或"让下游 LLM 编造"。
这条纪律来自问题报告 RPI-002：空文本静默喂给 LLM = 模型基于岗位描述编造整份简历。

两个真实实现：
- PaddleOcrBackend：自托管 PP-StructureV3/PaddleOCR 服务（env RESUME_PARSER_PADDLE_URL）
- VlmOcrBackend：多模态 LLM 直读（env RESUME_PARSER_VLM_API_KEY + RESUME_PARSER_VLM_URL，
  OpenAI 兼容协议；每页渲染 PNG 后送 VLM 转写）
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class OcrBackend:
    """OCR/多模态抽取接口：输入 PDF 字节，输出纯文本（保持版面阅读顺序尽量好）。"""

    name = "abstract"

    def extract(self, pdf_bytes: bytes, stem: str = "") -> str:
        raise NotImplementedError


class OcrNotConfiguredError(RuntimeError):
    """OCR 后端未配置。信息必须包含配置指引（评审意见 #3）。"""


CONFIG_HINT = (
    "配置方式：\n"
    "  自托管 PaddleOCR：export RESUME_PARSER_PADDLE_URL=http://<paddle-service>/predict\n"
    "  或多模态 LLM 直读：export RESUME_PARSER_VLM_API_KEY=<key> "
    "RESUME_PARSER_VLM_URL=https://open.bigmodel.cn/api/paas/v4\n"
    "  （可选 RESUME_PARSER_VLM_MODEL，默认 glm-4v-flash，任意 OpenAI 兼容多模态服务均可）。\n"
    "在未配置后端时，本服务拒绝静默返回空结果。"
)


class PaddleOcrBackend(OcrBackend):
    """自托管 PP-StructureV3 服务：POST pdf → markdown 文本。"""

    name = "paddle"

    def __init__(self):
        self.url = os.environ.get("RESUME_PARSER_PADDLE_URL", "")

    def extract(self, pdf_bytes: bytes, stem: str = "") -> str:
        if not self.url:
            raise OcrNotConfiguredError(
                "图片型 PDF 需要 OCR 后端，但 RESUME_PARSER_PADDLE_URL 未配置。\n" + CONFIG_HINT
            )
        import urllib.request

        req = urllib.request.Request(
            self.url, data=pdf_bytes, headers={"Content-Type": "application/pdf"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")


# VLM 直读转写指令：要求逐字转写而非摘要，保持阅读顺序，不补全不编造
_VLM_PROMPT = (
    "逐字转写这页简历图片中的全部文字，保持从上到下、从左到右的阅读顺序。"
    "只输出图中真实存在的内容，不要总结、不要补全、不要纠正。"
)

# 顶部条带（姓名/联系方式区）二次放大转写指令：标量字段的高分辨率复读
_STRIP_PROMPT = (
    "逐字转写这页简历顶部区域的全部文字，保持阅读顺序，不要补全或纠正。"
)



def _is_tofu_score(text: str) -> int:
    """豆腐块（□ U+25A1 / 替换字符 U+FFFD）计数，用于择优。"""
    return text.count("\u25a1") + text.count("\ufffd")


def _is_tofu(text: str) -> bool:
    """成片豆腐块判定：≥10 个即认为转写质量不可用（正常转写不出现该字符）。"""
    return _is_tofu_score(text) >= 10


class VlmOcrBackend(OcrBackend):
    """多模态 LLM 直读：每页渲染成 PNG → OpenAI 兼容 /chat/completions 转写。"""

    name = "vlm"

    def __init__(self):
        self.api_key = os.environ.get("RESUME_PARSER_VLM_API_KEY", "")
        self.url = os.environ.get("RESUME_PARSER_VLM_URL", "")
        self.model = os.environ.get("RESUME_PARSER_VLM_MODEL", "glm-4v-flash")
        # 标量字段放大复读（默认关）：形近字在小字号整页渲染下处于模型识别边界
        # （2026-10-14 Q7 实测：整页 150dpi 冯静姝→妹 8/8 错，顶条 2x 放大双模型全对）。
        # 开启后每页多一次 API 调用（+1 成本），换姓名/联系方式的高分辨率复读。
        self.scalar_zoom = os.environ.get("RESUME_PARSER_VLM_SCALAR_ZOOM", "") in ("1", "on", "true")

    def _transcribe_page(self, image_png: bytes, prompt: str = _VLM_PROMPT) -> str:
        import base64
        import urllib.request

        b64 = base64.b64encode(image_png).decode("ascii")
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url.rstrip('/')}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"].strip()

    def _top_strip_zoomed(self, page, dpi: int = 150, frac: float = 0.12, zoom: float = 2.0) -> str:
        """顶部条带裁剪 + 放大重转写（姓名/联系方式区的高分辨率复读）。"""
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png")))
        w, h = img.size
        strip = img.crop((0, 0, w, int(h * frac)))
        strip = strip.resize((int(strip.width * zoom), int(strip.height * zoom)), Image.LANCZOS)
        buf = io.BytesIO()
        strip.save(buf, format="PNG")
        return self._transcribe_page(buf.getvalue(), prompt=_STRIP_PROMPT)

    def extract(self, pdf_bytes: bytes, stem: str = "") -> str:
        if not (self.api_key and self.url):
            raise OcrNotConfiguredError(
                "图片型 PDF 需要 OCR 后端，但 RESUME_PARSER_VLM_API_KEY / RESUME_PARSER_VLM_URL 未配置。\n"
                + CONFIG_HINT
            )
        import fitz  # PyMuPDF

        pages: list[str] = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text = self._transcribe_page(page.get_pixmap(dpi=150).tobytes("png"))
                if _is_tofu(text):
                    # 端点对同一字节输入转写确定（2026-10-14 Q5 实测 6/6 一致）；
                    # 豆腐块与渲染像素相关 → 升档 180dpi 改变像素即可自愈，仍败则如实保留。
                    retry = self._transcribe_page(page.get_pixmap(dpi=180).tobytes("png"))
                    text = retry if not _is_tofu(retry) else min(text, retry, key=_is_tofu_score)
                if self.scalar_zoom:
                    # 条带文本前置：extract_fields 的姓名/电话/邮箱取首个匹配，
                    # 高分辨率复读结果优先（Q8 验证：F1 0.99→1.00，其余组不受影响）
                    text = self._top_strip_zoomed(page) + "\n" + text if text else text
                pages.append(text)
        return "\n".join(p for p in pages if p)


def pick_configured_backend() -> OcrBackend | None:
    """按环境变量返回已配置的真实 OCR 后端；均未配置返回 None（由调用方决定报错/跳过）。"""
    if os.environ.get("RESUME_PARSER_PADDLE_URL"):
        return PaddleOcrBackend()
    if os.environ.get("RESUME_PARSER_VLM_API_KEY") and os.environ.get("RESUME_PARSER_VLM_URL"):
        return VlmOcrBackend()
    return None
