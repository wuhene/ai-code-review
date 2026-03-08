"""Git Diff Fetcher - 通过网络 API 获取分支差异（支持 GitHub/GitLab）。"""

import asyncio
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, quote

import httpx


@dataclass
class FileDiff:
    """表示单个文件的差异。"""
    filename: str
    diff: str
    old_path: Optional[str] = None
    new_path: Optional[str] = None


class GitDiffFetcher:
    """从 Git 平台（GitHub/GitLab）获取代码差异的网络请求实现。"""

    def __init__(
        self,
        token: str,
        repo_url: str,
        platform: str = "gitlab",  # "github" 或 "gitlab"
        base_url: Optional[str] = None  # 自定义 API 基础 URL（仅 GitLab 私有部署时使用）
    ):
        """
        初始化 Git diff 获取器。

        Args:
            token: API Token (GitHub Personal Access Token 或 GitLab Token)
            repo_url: 仓库地址
                - GitHub: owner/repo 格式
                - GitLab: group/subgroup/repo 或完整 URL
            platform: 平台类型 ('github' 或 'gitlab')
            base_url: 自定义 API 基础 URL（仅当 platform='gitlab' 且使用私有部署时使用）
        """
        self.token = token
        self.repo_url = repo_url.rstrip("/")
        self.platform = platform.lower()
        self.base_url = base_url

        # 设置默认的 API 基础 URL
        if self.platform == "github":
            self.api_base = "https://api.github.com"
        elif self.platform == "gitlab":
            # 如果是 https://gitlab.example.com/group/repo 格式，提取域名部分
            if repo_url.startswith("http"):
                parsed = urlparse(repo_url)
                self.api_base = f"{parsed.scheme}://{parsed.netloc}"
                if base_url:
                    self.api_base = base_url
            else:
                self.api_base = "https://gitlab.com/api/v4"
                if base_url:
                    self.api_base = base_url
        else:
            raise ValueError(f"不支持的平台：{self.platform}")

    def get_branch_diff(self, branch: str, base: str = "master") -> list[FileDiff]:
        """
        获取分支与基础分支之间的差异。

        Args:
            branch: 功能分支名称
            base: 基础分支名称（默认为 master）

        Returns:
            每个更改文件的 FileDiff 对象列表
        """
        if self.platform == "github":
            return self._get_github_diff(branch, base)
        elif self.platform == "gitlab":
            return self._get_gitlab_diff(branch, base)
        else:
            raise ValueError(f"不支持的平台：{self.platform}")

    def _get_github_diff(self, branch: str, base: str) -> list[FileDiff]:
        """从 GitHub API 获取分支差异。"""
        diffs = []

        try:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AI-Code-Reviewer"
            }

            # 获取分支对比信息
            url = f"{self.api_base}/repos/{self.repo_url}/compare/{base}...{branch}"

            async def fetch():
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    return response.json()

            data = asyncio.run(fetch())

            if "error" in data:
                raise RuntimeError(f"GitHub API 错误：{data['message']}")

            for file in data.get("files", []):
                if not file.get("filename", "").endswith(".py"):
                    continue

                diffs.append(FileDiff(
                    filename=file["filename"],
                    diff=file.get("patch", ""),
                    old_path=file.get("previous_filename"),
                    new_path=file["filename"]
                ))

        except Exception as e:
            raise RuntimeError(f"从 GitHub 获取 diff 失败：{str(e)}")

        return diffs

    def _get_gitlab_diff(self, branch: str, base: str) -> list[FileDiff]:
        """从 GitLab API 获取分支差异。"""
        diffs = []

        try:
            headers = {
                "PRIVATE-TOKEN": self.token,
                "Accept": "application/json"
            }

            # 获取合并请求/分支对比信息
            # GitLab API 端点：GET /projects/:id/repository/compare
            project_id = self._get_project_id()

            url = f"{self.api_base}/projects/{project_id}/repository/compare"
            params = {
                "from": base,
                "to": branch
            }

            async def fetch():
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    return response.json()

            import asyncio
            data = asyncio.run(fetch())

            if "error" in data or "message" in data:
                raise RuntimeError(f"GitLab API 错误：{data.get('error', data.get('message'))}")

            for file in data.get("diffs", []):
                filename = file.get("new_path") or file.get("old_path")

                if not filename or not filename.endswith(".py"):
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

    def _get_project_id(self) -> str:
        """获取 GitLab 项目 ID。"""
        try:
            # 尝试将 repo_url 转换为 project path
            # 例如：gitlab.example.com/group/subgroup/repo -> group%2Fsubgroup%2Frepo
            path = self.repo_url
            if path.startswith("http"):
                parsed = urlparse(path)
                path = parsed.path.lstrip("/")

            encoded_path = self._url_encode_group_path(path)

            headers = {
                "PRIVATE-TOKEN": self.token,
                "Accept": "application/json"
            }

            async def fetch():
                async with httpx.AsyncClient(timeout=30.0) as client:
                    url = f"{self.api_base}/projects?search={encoded_path}"
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    projects = response.json()

                    # 查找匹配的项目
                    target_path = self.repo_url.rsplit("/", 1)[-1]  # 取最后一层
                    for project in projects:
                        if project["name"] == target_path:
                            return str(project["id"])

                    # 如果没找到，返回第一个匹配
                    if projects:
                        return str(projects[0]["id"])

                    raise RuntimeError(f"未找到项目：{target_path}")

            return asyncio.run(fetch())

        except Exception as e:
            # 如果无法获取项目 ID，尝试直接解析
            return self._parse_project_id_from_url()

    def _url_encode_group_path(self, path: str) -> str:
        """URL 编码组路径。"""
        parts = path.split("/")
        # 除了最后一个部分（repo 名），其他都编码
        encoded_parts = [quote(p, safe='') for p in parts[:-1]] + [parts[-1]]
        return "/".join(encoded_parts)

    def _parse_project_id_from_url(self) -> str:
        """从 URL 解析项目 ID（备用方案）。"""
        # 对于简单情况，直接从 URL 中解析
        path = self.repo_url
        if path.startswith("http"):
            parsed = urlparse(path)
            path = parsed.path.lstrip("/")

        parts = path.split("/")
        # 最后两部分是 group/repo 或直接就是 repo
        if len(parts) >= 2:
            # 尝试构造完整的路径标识符
            return path  # 有些 GitLab 版本也接受路径作为标识符
        return parts[-1]
