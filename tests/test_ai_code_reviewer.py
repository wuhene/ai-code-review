"""Tests for AI Code Reviewer."""

import pytest


def test_import():
    """Test that main modules can be imported."""
    from ai_code_reviewer import GitHubDiffFetcher, CodeAnalyzer, AIReviewer
    assert GitHubDiffFetcher is not None
    assert CodeAnalyzer is not None
    assert AIReviewer is not None


def test_cli_exists():
    """Test that CLI entry point exists."""
    from ai_code_reviewer.cli import main
    assert main is not None
