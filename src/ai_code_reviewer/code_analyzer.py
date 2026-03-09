"""代码分析器 - 从 diff 中提取代码元素并获取远程文件内容。"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List

try:
    from .gitlab_diff import GitDiffFetcher, FileDiff
except ImportError:
    from gitlab_diff import GitDiffFetcher, FileDiff


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


class CodeAnalyzer:
    """分析代码以提取元素并获取远程文件内容。"""

    def __init__(
        self,
        project_root: str = ".",
        fetcher: Optional[GitDiffFetcher] = None,
        ref: str = "master",
        base_ref: str = "master",
        manual_files: Optional[List[str]] = None,
        auto_fetch_all: bool = True
    ):
        """
        初始化代码分析器。

        Args:
            project_root: 本地项目根目录
            fetcher: GitDiffFetcher 实例，用于从远程获取文件
            ref: 功能分支
            base_ref: 基础分支
            manual_files: 手动指定的文件列表
            auto_fetch_all: 是否自动获取所有文件
        """
        self.project_root = Path(project_root)
        self.fetcher = fetcher
        self.ref = ref
        self.base_ref = base_ref
        self.manual_files = manual_files
        self.auto_fetch_all = auto_fetch_all

        # 缓存
        self._file_cache: Dict[str, str] = {}
        self._base_file_cache: Dict[str, str] = {}

    def get_file_content_from_branch(self, filepath: str, branch: str = None) -> Optional[str]:
        """获取指定分支的文件内容。"""
        if branch is None:
            branch = self.ref

        cache = self._file_cache if branch == self.ref else self._base_file_cache
        cache_key = f"{filepath}@{branch}"

        if cache_key in cache:
            return cache[cache_key]

        # 优先从远程获取
        if self.fetcher:
            content = self.fetcher.get_file_content(filepath, branch)
            if content:
                cache[cache_key] = content
                return content

        # 从本地读取
        file_path = self.project_root / filepath
        if file_path.exists():
            try:
                content = file_path.read_text(encoding='utf-8')
                cache[cache_key] = content
                return content
            except Exception:
                pass

        return None

    def get_file_content_both_branches(self, filepath: str) -> tuple[Optional[str], Optional[str]]:
        """获取文件在两个分支的完整内容。"""
        branch_content = self.get_file_content_from_branch(filepath, self.ref)
        base_content = self.get_file_content_from_branch(filepath, self.base_ref)
        return branch_content, base_content

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

        # 判断文件类型
        is_python = filename.endswith('.py')

        if is_python:
            # Python 文件：使用 AST 解析
            elements = self._extract_python_elements(filename, added_lines)
        else:
            # 非 Python 文件（Java, Go 等）：使用正则表达式提取
            elements = self._extract_elements_by_regex(filename, added_lines)

        return elements

    def _extract_python_elements(self, filename: str, added_lines: list[int]) -> list[CodeElement]:
        """使用 AST 提取 Python 文件的元素。"""
        elements = []

        # 获取文件内容
        file_content = self._get_file_content(filename)

        if file_content:
            try:
                tree = ast.parse(file_content)
                self._file_cache[filename] = file_content

                for line_num in added_lines:
                    element = self._find_element_at_line(tree, line_num, filename, file_content)
                    if element and element not in elements:
                        elements.append(element)
            except SyntaxError:
                pass

        return elements

    def _extract_elements_by_regex(self, filename: str, added_lines: list[int]) -> list[CodeElement]:
        """使用正则表达式提取非 Python 文件的元素（支持 Java, Go 等）。"""
        elements = []

        # 尝试获取文件内容
        file_content = self._get_file_content(filename)

        if file_content:
            self._file_cache[filename] = file_content
            lines = file_content.split('\n')

            # 查找新增行附近的类和方法定义
            for line_num in added_lines:
                # 检查附近 20 行内的类和方法定义
                start = max(0, line_num - 20)
                end = min(len(lines), line_num + 10)

                for i in range(start, end):
                    line = lines[i]
                    # Java/Go 类: public class XXX, class XXX
                    class_match = re.match(r'\s*(public\s+)?class\s+(\w+)', line)
                    if class_match:
                        elements.append(CodeElement(
                            name=class_match.group(2),
                            element_type="class",
                            filename=filename,
                            line_start=i + 1,
                            line_end=i + 2,
                            source=line
                        ))
                        continue

                    # Java 方法: public XXX returnType methodName(...)
                    method_match = re.match(r'\s*(public|private|protected)?\s+[\w<>,\s]+\s+(\w+)\s*\([^)]*\)', line)
                    if method_match and not line.strip().startswith('//') and not line.strip().startswith('/*'):
                        method_name = method_match.group(2)
                        # 排除构造函数
                        if method_name and method_name[0].islower():
                            elements.append(CodeElement(
                                name=method_name,
                                element_type="method",
                                filename=filename,
                                line_start=i + 1,
                                line_end=i + 2,
                                source=line
                            ))

        return elements

    def _get_file_content(self, filepath: str) -> Optional[str]:
        """获取文件内容，优先远程后本地。"""
        # 先检查缓存
        if filepath in self._file_cache:
            return self._file_cache[filepath]

        # 尝试从远程获取
        if self.fetcher:
            content = self.fetcher.get_file_content(filepath, self.ref)
            if content:
                self._file_cache[filepath] = content
                return content

        # 尝试从本地读取
        file_path = self.project_root / filepath
        if file_path.exists():
            content = file_path.read_text(encoding='utf-8')
            self._file_cache[filepath] = content
            return content

        return None

    def _parse_diff_added_lines(self, diff_content: str) -> list[int]:
        """从 diff 中提取新增行的行号。"""
        added_lines = []
        current_line = 0

        for line in diff_content.split("\n"):
            if line.startswith("@@"):
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
                self.current_class: Optional[str] = None

            def visit_ClassDef(self, node: ast.ClassDef):
                if node.lineno <= self.target_line <= getattr(node, "end_lineno", node.lineno):
                    self.current_class = node.name
                    self._try_update(node, "class")
                self.generic_visit(node)
                self.current_class = None

            def visit_FunctionDef(self, node: ast.FunctionDef):
                if node.lineno <= self.target_line <= getattr(node, "end_lineno", node.lineno):
                    elem_type = "method" if self.current_class else "function"
                    self._try_update(node, elem_type)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                if node.lineno <= self.target_line <= getattr(node, "end_lineno", node.lineno):
                    elem_type = "method" if self.current_class else "function"
                    self._try_update(node, elem_type)
                self.generic_visit(node)

            def _try_update(self, node, elem_type: str):
                if self.found is None or (
                    self.found.line_end - self.found.line_start >
                    getattr(node, "end_lineno", node.lineno) - node.lineno
                ):
                    source_lines = self.source.split("\n")
                    end_line = getattr(node, "end_lineno", node.lineno + 1)
                    element_source = "\n".join(
                        source_lines[node.lineno - 1:end_line]
                    )

                    self.found = CodeElement(
                        name=node.name,
                        element_type=elem_type,
                        filename=filename,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno + 1),
                        source=element_source,
                        parent_class=self.current_class
                    )

        finder = ElementFinder(line_num, source)
        finder.visit(tree)
        return finder.found
