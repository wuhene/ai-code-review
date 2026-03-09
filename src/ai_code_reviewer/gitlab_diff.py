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
            # 优先使用用户提供的 base_url（私有 GitLab 部署时）
            if base_url:
                # 用户提供了自定义 URL，直接使用
                self.api_base = base_url.rstrip('/')
                self.content_base = base_url.rstrip('/')
            elif repo_url.startswith("http"):
                # 从 repo_url 提取域名，需要添加 /api/v4
                parsed = urlparse(repo_url)
                self.api_base = f"{parsed.scheme}://{parsed.netloc}/api/v4"
                self.content_base = f"{parsed.scheme}://{parsed.netloc}"
            else:
                # 默认使用 gitlab.com
                self.api_base = "https://gitlab.com/api/v4"
                self.content_base = "https://gitlab.com"
        else:
            raise ValueError(f"不支持的平台：{self.platform}")

        # 缓存已获取的远程文件
        self._file_cache: Dict[str, str] = {}
        # 缓存项目 ID（避免重复调用 API）
        self._cached_project_id: Optional[str] = None

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
        """从 GitHub API 获取分支差异（同步版本）。"""
        import httpx

        diffs = []

        try:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AI-Code-Reviewer"
            }

            url = f"{self.api_base}/repos/{self.repo_url}/compare/{base}...{branch}"

            with httpx.Client(timeout=60.0) as client:
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
        """从 GitLab API 获取分支差异（同步版本）。"""
        import httpx

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

            with httpx.Client(timeout=60.0) as client:
                response = client.get(url, headers=headers, params=params)
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

    async def _get_gitlab_diff_async(self, branch: str, base: str) -> list[FileDiff]:
        """异步获取 GitLab 分支差异。"""
        diffs = []

        try:
            headers = {
                "PRIVATE-TOKEN": self.token,
                "Accept": "application/json"
            }

            project_id = await self._get_project_id_async()

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

                diffs.append(FileDiff(
                    filename=filename,
                    diff=file.get("diff", ""),
                    old_path=file.get("old_path"),
                    new_path=file.get("new_path")
                ))

        except Exception as e:
            raise RuntimeError(f"从 GitLab 获取 diff 失败：{str(e)}")

        return diffs

    async def _get_project_id_async(self) -> str:
        """获取 GitLab 项目 ID（异步版本）。"""
        # 如果已经缓存，直接返回
        if self._cached_project_id:
            return self._cached_project_id

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

            print(f"  [调试] Token 前5位: {self.token[:5] if self.token else 'None'}...")
            print(f"  [调试] API URL: {self.api_base}")

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                # 方法1：直接通过编码路径获取项目
                url = f"{self.api_base}/projects/{encoded_path}"
                print(f"  [调试] 尝试获取项目: {url}")
                response = await client.get(url, headers=headers)
                print(f"  [调试] 响应状态: {response.status_code}")

                if response.status_code == 200:
                    project = response.json()
                    project_id = str(project["id"])
                    print(f"  [调试] 找到项目: {project.get('name')} (id: {project_id})")
                    self._cached_project_id = project_id
                    return project_id
                elif response.status_code == 404:
                    # 方法2：使用 search API 作为备用
                    print(f"  [调试] 直接获取失败，尝试搜索...")
                    target_path = path.rsplit("/", 1)[-1]
                    search_url = f"{self.api_base}/projects?search={target_path}"
                    response = await client.get(search_url, headers=headers)
                    print(f"  [调试] 搜索响应状态: {response.status_code}")

                    if response.status_code == 200:
                        projects = response.json()
                        print(f"  [调试] 搜索结果类型: {type(projects)}")
                        print(f"  [调试] 搜索结果: {projects}")

                        # 检查是否是正确的数组格式
                        if isinstance(projects, list):
                            for project in projects:
                                if project["path_with_namespace"] == path:
                                    project_id = str(project["id"])
                                    self._cached_project_id = project_id
                                    return project_id

                            if projects:
                                project_id = str(projects[0]["id"])
                                self._cached_project_id = project_id
                                return project_id
                        elif isinstance(projects, dict):
                            # 可能返回了错误或其他信息
                            print(f"  [调试] 搜索返回字典: {projects}")

                raise RuntimeError(f"未找到项目：{path}，状态码：{response.status_code}")

        except Exception as e:
            print(f"  [调试] 获取项目ID失败: {e}")
            return self._parse_project_id_from_url()

    def _get_project_id(self) -> str:
        """获取 GitLab 项目 ID（同步版本，内部调用异步版本）。"""
        # 如果已经缓存，直接返回
        if self._cached_project_id:
            return self._cached_project_id

        try:
            return asyncio.run(self._get_project_id_async())
        except Exception as e:
            print(f"  [调试] 同步获取项目ID失败: {e}")
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
            project_id = path
        else:
            project_id = parts[-1]

        self._cached_project_id = project_id
        return project_id

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
        """从 GitHub 获取文件内容（同步版本）。"""
        import httpx

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # GitHub raw content URL: https://raw.githubusercontent.com/owner/repo/ref/path/to/file
        url = f"{self.content_base}/{self.repo_url}/{ref}/{filepath}"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                content = response.text
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
        """从 GitLab 获取文件内容（同步版本）。"""
        import base64
        import httpx

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json"
        }

        project_id = self._get_project_id()

        # GitLab API: GET /projects/:id/repository/files/:file_path
        url = f"{self.api_base}/projects/{project_id}/repository/files/{quote(filepath, safe='')}"
        params = {"ref": ref}

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                # GitLab 返回的内容是 base64 编码的
                content = base64.b64decode(data["content"]).decode('utf-8')
                self._file_cache[f"{filepath}@{ref}"] = content
                return content
        except Exception as e:
            print(f"  [调试] 获取文件失败: {e}")
            return None

    async def _get_gitlab_file_content_async(self, filepath: str, ref: str) -> Optional[str]:
        """异步从 GitLab 获取文件内容。"""
        import base64

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json"
        }

        project_id = await self._get_project_id_async()

        url = f"{self.api_base}/projects/{project_id}/repository/files/{quote(filepath, safe='')}"
        params = {"ref": ref}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

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
        """从 GitHub 获取仓库文件列表（同步版本）。"""
        import httpx

        files = []
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

        url = f"{self.api_base}/repos/{self.repo_url}/git/trees/{ref}"

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

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
        """从 GitLab 获取仓库文件列表（同步版本）。"""
        import httpx

        files = []
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json"
        }

        project_id = self._get_project_id()

        # GitLab API: GET /projects/:id/repository/tree
        url = f"{self.api_base}/projects/{project_id}/repository/tree"
        params = {"ref": ref, "recursive": 1 if recursive else 0}

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

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
