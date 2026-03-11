"""审查结果 - 表示 AI 代码审查的结果。"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ReviewResult:
    """
    审查结果 - 表示 AI 代码审查的结果。

    属性:
        filename: 文件名
        element_name: 变更的元素名称
        summary: 审查摘要
        issues: 发现的问题列表
        suggestions: 改进建议列表
        raw_response: AI 原始响应
        element_type: 元素类型
        element_line_start: 元素起始行
        element_line_end: 元素结束行
    """
    filename: str
    element_name: Optional[str]
    summary: str
    issues: list[dict]
    suggestions: list[str]
    raw_response: str
    element_type: Optional[str] = None
    element_line_start: int = 0
    element_line_end: int = 0
