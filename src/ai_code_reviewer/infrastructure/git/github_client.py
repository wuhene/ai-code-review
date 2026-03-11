"""
GitHub API 客户端实现。
"""

import base64
from typing import List, Optional
from urllib.parse import urlparse

from ...domain.entities import FileDiff
from .git_client_base import GitClientBase


class GitHubClient(GitClientBase):
    """GitHub API 客户端。"""

    def __init__(self, token: str, repo_url: str):
        """
        初始化 GitHub 客户端。

        Args:
            token: GitHub Personal Access Token
            repo_url: 仓库地址 (owner/repo 格式)
        """
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装 httpx: pip install httpx")

        self.token = token
        self.repo_url = repo_url.rstrip("/")
        self.api_base = "https://api.github.com"
        self.httpx = httpx
        self._file_cache: dict = {}

    async def get_branch_diff(self, branch: str, base: str = "master") -> List[FileDiff]:
        """获取分支差异。"""
        diffs = []

        try:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AI-Code-Reviewer"
            }

            url = f"{self.api_base}/repos/{self.repo_url}/compare/{base}...{branch}"

            with self.httpx.Client(timeout=60.0) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

            if "error" in data:
                raise RuntimeError(f"GitHub API 错误：{data['message']}")

            for file in data.get("files", []):
                diffs.append(FileDiff(
                    filename=file["filename"],
                    diff=file.get("patch", ""),
                    old_path=file.get("previous_filename"),
                    new_path=file["filename"]
                ))

        except Exception as e:
            raise RuntimeError(f"从 GitHub 获取 diff 失败：{str(e)}")

        return diffs

    async def get_file_content(self, filepath: str, ref: str = "master") -> Optional[str]:
        """获取文件内容。"""
        cache_key = f"{filepath}@{ref}"
        if cache_key in self._file_cache:
            return self._file_cache[cache_key]

        try:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }

            url = f"{self.api_base}/repos/{self.repo_url}/contents/{filepath}"
            params = {"ref": ref}

            with self.httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                content = base64.b64decode(data["content"]).decode('utf-8')
                self._file_cache[cache_key] = content
                return content

        except Exception:
            return None
