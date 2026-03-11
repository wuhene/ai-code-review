"""
Git 客户端工厂 - 根据平台类型创建对应的客户端。
"""

from typing import Optional

from .git_client_base import GitClientBase
from .github_client import GitHubClient
from .gitlab_client import GitLabClient


class GitFactory:
    """Git 客户端工厂类。"""

    @classmethod
    def create_client(
        cls,
        platform: str,
        token: str,
        repo_url: str,
        base_url: Optional[str] = None
    ) -> GitClientBase:
        """
        根据平台类型创建 Git 客户端。

        Args:
            platform: 平台类型 ('github' 或 'gitlab')
            token: API Token
            repo_url: 仓库地址
            base_url: 自定义 API 端点（仅 GitLab 使用）

        Returns:
            Git 客户端实例
        """
        platform = platform.lower()

        if platform == "github":
            return GitHubClient(token=token, repo_url=repo_url)
        elif platform == "gitlab":
            return GitLabClient(token=token, repo_url=repo_url, base_url=base_url)
        else:
            raise ValueError(f"不支持的平台：{platform}")
