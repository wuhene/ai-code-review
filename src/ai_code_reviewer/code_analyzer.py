"""代码分析器 - 提取代码元素并追踪引用。"""

import ast
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CodeElement:
    """表示一个代码元素（类、方法、函数）。"""
    name: str
    element_type: str  # 'class', 'method', 'function'
    filename: str
    line_start: int
    line_end: int
    source: str
    parent_class: Optional[str] = None


@dataclass
class ReferenceChain:
    """表示代码元素的引用链。"""
    element: CodeElement
    usages: list[str] = field(default_factory=list)  # 使用位置列表
    callers: list[str] = field(default_factory=list)  # 调用此元素的函数/方法
    full_context: str = ""  # 完整源代码上下文


class CodeAnalyzer:
    """分析代码以提取元素并追踪引用。"""

    def __init__(self, project_root: str):
        """
        初始化代码分析器。

        Args:
            project_root: 要分析的项目根目录
        """
        self.project_root = Path(project_root)
        self._file_cache: dict[str, str] = {}
        self._ast_cache: dict[str, ast.AST] = {}

    def extract_changed_elements(self, diff_content: str, filename: str) -> list[CodeElement]:
        """
        从 diff 内容中提取类和函数。

        Args:
            diff_content: diff 输出
            filename: 源文件路径

        Returns:
            更改代码的 CodeElement 对象列表
        """
        elements = []
        added_lines = self._parse_diff_added_lines(diff_content)

        if not added_lines:
            return elements

        # 获取完整文件内容
        file_path = self.project_root / filename
        if file_path.exists():
            full_content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(full_content)
            self._ast_cache[filename] = tree
            self._file_cache[filename] = full_content

            # 查找包含新增行的元素
            for line_num in added_lines:
                element = self._find_element_at_line(tree, line_num, filename, full_content)
                if element and element not in elements:
                    elements.append(element)
        else:
            # 新文件 - 从 diff 中提取
            elements.extend(self._extract_from_diff_new_file(diff_content, filename))

        return elements

    def _parse_diff_added_lines(self, diff_content: str) -> list[int]:
        """从 diff 中提取新增行的行号。"""
        added_lines = []
        current_line = 0

        for line in diff_content.split("\n"):
            if line.startswith("@@"):
                # 解析 hunk 头部：@@ -old_start,old_count +new_start,new_count @@
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                added_lines.append(current_line)
                current_line += 1
            elif not line.startswith("-"):
                current_line += 1

        return added_lines

    def _find_element_at_line(
        self,
        tree: ast.AST,
        line_num: int,
        filename: str,
        source: str
    ) -> Optional[CodeElement]:
        """查找包含给定行的最小代码元素。"""

        class ElementFinder(ast.NodeVisitor):
            def __init__(self, target_line: int, source_text: str):
                self.target_line = target_line
                self.source = source_text
                self.found: Optional[CodeElement] = None
                self.current_class: Optional[str] = None  # 当前所在的类名

            def visit_ClassDef(self, node: ast.ClassDef):
                if node.lineno <= self.target_line <= node.end_lineno:
                    self.current_class = node.name
                    self._try_update(node, "class")
                self.generic_visit(node)
                self.current_class = None

            def visit_FunctionDef(self, node: ast.FunctionDef):
                if node.lineno <= self.target_line <= node.end_lineno:
                    elem_type = "method" if self.current_class else "function"
                    self._try_update(node, elem_type)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                if node.lineno <= self.target_line <= node.end_lineno:
                    elem_type = "method" if self.current_class else "function"
                    self._try_update(node, elem_type)
                self.generic_visit(node)

            def _try_update(self, node, elem_type: str):
                if self.found is None or (
                    self.found.line_end - self.found.line_start >
                    node.end_lineno - node.lineno
                ):
                    source_lines = self.source.split("\n")
                    element_source = "\n".join(
                        source_lines[node.lineno - 1:node.end_lineno]
                    )

                    self.found = CodeElement(
                        name=node.name,
                        element_type=elem_type,
                        filename=filename,
                        line_start=node.lineno,
                        line_end=node.end_lineno,
                        source=element_source,
                        parent_class=self.current_class
                    )

        finder = ElementFinder(line_num, source)
        finder.visit(tree)
        return finder.found

    def _extract_from_diff_new_file(self, diff_content: str, filename: str) -> list[CodeElement]:
        """从新文件的 diff 中提取元素。"""
        elements = []
        source_lines = []

        for line in diff_content.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                source_lines.append(line[1:])
            elif not line.startswith("-") and not line.startswith("@@"):
                source_lines.append(line)

        if not source_lines:
            return elements

        source = "\n".join(source_lines)
        try:
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    elements.append(CodeElement(
                        name=node.name,
                        element_type="class",
                        filename=filename,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno + 1),
                        source=source
                    ))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    elements.append(CodeElement(
                        name=node.name,
                        element_type="function",
                        filename=filename,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno + 1),
                        source=source
                    ))
        except SyntaxError:
            pass  # 如果无法解析则跳过

        return elements

    def trace_references(self, element: CodeElement) -> ReferenceChain:
        """
        追踪项目中对该代码元素的所有引用。

        Args:
            element: 要追踪的代码元素

        Returns:
            包含所有使用位置和调用者的 ReferenceChain
        """
        chain = ReferenceChain(element=element)

        # 使用 ripgrep（快速）或 grep（备用）搜索用法
        usages = self._find_usages_ripgrep(element.name)
        chain.usages = usages

        # Get full context - read all files that reference this element
        context_files = set()
        for usage in usages:
            if ":" in usage:
                filepath = usage.rsplit(":", 1)[0]
                context_files.add(filepath)

        chain.full_context = self._build_context(element, list(context_files))

        return chain

    def _find_usages_ripgrep(self, name: str) -> list[str]:
        """使用 ripgrep 查找名称的用法。"""
        usages = []

        try:
            # 先尝试 ripgrep（更快）
            result = subprocess.run(
                ["rg", "--line-number", "--color", "never", name],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                usages = result.stdout.strip().split("\n")
                return [u for u in usages if u]
        except FileNotFoundError:
            pass

        # 备用到 grep
        try:
            result = subprocess.run(
                ["grep", "-rn", name],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                usages = result.stdout.strip().split("\n")
                return [u for u in usages if u]
        except FileNotFoundError:
            pass

        return usages

    def _build_context(
        self,
        element: CodeElement,
        context_files: list[str]
    ) -> str:
        """从引用文件构建完整上下文。"""
        context_parts = [f"=== 原文：{element.filename} ===\n{element.source}\n"]

        for filepath in context_files[:10]:  # 限制为 10 个文件
            if filepath == element.filename:
                continue

            full_path = self.project_root / filepath
            if full_path.exists():
                try:
                    content = full_path.read_text()
                    context_parts.append(f"\n=== 上下文：{filepath} ===\n{content[:2000]}")
                except Exception:
                    pass

        return "\n".join(context_parts)

    def get_full_file_context(self, filename: str) -> str:
        """获取文件的完整内容。"""
        file_path = self.project_root / filename
        if file_path.exists():
            return file_path.read_text()
        return ""
