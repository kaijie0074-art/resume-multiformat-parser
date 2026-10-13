"""研究用 VLM 探针：串行限速客户端 + JSONL 调用缓存。

约定（研究方法/共享配额）：
- 所有调用串行执行，相邻真实调用间 sleep ≥2s
- HTTP 429 → sleep 60s 重试，最多 3 次
- 原始输出落盘 evidence/research-20261014/calls.jsonl（可追溯、可复算）
- 相同 (model, stem, dpi, tag, prompt) 命中缓存绝不重复调用（重跑免费）
- API key 只从环境变量读，绝不写入任何文件
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "evidence" / "research-20261014"
CALLS = EVID / "calls.jsonl"

TRANSCRIBE_PROMPT = (
    "逐字转写这页简历图片中的全部文字，保持从上到下、从左到右的阅读顺序。"
    "只输出图中真实存在的内容，不要总结、不要补全、不要纠正。"
)

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_last_call_ts = 0.0


def _load_cache() -> dict[str, str]:
    cache: dict[str, str] = {}
    if CALLS.exists():
        for ln in CALLS.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rec = json.loads(ln)
                cache[rec["key"]] = rec["content"]
    return cache


def _strip_reasoning(content: str) -> str:
    return _THINK_RE.sub("", content).strip()


def cache_key(model: str, stem: str, dpi: int, tag: str, prompt: str) -> str:
    ph = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
    return hashlib.sha1(f"{model}|{stem}|{dpi}|{tag}|{ph}".encode()).hexdigest()[:16]


def transcribe(
    image_png: bytes,
    *,
    model: str,
    stem: str,
    dpi: int,
    tag: str = "",
    prompt: str = TRANSCRIBE_PROMPT,
    timeout: int = 300,
) -> str:
    """转写一页图片。命中缓存直接返回；未命中才发真实请求（限速 + 重试）。"""
    global _last_call_ts
    key = cache_key(model, stem, dpi, tag, prompt)
    cached = _load_cache().get(key)
    if cached is not None:
        return cached

    api_key = os.environ["RESUME_PARSER_VLM_API_KEY"]
    url = os.environ.get("RESUME_PARSER_VLM_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
    b64 = base64.b64encode(image_png).decode("ascii")
    body = json.dumps(
        {
            "model": model,
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

    last_err: Exception | None = None
    for attempt in range(3):
        wait = _last_call_ts + 2.0 - time.time()
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(
            f"{url.rstrip('/')}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            raw = payload["choices"][0]["message"].get("content") or ""
            reasoning = payload["choices"][0]["message"].get("reasoning_content") or ""
            content = _strip_reasoning(raw)
            latency = round(time.monotonic() - t0, 2)
            _last_call_ts = time.monotonic()
            EVID.mkdir(parents=True, exist_ok=True)
            with CALLS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "key": key, "model": model, "stem": stem, "dpi": dpi, "tag": tag,
                    "latency_s": latency, "usage": payload.get("usage"),
                    "reasoning_chars": len(reasoning), "content": content,
                }, ensure_ascii=False) + "\n")
            return content
        except urllib.error.HTTPError as e:
            _last_call_ts = time.monotonic()
            last_err = e
            if e.code == 429 and attempt < 2:
                print(f"[429] {stem} {model} dpi={dpi} tag={tag} → sleep 60 重试 ({attempt + 1}/3)")
                time.sleep(60)
                continue
            raise
    raise RuntimeError(f"重试耗尽: {stem} {model} dpi={dpi} tag={tag}: {last_err}")


def render_page(pdf_path: Path, dpi: int) -> bytes:
    """PDF 第一页按 dpi 渲染为 PNG 字节（与生产 VlmOcrBackend 同路径）。"""
    import fitz  # PyMuPDF

    with fitz.open(pdf_path) as doc:
        return doc[0].get_pixmap(dpi=dpi).tobytes("png")


def call_log_stats() -> dict:
    """缓存文件统计（真实调用次数/模型分布）。"""
    if not CALLS.exists():
        return {"calls": 0}
    recs = [json.loads(ln) for ln in CALLS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    by_model: dict[str, int] = {}
    for r in recs:
        by_model[r["model"]] = by_model.get(r["model"], 0) + 1
    return {"calls": len(recs), "by_model": by_model}
