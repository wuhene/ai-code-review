"""审查请求 - 表示一次代码审查的请求。"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ReviewRequest:
    """
    审查请求 - 表示一次代码审查的请求。

    属性:
        diff_content: diff 内容
        context_code: 完整代码上下文
        filename: 文件名
        element_name: 变更的元素名称
        element_type: 变更的元素类型
        element_line_start: 元素起始行
        element_line_end: 元素结束行
        call_chain_info: 调用链信息
    """
    diff_content: str
    context_code: str
    filename: str
    element_name: Optional[str] = None
    element_type: Optional[str] = None
    element_line_start: int = 0
    element_line_end: int = 0
    call_chain_info: Optional[str] = None
