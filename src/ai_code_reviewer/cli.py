"""AI Code Reviewer 的命令行界面。"""

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv

from .github_diff import GitHubDiffFetcher
from .code_analyzer import CodeAnalyzer
from .ai_reviewer import AIReviewer, ReviewRequest

load_dotenv()
console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """AI Code审查器 - 基于 AI 的 GitHub PR 代码审查工具。"""
    pass


@main.command()
@click.option("--branch", "-b", required=True, help="要审查的功能分支")
@click.option("--base", default="master", help="基础分支（默认为 master）")
@click.option("--repo", "-r", default=None, help="GitHub 仓库（所有者/仓库名），默认为当前目录")
@click.option("--token", "-t", default=None, help="GitHub 令牌（或设置 GITHUB_TOKEN 环境变量）")
@click.option("--api-key", default=None, help="AI API 密钥（或设置对应环境变量）")
@click.option("--model", default="claude-sonnet-4-20250929", help="要使用的 AI 模型")
@click.option("--provider", default="anthropic", help="AI 提供商（anthropic/openai/qwen/doubao/custom）")
@click.option("--base-url", default=None, help="API 基础 URL（自定义提供商时使用）")
@click.option("--project-root", default=".", help="代码分析的项目根目录")
def review(branch, base, repo, token, api_key, model, provider, base_url, project_root):
    """审查一个分支与基础分支的差异。"""

    # 验证凭证
    github_token = token or os.getenv("GITHUB_TOKEN")
    if not github_token:
        console.print("[red]Error:[/red] GitHub token required. Set GITHUB_TOKEN or use --token.")
        sys.exit(1)

    # 如果未提供，自动检测仓库名称
    if not repo:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, check=True
            )
            remote_url = result.stdout.strip()
            # 从 URL 解析 owner/repo
            if "github.com" in remote_url:
                parts = remote_url.rstrip(".git").split("/")[-2:]
                repo = "/".join(parts)
            else:
                repo = remote_url.rstrip(".git").split("/")[-2:]
                repo = "/".join(repo)
        except Exception as e:
            console.print(f"[red]检测到仓库错误:[/red] {e}")
            sys.exit(1)

    panel_text = f"Branch: {branch} vs {base} | Repo: {repo}"
    console.print(Panel(panel_text, title="[bold]AI Code Review[/bold]"))

    try:
        # 步骤 1：获取 diff
        console.print("\n[bold blue]步骤 1/3:[/bold blue] 从 GitHub 获取 diff...")
        fetcher = GitHubDiffFetcher(token=github_token, repo_name=repo, base_dir=project_root)
        diffs = fetcher.compare_branches(branch, base)
        console.print(f"  找到 [green]{len(diffs)}[/green] 个 Python 文件已更改")

        if not diffs:
            console.print("[yellow]没有 Python 文件更改。[/yellow]")
            return

        # 步骤 2：分析代码
        console.print("\n[bold blue]步骤 2/3:[/bold blue] 分析代码更改...")
        analyzer = CodeAnalyzer(project_root)

        review_requests = []
        for file_diff in diffs:
            elements = analyzer.extract_changed_elements(file_diff.diff, file_diff.new_path)
            console.print(f"  [cyan]{file_diff.filename}[/cyan]: {len(elements)} 个元素已更改")

            for element in elements:
                # 追踪引用
                chain = analyzer.trace_references(element)

                # 构建审查请求
                review_requests.append(ReviewRequest(
                    diff_content=file_diff.diff,
                    context_code=chain.full_context,
                    filename=file_diff.filename,
                    element_name=element.name,
                    element_type=element.element_type
                ))

        console.print(f"  总计：[green]{len(review_requests)}[/green] 个审查项")

        # 步骤 3：AI 审查
        console.print("\n[bold blue]步骤 3/3:[/bold blue] 发送给 AI 进行审查...")
        reviewer = AIReviewer(api_key=api_key, model=model, provider=provider, base_url=base_url)

        results = reviewer.review_batch(review_requests)

        # 显示结果
        console.print("\n[bold]审查结果[/bold]\n")

        for result in results:
            issues_count = len(result.issues)
            suggestions_count = len(result.suggestions)

            table_title = result.filename
            if result.element_name:
                table_title += f" ({result.element_name})"

            table = Table(title=table_title)
            table.add_column("方面", style="cyan")
            table.add_column("详情", style="white")

            summary_display = result.summary
            if len(result.summary) > 200:
                summary_display = result.summary[:200] + "..."
            table.add_row("摘要", summary_display)

            issues_display = f"[red]{issues_count}[/red] 个发现" if issues_count else "[green]无[/green]"
            table.add_row("问题", issues_display)

            suggestions_display = f"[yellow]{suggestions_count}[/yellow] 条建议"
            table.add_row("建议", suggestions_display)

            console.print(table)

            if result.issues:
                for issue in result.issues[:5]:  # 显示前 5 个问题
                    severity = issue.get("severity", "unknown")
                    desc = issue.get("description", "无描述")
                    color_map = {"critical": "red", "high": "red", "medium": "yellow", "low": "blue"}
                    color = color_map.get(severity, "white")
                    console.print(f"  [{color}] [{severity.upper()}] {desc}")

            console.print()

        # 摘要
        total_issues = sum(len(r.issues) for r in results)
        total_suggestions = sum(len(r.suggestions) for r in results)

        summary_panel = f"总问题数：[red]{total_issues}[/red]\n总建议数：[yellow]{total_suggestions}[/yellow]"
        console.print(Panel(summary_panel, title="[bold]审查摘要[/bold]"))

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@main.command()
def init():
    """初始化配置文件。"""
    env_path = Path(".env")

    if env_path.exists():
        console.print("[yellow].env 文件已存在。[/yellow]")
        return

    content = """# GitHub 配置
GITHUB_TOKEN=your_github_token_here

# Anthropic API 配置
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# 可选：AI 模型
AI_MODEL=claude-sonnet-4-20250929
"""
    env_path.write_text(content)
    console.print(f"[green]在 {env_path} 创建 .env 文件[/green]")
    console.print("请编辑该文件并填入你的 API 密钥。")


if __name__ == "__main__":
    main()
