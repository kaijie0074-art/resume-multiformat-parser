"""OCR 后端抽象。

设计要点（docs/design.md）：图片型 PDF 必须走 OCR/多模态路径，且**未配置后端时
必须显式失败**——绝不允许"文本为空 → 当作空简历继续"或"让下游 LLM 编造"。
这条纪律来自问题报告 RPI-002：空文本静默喂给 LLM = 模型基于岗位描述编造整份简历。

三个实现：
- RecordedOcrBackend：回放 evals/ocr_fixtures/<stem>.json（CI 零依赖确定性路径）
- PaddleOcrBackend：指向自托管 PP-StructureV3/PaddleOCR 服务的桩（env RESUME_PARSER_PADDLE_URL）
- VlmOcrBackend：多模态 LLM 直读桩（env RESUME_PARSER_VLM_API_KEY + RESUME_PARSER_VLM_URL）
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


class RecordedOcrBackend(OcrBackend):
    name = "recorded"

    def __init__(self, fixtures_dir: str | Path):
        self.fixtures_dir = Path(fixtures_dir)

    def extract(self, pdf_bytes: bytes, stem: str = "") -> str:
        path = self.fixtures_dir / f"{stem}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"OCR 回放语料缺失: {path}。请先用 evals/generate_corpus.py 生成，"
                f"或改用 PaddleOcrBackend/VlmOcrBackend 并配置相应环境变量。"
            )
        return json.loads(path.read_text(encoding="utf-8"))["text"]


class PaddleOcrBackend(OcrBackend):
    """自托管 PP-StructureV3 服务桩。生产接入：POST pdf → markdown 文本。"""

    name = "paddle"

    def __init__(self):
        self.url = os.environ.get("RESUME_PARSER_PADDLE_URL", "")

    def extract(self, pdf_bytes: bytes, stem: str = "") -> str:
        if not self.url:
            raise OcrNotConfiguredError(
                "图片型 PDF 需要 OCR 后端，但 RESUME_PARSER_PADDLE_URL 未配置。"
                "配置方式：export RESUME_PARSER_PADDLE_URL=http://<paddle-service>/predict；"
                "或选择 VlmOcrBackend（RESUME_PARSER_VLM_API_KEY/RESUME_PARSER_VLM_URL）。"
                "在未配置后端时，本服务拒绝静默返回空结果。"
            )
        import urllib.request

        req = urllib.request.Request(
            self.url, data=pdf_bytes, headers={"Content-Type": "application/pdf"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")


class VlmOcrBackend(OcrBackend):
    """多模态 LLM 直读桩（每页渲染成图 → VLM）。"""

    name = "vlm"

    def __init__(self):
        self.api_key = os.environ.get("RESUME_PARSER_VLM_API_KEY", "")
        self.url = os.environ.get("RESUME_PARSER_VLM_URL", "")

    def extract(self, pdf_bytes: bytes, stem: str = "") -> str:
        if not (self.api_key and self.url):
            raise OcrNotConfiguredError(
                "图片型 PDF 需要 OCR 后端，但 RESUME_PARSER_VLM_API_KEY / RESUME_PARSER_VLM_URL 未配置。"
                "本服务在未配置后端时拒绝静默返回空结果（防下游 LLM 编造，见 RPI-002）。"
            )
        raise NotImplementedError(
            "VLM 直读适配器为生产接入位：渲染-分页-直读实现不属本演练范围，"
            "演练环境使用 RecordedOcrBackend 等价回放其输出。"
        )
