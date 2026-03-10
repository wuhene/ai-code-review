"""代码分析器 - 主入口，协调元素提取和文件获取。"""

from typing import Optional, List

from .element_extractor import CodeElement, ElementExtractor
from .file_fetcher import FileFetcher

try:
    from .gitlab_diff import GitDiffFetcher
except ImportError:
    from gitlab_diff import GitDiffFetcher


class CodeAnalyzer:
    """代码分析器主类。"""

    def __init__(
        self,
        fetcher: Optional[GitDiffFetcher] = None,
        ref: str = "master",
        base_ref: str = "master"
    ):
        """
        初始化代码分析器。

        Args:
            fetcher: GitDiffFetcher 实例，用于从远程获取文件
            ref: 功能分支
            base_ref: 基础分支
        """
        self.fetcher = fetcher
        self.ref = ref
        self.base_ref = base_ref

        # 文件获取器
        self.file_fetcher = FileFetcher(fetcher, ref, base_ref)

    def extract_changed_elements(self, diff_content: str, filename: str) -> List[CodeElement]:
        """
        从 diff 中提取变化的代码元素。

        Args:
            diff_content: diff 内容
            filename: 文件名

        Returns:
            代码元素列表
        """
        return ElementExtractor.extract_from_diff(diff_content, filename)

    async def get_file_both_branches(self, filepath: str):
        """获取文件在两个分支的内容。"""
        return await self.file_fetcher.get_file_both_branches(filepath)
