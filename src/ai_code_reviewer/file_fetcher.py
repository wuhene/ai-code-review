"""代码分析器 - 获取远程文件内容。"""

from pathlib import Path
from typing import Optional, Dict

try:
    from .gitlab_diff import GitDiffFetcher
except ImportError:
    from gitlab_diff import GitDiffFetcher


class FileFetcher:
    """从远程或本地获取文件内容。"""

    def __init__(
        self,
        project_root: str = ".",
        fetcher: Optional[GitDiffFetcher] = None,
        ref: str = "master",
        base_ref: str = "master"
    ):
        """
        初始化文件获取器。

        Args:
            project_root: 本地项目根目录
            fetcher: GitDiffFetcher 实例，用于从远程获取文件
            ref: 功能分支
            base_ref: 基础分支
        """
        self.project_root = Path(project_root)
        self.fetcher = fetcher
        self.ref = ref
        self.base_ref = base_ref

        # 缓存
        self._file_cache: Dict[str, str] = {}
        self._base_file_cache: Dict[str, str] = {}

    def get_file(self, filepath: str, branch: str = None) -> Optional[str]:
        """获取指定分支的文件内容。"""
        if branch is None:
            branch = self.ref

        cache = self._file_cache if branch == self.ref else self._base_file_cache
        cache_key = f"{filepath}@{branch}"

        if cache_key in cache:
            return cache[cache_key]

        # 优先从远程获取
        if self.fetcher:
            content = self.fetcher.get_file_content(filepath, branch)
            if content:
                cache[cache_key] = content
                return content

        # 从本地读取
        file_path = self.project_root / filepath
        if file_path.exists():
            try:
                content = file_path.read_text(encoding='utf-8')
                cache[cache_key] = content
                return content
            except Exception:
                pass

        return None

    def get_file_both_branches(self, filepath: str) -> tuple[Optional[str], Optional[str]]:
        """获取文件在两个分支的内容。"""
        branch_content = self.get_file(filepath, self.ref)
        base_content = self.get_file(filepath, self.base_ref)
        return branch_content, base_content
