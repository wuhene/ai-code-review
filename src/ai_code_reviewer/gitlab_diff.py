"""Git Diff Fetcher - 通过网络 API 获取分支差异（支持 GitHub/GitLab）。"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from urllib.parse import urlparse, quote

import httpx


@dataclass
class FileDiff:
    """表示单个文件的差异。"""
    filename: str
    diff: str
    old_path: Optional[str] = None
    new_path: Optional[str] = None


@dataclass
class RemoteFile:
    """表示一个远程文件及其内容。"""
    path: str
    content: str
    file_type: str = "python"  # python, java, go, etc.


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
            self.content_base = "https://raw.githubusercontent.com"
        elif self.platform == "gitlab":
            # 如果是 https://gitlab.example.com/group/repo 格式，提取域名部分
            if repo_url.startswith("http"):
                parsed = urlparse(repo_url)
                self.api_base = f"{parsed.scheme}://{parsed.netloc}"
                self.content_base = self.api_base
                if base_url:
                    self.api_base = base_url
                    self.content_base = base_url
            else:
                self.api_base = "https://gitlab.com/api/v4"
                self.content_base = "https://gitlab.com"
                if base_url:
                    self.api_base = base_url
                    self.content_base = base_url
        else:
            raise ValueError(f"不支持的平台：{self.platform}")

        # 缓存已获取的远程文件
        self._file_cache: Dict[str, str] = {}

    async def get_branch_diff(self, branch: str, base: str = "master") -> list[FileDiff]:
        """
        获取分支与基础分支之间的差异。

        Args:
            branch: 功能分支名称
            base: 基础分支名称（默认为 master）

        Returns:
            每个更改文件的 FileDiff 对象列表
        """
        if self.platform == "github":
            return await self._get_github_diff_async(branch, base)
        elif self.platform == "gitlab":
            return await self._get_gitlab_diff_async(branch, base)
        else:
            raise ValueError(f"不支持的平台：{self.platform}")

    async def get_branch_diff_async(self, branch: str, base: str = "master") -> list[FileDiff]:
        """异步获取分支差异。"""
        if self.platform == "github":
            return await self._get_github_diff_async(branch, base)
        elif self.platform == "gitlab":
            return await self._get_gitlab_diff_async(branch, base)
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

    async def _get_github_diff_async(self, branch: str, base: str) -> list[FileDiff]:
        """异步获取 GitHub 分支差异。"""
        diffs = []

        try:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AI-Code-Reviewer"
            }

            url = f"{self.api_base}/repos/{self.repo_url}/compare/{base}...{branch}"

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

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

    async def _get_gitlab_diff_async(self, branch: str, base: str) -> list[FileDiff]:
        """异步获取 GitLab 分支差异。"""
        diffs = []

        try:
            headers = {
                "PRIVATE-TOKEN": self.token,
                "Accept": "application/json"
            }

            project_id = self._get_project_id()

            url = f"{self.api_base}/projects/{project_id}/repository/compare"
            params = {
                "from": base,
                "to": branch
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

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
            path = self.repo_url
            if path.startswith("http"):
                parsed = urlparse(path)
                path = parsed.path.lstrip("/")

            # URL 编码路径（将 / 编码为 %2F）
            encoded_path = quote(path, safe='')

            headers = {
                "PRIVATE-TOKEN": self.token,
                "Accept": "application/json"
            }

            async def fetch():
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # 方法1：直接通过编码路径获取项目
                    url = f"{self.api_base}/projects/{encoded_path}"
                    print(f"  [调试] 尝试获取项目: {url}")
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        project = response.json()
                        print(f"  [调试] 找到项目: {project.get('name')} (id: {project.get('id')})")
                        return str(project["id"])
                    elif response.status_code == 404:
                        # 方法2：使用 search API 作为备用
                        print(f"  [调试] 直接获取失败，尝试搜索...")
                        target_path = path.rsplit("/", 1)[-1]
                        search_url = f"{self.api_base}/projects?search={target_path}"
                        response = await client.get(search_url, headers=headers)
                        response.raise_for_status()
                        projects = response.json()
                        print(f"  [调试] 搜索结果: {len(projects)} 个项目")

                        for project in projects:
                            if project["path_with_namespace"] == path:
                                return str(project["id"])

                        if projects:
                            return str(projects[0]["id"])

                    raise RuntimeError(f"未找到项目：{path}")

            return asyncio.run(fetch())

        except Exception as e:
            print(f"  [调试] 获取项目ID失败: {e}")
            return self._parse_project_id_from_url()

    def _url_encode_group_path(self, path: str) -> str:
        """URL 编码组路径。"""
        parts = path.split("/")
        encoded_parts = [quote(p, safe='') for p in parts[:-1]] + [parts[-1]]
        return "/".join(encoded_parts)

    def _parse_project_id_from_url(self) -> str:
        """从 URL 解析项目 ID（备用方案）。"""
        path = self.repo_url
        if path.startswith("http"):
            parsed = urlparse(path)
            path = parsed.path.lstrip("/")

        parts = path.split("/")
        if len(parts) >= 2:
            return path
        return parts[-1]

    # ========== 新增方法：获取远程文件内容 ==========

    def get_file_content(self, filepath: str, ref: str = "master") -> Optional[str]:
        """
        从 Git 平台获取指定文件的内容。

        Args:
            filepath: 文件路径（相对于仓库根目录）
            ref: 分支/标签名（默认：master）

        Returns:
            文件内容，如果失败返回 None
        """
        # 检查缓存
        cache_key = f"{filepath}@{ref}"
        if cache_key in self._file_cache:
            return self._file_cache[cache_key]

        try:
            if self.platform == "github":
                return self._get_github_file_content(filepath, ref)
            elif self.platform == "gitlab":
                return self._get_gitlab_file_content(filepath, ref)
        except Exception as e:
            print(f"Warning: 无法获取文件 {filepath}: {e}")

        return None

    async def get_file_content_async(self, filepath: str, ref: str = "master") -> Optional[str]:
        """异步获取文件内容。"""
        cache_key = f"{filepath}@{ref}"
        if cache_key in self._file_cache:
            return self._file_cache[cache_key]

        try:
            if self.platform == "github":
                content = await self._get_github_file_content_async(filepath, ref)
            elif self.platform == "gitlab":
                content = await self._get_gitlab_file_content_async(filepath, ref)
            else:
                return None

            if content:
                self._file_cache[cache_key] = content
            return content
        except Exception as e:
            print(f"Warning: 无法获取文件 {filepath}: {e}")
            return None

    def _get_github_file_content(self, filepath: str, ref: str) -> Optional[str]:
        """从 GitHub 获取文件内容。"""
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # GitHub raw content URL: https://raw.githubusercontent.com/owner/repo/ref/path/to/file
        url = f"{self.content_base}/{self.repo_url}/{ref}/{filepath}"

        async def fetch():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.text

        try:
            content = asyncio.run(fetch())
            self._file_cache[f"{filepath}@{ref}"] = content
            return content
        except Exception:
            return None

    async def _get_github_file_content_async(self, filepath: str, ref: str) -> Optional[str]:
        """异步从 GitHub 获取文件内容。"""
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        url = f"{self.content_base}/{self.repo_url}/{ref}/{filepath}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            content = response.text

        self._file_cache[f"{filepath}@{ref}"] = content
        return content

    def _get_gitlab_file_content(self, filepath: str, ref: str) -> Optional[str]:
        """从 GitLab 获取文件内容。"""
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json"
        }

        project_id = self._get_project_id()

        # GitLab API: GET /projects/:id/repository/files/:file_path
        url = f"{self.api_base}/projects/{project_id}/repository/files/{filepath}"
        params = {"ref": ref}

        async def fetch():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                # GitLab 返回的内容是 base64 编码的
                import base64
                return base64.b64decode(data["content"]).decode('utf-8')

        try:
            content = asyncio.run(fetch())
            self._file_cache[f"{filepath}@{ref}"] = content
            return content
        except Exception:
            return None

    async def _get_gitlab_file_content_async(self, filepath: str, ref: str) -> Optional[str]:
        """异步从 GitLab 获取文件内容。"""
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json"
        }

        project_id = self._get_project_id()

        url = f"{self.api_base}/projects/{project_id}/repository/files/{filepath}"
        params = {"ref": ref}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        import base64
        content = base64.b64decode(data["content"]).decode('utf-8')
        self._file_cache[f"{filepath}@{ref}"] = content
        return content

    # ========== 批量获取远程文件内容 ==========

    def get_multiple_files(self, filepaths: List[str], ref: str = "master") -> Dict[str, str]:
        """
        批量获取多个文件的内容。

        Args:
            filepaths: 文件路径列表
            ref: 分支/标签名

        Returns:
            {filepath: content} 字典
        """
        results = {}
        for filepath in filepaths:
            content = self.get_file_content(filepath, ref)
            if content:
                results[filepath] = content
        return results

    async def get_multiple_files_async(self, filepaths: List[str], ref: str = "master") -> Dict[str, str]:
        """异步批量获取多个文件的内容。"""
        tasks = [self.get_file_content_async(fp, ref) for fp in filepaths]
        contents = await asyncio.gather(*tasks)

        results = {}
        for filepath, content in zip(filepaths, contents):
            if content:
                results[filepath] = content
        return results

    # ========== 新增：获取仓库中的文件列表 ==========

    def list_repository_files(self, ref: str = "master", recursive: bool = True) -> List[str]:
        """
        获取仓库中的所有文件路径。

        Args:
            ref: 分支/标签名
            recursive: 是否递归获取子目录文件

        Returns:
            文件路径列表
        """
        if self.platform == "github":
            return self._get_github_tree(ref, recursive)
        elif self.platform == "gitlab":
            return self._get_gitlab_tree(ref, recursive)
        return []

    def list_python_files(self, ref: str = "master") -> List[str]:
        """
        获取仓库中的所有 Python 文件。

        Args:
            ref: 分支/标签名

        Returns:
            Python 文件路径列表
        """
        all_files = self.list_repository_files(ref, recursive=True)
        return [f for f in all_files if f.endswith('.py')]

    def _get_github_tree(self, ref: str, recursive: bool = True) -> List[str]:
        """从 GitHub 获取仓库文件列表。"""
        files = []
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        url = f"{self.api_base}/repos/{self.repo_url}/git/trees/{ref}"

        async def fetch():
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()

        try:
            data = asyncio.run(fetch())
            tree = data.get("tree", [])

            for item in tree:
                if recursive and item.get("type") == "tree":
                    # 递归获取子目录
                    sub_files = self._get_github_tree(item["path"], True)
                    files.extend(sub_files)
                elif item.get("type") == "blob":
                    files.append(item["path"])

            return files
        except Exception as e:
            print(f"Warning: 无法获取 GitHub 文件列表：{e}")
            return files

    def _get_gitlab_tree(self, ref: str, recursive: bool = True) -> List[str]:
        """从 GitLab 获取仓库文件列表。"""
        files = []
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json"
        }

        project_id = self._get_project_id()

        # GitLab API: GET /projects/:id/repository/tree
        url = f"{self.api_base}/projects/{project_id}/repository/tree"
        params = {"ref": ref, "recursive": 1 if recursive else 0}

        async def fetch():
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()

        try:
            data = asyncio.run(fetch())

            for item in data:
                if item.get("type") == "blob":
                    files.append(item["path"])
                elif recursive and item.get("type") == "directory":
                    # GitLab tree API 已经支持 recursive=true
                    pass

            return files
        except Exception as e:
            print(f"Warning: 无法获取 GitLab 文件列表：{e}")
            return files
