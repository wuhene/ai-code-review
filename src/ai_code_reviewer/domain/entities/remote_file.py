"""远程文件 - 表示从 Git 仓库获取的文件。"""

from dataclasses import dataclass


@dataclass
class RemoteFile:
    """
    远程文件 - 表示从 Git 仓库获取的文件。

    属性:
        path: 文件路径
        content: 文件内容
        file_type: 文件类型 (python, java, go, etc.)
    """
    path: str
    content: str
    file_type: str = "python"
