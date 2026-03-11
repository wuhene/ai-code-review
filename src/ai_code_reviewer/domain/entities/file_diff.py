"""文件差异 - 表示单个文件的变更。"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class FileDiff:
    """
    文件差异 - 表示单个文件的变更。

    属性:
        filename: 文件名
        diff: diff 内容
        old_path: 旧文件路径（如果文件被重命名）
        new_path: 新文件路径
    """
    filename: str
    diff: str
    old_path: Optional[str] = None
    new_path: Optional[str] = None
