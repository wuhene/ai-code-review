"""代码元素 - 表示一个代码变更的基本单元。"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CodeElement:
    """
    代码元素 - 表示一个代码变更的基本单元。

    属性:
        name: 元素名称（类名或方法名）
        element_type: 元素类型 ('class', 'method', 'function')
        filename: 文件名
        line_start: 起始行号
        line_end: 结束行号
        source: 源代码片段
        parent_class: 所属类（如果是方法）
    """
    name: str
    element_type: str  # 'class', 'method', 'function'
    filename: str
    line_start: int
    line_end: int
    source: str
    parent_class: Optional[str] = None
