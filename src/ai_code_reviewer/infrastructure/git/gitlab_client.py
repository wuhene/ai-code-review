"""
GitLab API 客户端实现。
"""

import base64
from typing import List, Optional
from urllib.parse import urlparse, quote

from ...domain.entities import FileDiff
from .git_client_base import GitClientBase


class GitLabClient(GitClientBase):
    """GitLab API 客户端。"""

    def __init__(self, token: str, repo_url: str, base_url: Optional[str] = None):
        """
        初始化 GitLab 客户端。

        Args:
            token: GitLab Private Token
            repo_url: 仓库地址
            base_url: 自定义 GitLab 地址（私有部署时使用）
        """
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装 httpx: pip install httpx")

        self.token = token
        self.repo_url = repo_url.rstrip("/")
        self.base_url = base_url
        self.httpx = httpx

        # 设置 API 基础 URL
        if base_url:
            self.api_base = base_url.rstrip('/')
            if "/api/v4" not in self.api_base:
                self.api_base = f"{self.api_base}/api/v4"
        else:
            self.api_base = "https://gitlab.com/api/v4"

        self._file_cache: dict = {}
        self._cached_project_id: Optional[str] = None

    async def get_branch_diff(self, branch: str, base: str = "master") -> List[FileDiff]:
        """获取分支差异。"""
        diffs = []

        try:
            headers = {
                "PRIVATE-TOKEN": self.token,
                "Accept": "application/json"
            }

            project_id = await self._get_project_id()

            url = f"{self.api_base}/projects/{project_id}/repository/compare"
            params = {
                "from": base,
                "to": branch
            }

            async with self.httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

            if "error" in data or "message" in data:
                raise RuntimeError(f"GitLab API 错误：{data.get('error', data.get('message'))}")

            for file in data.get("diffs", []):
                filename = file.get("new_path") or file.get("old_path")
                if not filename:
                    continue

                diffs.append(FileDiff(
                    filename=filename,
                    diff=file.get("diff", ""),
                    old_path=file.get("old_path"),
                    new_path=file.get("new_path")
                ))

        except Exception as e:
            raise RuntimeError(f"从 GitLab 获取 diff 失败：{str(e)}")

        return diffs

    async def get_file_content(self, filepath: str, ref: str = "master") -> Optional[str]:
        """获取文件内容。"""
        cache_key = f"{filepath}@{ref}"
        if cache_key in self._file_cache:
            return self._file_cache[cache_key]

        try:
            headers = {
                "PRIVATE-TOKEN": self.token,
                "Accept": "application/json"
            }

            project_id = await self._get_project_id()

            url = f"{self.api_base}/projects/{project_id}/repository/files/{quote(filepath, safe='')}"
            params = {"ref": ref}

            async with self.httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                content = base64.b64decode(data["content"]).decode('utf-8')
                self._file_cache[cache_key] = content
                return content

        except Exception:
            return None

    async def _get_project_id(self) -> str:
        """获取项目 ID。"""
        if self._cached_project_id:
            return self._cached_project_id

        path = self.repo_url
        if path.startswith("http"):
            parsed = urlparse(path)
            path = parsed.path.lstrip("/")

        encoded_path = quote(path, safe='')

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json"
        }

        async with self.httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            url = f"{self.api_base}/projects/{encoded_path}"
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                project = response.json()
                project_id = str(project["id"])
                self._cached_project_id = project_id
                return project_id
            elif response.status_code == 404:
                # 尝试搜索
                target_path = path.rsplit("/", 1)[-1]
                search_url = f"{self.api_base}/projects?search={target_path}"
                response = await client.get(search_url, headers=headers)

                if response.status_code == 200:
                    projects = response.json()
                    if isinstance(projects, list) and projects:
                        project_id = str(projects[0]["id"])
                        self._cached_project_id = project_id
                        return project_id

        raise RuntimeError(f"未找到项目：{path}")
