"""resume-parser：简历多格式解析路由（文本层判空 / 双栏重排 / docx 表格 / OCR 后端抽象）。"""

from .fields import Fields, Education, WorkExperience
from .service import ParseResult, parse, parse_baseline

__all__ = ["Fields", "Education", "WorkExperience", "ParseResult", "parse", "parse_baseline"]
__version__ = "1.0.0"
