"""
代码审查应用服务 - 协调各领域服务完成审查流程。

本模块属于 Application Layer，负责：
1. 协调 Git 客户端获取 diff
2. 协调元素提取
3. 协调文件获取
4. 协调 AI 审查
5. 整合结果返回

这是核心的用例服务，将领域服务串联起来。
"""

from typing import Optional, List

from ..domain.entities import FileDiff, ReviewRequest, ReviewResult
from ..domain.services.element_extractor import ElementExtractor
from ..domain.services.ai_reviewer import AIReviewer
from ..infrastructure.git.git_factory import GitFactory


class ReviewApplicationService:
    """
    代码审查应用服务。

    这是一个应用服务（Application Service），负责协调各个领域服务完成审查流程。
    它不包含业务逻辑，只是将领域服务串联起来。
    """

    def __init__(
        self,
        platform: str,
        token: str,
        repo_url: str,
        api_key: str,
        model: str = "claude-sonnet-4-20250929",
        provider: str = "anthropic",
        base_url: Optional[str] = None,
        gitlab_url: Optional[str] = None
    ):
        """
        初始化应用服务。

        Args:
            platform: Git 平台 ('github' 或 'gitlab')
            token: Git API Token
            repo_url: 仓库地址
            api_key: LLM API Key
            model: LLM 模型
            provider: LLM 提供商
            base_url: LLM 自定义端点
            gitlab_url: GitLab 自定义地址
        """
        # Git 客户端
        self.git_client = GitFactory.create_client(
            platform=platform,
            token=token,
            repo_url=repo_url,
            base_url=gitlab_url
        )

        # LLM 客户端通过 AIReviewer 内部创建
        self.llm_api_key = api_key
        self.llm_model = model
        self.llm_provider = provider
        self.llm_base_url = base_url

    async def get_diffs(self, branch: str, base: str = "master") -> List[FileDiff]:
        """
        获取分支差异。

        Args:
            branch: 功能分支
            base: 基础分支

        Returns:
            文件差异列表
        """
        return await self.git_client.get_branch_diff(branch, base)

    def extract_elements(self, diff_content: str, filename: str) -> List:
        """
        从 diff 中提取代码元素。

        Args:
            diff_content: diff 内容
            filename: 文件名

        Returns:
            代码元素列表
        """
        return ElementExtractor.extract_from_diff(diff_content, filename)

    async def get_file_content(self, filepath: str, ref: str) -> Optional[str]:
        """
        获取文件内容。

        Args:
            filepath: 文件路径
            ref: 分支名

        Returns:
            文件内容
        """
        return await self.git_client.get_file_content(filepath, ref)

    async def get_file_both_branches(self, filepath: str, branch: str, base: str):
        """
        获取文件在两个分支的内容。

        Args:
            filepath: 文件路径
            branch: 功能分支
            base: 基础分支

        Returns:
            (功能分支内容, 基础分支内容)
        """
        branch_content = await self.git_client.get_file_content(filepath, branch)
        base_content = await self.git_client.get_file_content(filepath, base)
        return branch_content, base_content

    async def review_code(
        self,
        diffs: List[FileDiff],
        branch: str,
        base: str = "master"
    ) -> List[ReviewResult]:
        """
        审查代码变更。

        这是核心的用例方法，协调整个审查流程：
        1. 遍历每个文件的 diff
        2. 提取代码元素
        3. 获取完整文件内容
        4. 调用 AI 审查

        Args:
            diffs: 文件差异列表
            branch: 功能分支
            base: 基础分支

        Returns:
            审查结果列表
        """
        review_requests = []

        # 构建审查请求
        for file_diff in diffs:
            elements = self.extract_elements(file_diff.diff, file_diff.filename)

            if elements:
                elem = elements[0]

                # 获取文件内容
                branch_code, base_code = await self.get_file_both_branches(
                    file_diff.filename, branch, base
                )

                # 构建上下文
                context_parts = []
                context_parts.append(f"=== 功能分支 ({branch}) 完整文件 ===\n{branch_code or '(文件不存在)'}")
                if base_code:
                    context_parts.append(f"\n=== 主分支 ({base}) 完整文件 ===\n{base_code}")
                context_parts.append(f"\n=== DIFF (变更内容) ===\n{file_diff.diff}")
                context_code = "\n".join(context_parts)

                review_requests.append(ReviewRequest(
                    diff_content=file_diff.diff,
                    context_code=context_code,
                    filename=file_diff.filename,
                    element_name=elem.name,
                    element_type=elem.element_type,
                    element_line_start=elem.line_start,
                    element_line_end=elem.line_end,
                    call_chain_info=""
                ))

        # 执行 AI 审查
        if not review_requests:
            return []

        reviewer = AIReviewer(
            api_key=self.llm_api_key,
            model=self.llm_model,
            provider=self.llm_provider,
            base_url=self.llm_base_url
        )

        return reviewer.review_batch(review_requests)
