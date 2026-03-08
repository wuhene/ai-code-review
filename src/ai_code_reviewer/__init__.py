"""AI Code Reviewer - Project-level code review powered by AI."""

from .gitlab_diff import GitDiffFetcher
from .code_analyzer import CodeAnalyzer
from .ai_reviewer import AIReviewer
from .server import app

__version__ = "0.1.0"
__all__ = ["GitDiffFetcher", "CodeAnalyzer", "AIReviewer", "app"]
