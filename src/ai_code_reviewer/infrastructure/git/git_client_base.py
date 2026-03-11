"""
Git 客户端基类 - 定义 Git 平台 API 的统一接口。
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ...domain.entities import FileDiff


class GitClientBase(ABC):
    """Git 客户端基类，定义统一的接口。"""

    @abstractmethod
    async def get_branch_diff(self, branch: str, base: str = "master") -> List[FileDiff]:
        """
        获取分支与基础分支之间的差异。

        Args:
            branch: 功能分支名称
            base: 基础分支名称

        Returns:
            每个更改文件的 FileDiff 对象列表
        """
        pass

    @abstractmethod
    async def get_file_content(self, filepath: str, ref: str = "master") -> Optional[str]:
        """
        获取指定文件的内容。

        Args:
            filepath: 文件路径
            ref: 分支/标签名

        Returns:
            文件内容，失败返回 None
        """
        pass
