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
        project_root: str = ".",
        fetcher: Optional[GitDiffFetcher] = None,
        ref: str = "master",
        base_ref: str = "master",
        manual_files: Optional[List[str]] = None,
        auto_fetch_all: bool = True
    ):
        """
        初始化代码分析器。

        Args:
            project_root: 本地项目根目录
            fetcher: GitDiffFetcher 实例，用于从远程获取文件
            ref: 功能分支
            base_ref: 基础分支
            manual_files: 手动指定的文件列表
            auto_fetch_all: 是否自动获取所有文件
        """
        self.project_root = project_root
        self.fetcher = fetcher
        self.ref = ref
        self.base_ref = base_ref
        self.manual_files = manual_files or []
        self.auto_fetch_all = auto_fetch_all

        # 文件获取器
        self.file_fetcher = FileFetcher(project_root, fetcher, ref, base_ref)

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

    def get_file_content(self, filepath: str, branch: str = None) -> Optional[str]:
        """获取文件内容。"""
        return self.file_fetcher.get_file(filepath, branch)

    def get_file_both_branches(self, filepath: str):
        """获取文件在两个分支的内容。"""
        return self.file_fetcher.get_file_both_branches(filepath)
