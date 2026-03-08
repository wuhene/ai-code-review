"""代码分析器 - 提取代码元素并追踪引用链（支持远程代码获取）。"""

import ast
import os
import re
import subprocess
from dataclasses import dataclass, field
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


@dataclass
class CallNode:
    """表示调用链中的一个节点。"""
    element: CodeElement
    called_by: list['CallNode'] = field(default_factory=list)  # 调用此节点的上级
    calls: list['CallNode'] = field(default_factory=list)      # 此节点调用的下级


@dataclass
class ReferenceChain:
    """表示代码元素的引用链。"""
    element: CodeElement
    usages: list[str] = field(default_factory=list)  # 使用位置列表
    callers: list[str] = field(default_factory=list)  # 调用此元素的函数/方法
    call_chain: list[list[CodeElement]] = field(default_factory=list)  # 所有调用链条
    full_context: str = ""  # 完整源代码上下文


class CodeAnalyzer:
    """分析代码以提取元素并追踪引用。"""

    def __init__(
        self,
        project_root: str,
        fetcher: Optional[GitDiffFetcher] = None,
        ref: str = "master",  # 要分析的分支名
        manual_files: Optional[List[str]] = None,  # 用户手动指定的相关文件
        auto_fetch_all: bool = True  # 如果没有用户提供文件，是否自动获取全部
    ):
        """
        初始化代码分析器。

        Args:
            project_root: 本地项目根目录（用于缓存和本地搜索）
            fetcher: GitDiffFetcher 实例（用于从远程获取代码）
            ref: 要分析的分支名称
            manual_files: 用户手动指定的相关文件路径列表
            auto_fetch_all: 如果没有用户提供文件，是否自动获取全部 Python 文件
        """
        self.project_root = Path(project_root)
        self.fetcher = fetcher
        self.ref = ref
        self.manual_files = manual_files or []
        self.auto_fetch_all = auto_fetch_all

        self._file_cache: dict[str, str] = {}
        self._ast_cache: dict[str, ast.AST] = {}
        self._call_graph: Optional[dict] = None  # 调用图缓存
        self._all_functions: List[tuple] = []  # 所有函数信息

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

        # 优先从远程获取文件内容
        file_content = self._get_file_content(filename)

        if file_content:
            try:
                tree = ast.parse(file_content)
                self._ast_cache[filename] = tree
                self._file_cache[filename] = file_content

                for line_num in added_lines:
                    element = self._find_element_at_line(tree, line_num, filename, file_content)
                    if element and element not in elements:
                        elements.append(element)
            except SyntaxError:
                pass
        else:
            # 如果无法获取，尝试从 diff 中提取
            elements.extend(self._extract_from_diff_new_file(diff_content, filename))

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
            pass

        return elements

    def trace_references(self, element: CodeElement) -> ReferenceChain:
        """
        追踪项目中对该代码元素的所有引用及调用链。

        Args:
            element: 要追踪的代码元素

        Returns:
            包含所有使用位置、调用者和调用链的 ReferenceChain
        """
        chain = ReferenceChain(element=element)

        # 1. 使用 ripgrep 查找名称的用法（本地）
        usages = self._find_usages_ripgrep(element.name)
        chain.usages = usages

        # 2. 构建完整的调用图并获取调用链（从远程）
        call_chain_results = self._build_call_chain(element)
        chain.callers = call_chain_results['callers']
        chain.call_chain = call_chain_results['full_chains']

        # 3. 获取完整上下文
        context_files = set()
        for usage in usages:
            if ":" in usage:
                filepath = usage.rsplit(":", 1)[0]
                context_files.add(filepath)

        # 将所有相关节点的文件加入上下文
        for full_chain in chain.call_chain:
            for node in full_chain:
                context_files.add(node.filename)

        chain.full_context = self._build_context(element, list(context_files))

        return chain

    def _build_python_call_graph(self) -> tuple[dict, list]:
        """
        构建整个项目的函数调用图（从远程获取）。

        Returns:
            (graph, all_functions)
            - graph: {(file, function): [called_function_names]}
            - all_functions: [(file, func_name, lineno), ...]
        """
        if self._call_graph is not None:
            return self._call_graph, self._all_functions

        graph = {}  # {(file, function): [called_functions]}
        all_functions = []  # [(file, func_name, lineno)]

        if not self.fetcher:
            # 如果没有 fetcher，尝试从本地分析
            return self._build_local_call_graph()

        # 首先获取已更改的文件列表
        # 这里我们简化处理：假设我们知道所有相关文件
        # 实际应该通过某种方式获取项目中的 Python 文件列表

        # 方法：从 usages 中收集所有涉及的文件，然后逐一获取
        # 这是一个简化版本，实际可能需要更复杂的逻辑

        # 对于每个可能的文件，我们需要知道它的存在
        # 这里我们先用一个启发式方法：从已经遇到的文件中推断

        # 由于我们无法轻易列出仓库中的所有文件，我们采用另一种策略：
        # 在调用时传入需要分析的文件列表

        return graph, all_functions

    def _build_local_call_graph(self) -> tuple[dict, list]:
        """从本地构建调用图（作为备用方案）。"""
        graph = {}
        all_functions = []

        python_files = list(self.project_root.rglob("*.py"))
        for py_file in python_files:
            rel_path = str(py_file.relative_to(self.project_root))
            try:
                content = py_file.read_text(encoding='utf-8')
                tree = ast.parse(content)

                file_calls = {}
                file_funcs = []

                class CallVisitor(ast.NodeVisitor):
                    def __init__(self):
                        self.current_func = None
                        self.calls = set()

                    def visit_FunctionDef(self, node):
                        old_func = self.current_func
                        self.current_func = node.name
                        self.generic_visit(node)
                        file_calls[(node.lineno, node.name)] = sorted(self.calls)
                        self.calls.clear()
                        self.current_func = old_func

                    def visit_AsyncFunctionDef(self, node):
                        old_func = self.current_func
                        self.current_func = f"async {node.name}"
                        self.generic_visit(node)
                        file_calls[(node.lineno, node.name)] = sorted(self.calls)
                        self.calls.clear()
                        self.current_func = old_func

                    def visit_Call(self, node):
                        if self.current_func:
                            called = self._get_called_name(node)
                            if called:
                                self.calls.add(called)
                        self.generic_visit(node)

                    def _get_called_name(self, node) -> Optional[str]:
                        if isinstance(node.func, ast.Name):
                            return node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            return node.func.attr
                        return None

                visitor = CallVisitor()
                visitor.visit(tree)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        all_functions.append((rel_path, node.name, node.lineno))
                    elif isinstance(node, ast.AsyncFunctionDef):
                        all_functions.append((rel_path, f"async {node.name}", node.lineno))

                for key, calls in file_calls.items():
                    if (rel_path, key[1]) not in graph:
                        graph[(rel_path, key[1])] = []
                    graph[(rel_path, key[1])] = calls

            except Exception as e:
                print(f"Warning: 无法解析文件 {rel_path}: {e}")

        self._call_graph = graph
        self._all_functions = all_functions
        return graph, all_functions

    def analyze_call_chain_from_files(self, elements: List[CodeElement]) -> dict[str, ReferenceChain]:
        """
        分析一组代码元素的调用链（批量处理）。

        Args:
            elements: 代码元素列表

        Returns:
            {element_key: ReferenceChain}
        """
        results = {}

        # 收集所有需要获取内容的文件
        files_to_fetch = set()
        for elem in elements:
            files_to_fetch.add(elem.filename)

            # 还要获取可能相关的其他文件
            usages = self._find_usages_ripgrep(elem.name)
            for usage in usages:
                if ":" in usage:
                    filepath = usage.rsplit(":", 1)[0]
                    files_to_fetch.add(filepath)

        # 批量获取文件内容
        if self.fetcher:
            file_contents = self.fetcher.get_multiple_files(list(files_to_fetch), self.ref)
            self._file_cache.update(file_contents)

        # 为每个元素构建调用链
        for elem in elements:
            chain = self.trace_references(elem)
            results[f"{elem.filename}:{elem.name}"] = chain

        return results

    def _build_call_chain(self, target_element: CodeElement) -> dict:
        """
        从目标元素向上追溯完整的调用链（谁调用了它）。

        Args:
            target_element: 被修改的目标代码元素

        Returns:
            {
                'callers': ['A#method1', 'B#method2'],
                'full_chains': [[C#m3, B#m2, A#m1]]
            }
        """
        # 先尝试从本地构建调用图
        graph, all_functions = self._build_local_call_graph()

        # 如果没有找到调用图，尝试从远程获取
        if not graph and self.fetcher:
            graph, all_functions = self._build_remote_call_graph(target_element)

        # 创建函数名到信息的映射
        func_map = {}
        for file, name, lineno in all_functions:
            key = f"{file}:{name}@{lineno}"
            func_map[key] = {'file': file, 'name': name, 'line': lineno}

        result_key = f"{target_element.filename}:{target_element.name}@{target_element.line_start}"

        callers = []
        full_chains = []

        def find_callers(node_key, visited=None):
            """递归查找所有调用者（向上追溯）"""
            if visited is None:
                visited = set()

            if node_key in visited:
                return []

            visited.add(node_key)
            caller_list = []

            for (file, func), called_funcs in graph.items():
                if target_element.name in called_funcs or func == target_element.name:
                    caller_key = f"{file}:{func}"
                    if caller_key != node_key and caller_key not in visited:
                        caller_info = func_map.get(caller_key)
                        if caller_info:
                            caller_node = CodeElement(
                                name=caller_info['name'],
                                element_type='method' if '.' in caller_key else 'function',
                                filename=caller_info['file'],
                                line_start=caller_info['line'],
                                line_end=caller_info['line'] + 1,
                                source=f"def {caller_info['name']}(...)",
                                parent_class=None
                            )
                            caller_list.append(caller_node)

                            sub_callers = find_callers(caller_key, visited.copy())
                            if sub_callers:
                                caller_node.called_by.extend(sub_callers)

            return caller_list

        direct_callers = find_callers(result_key)

        def collect_chains(node: CodeElement, path: list[CodeElement] = None):
            if path is None:
                path = [node]

            if not node.called_by:
                full_chains.append(list(reversed(path)))
            else:
                for caller in node.called_by:
                    collect_chains(caller, path + [caller])

        if direct_callers:
            target_node = CallNode(element=target_element)
            for caller in direct_callers:
                target_node.called_by.append(CallNode(element=caller))
            collect_chains(target_node.element)

            for caller in direct_callers:
                callers.append(f"{caller.filename}#{caller.name}")

        if not full_chains:
            full_chains = [[target_element]]

        return {
            'callers': list(set(callers)),
            'full_chains': full_chains
        }

    def _build_remote_call_graph(self, target_element: CodeElement) -> tuple[dict, list]:
        """
        从远程构建完整的调用图。

        策略：
        1. 如果用户提供了手动文件列表，优先下载这些文件
        2. 如果没有用户提供文件或调用图不完整，则获取全部 Python 文件

        Returns:
            (graph, all_functions)
        """
        if not self.fetcher:
            return {}, []

        files_to_fetch = []

        # 优先使用用户手动指定的文件
        if self.manual_files:
            print(f"  [优化] 使用用户提供的 {len(self.manual_files)} 个相关文件...")
            files_to_fetch = self.manual_files.copy()

            # 同时添加目标文件本身
            if target_element.filename not in files_to_fetch:
                files_to_fetch.append(target_element.filename)

            # 批量获取用户指定的文件内容
            print(f"  [下载] 获取用户指定的文件内容...")
            file_contents = self.fetcher.get_multiple_files(files_to_fetch, self.ref)

            print(f"  [成功] 获取到 {len(file_contents)} 个文件")

            # 分析这些文件构建调用图
            graph, all_functions = self._analyze_files_content(file_contents)

            # 检查是否覆盖到了被修改的函数
            target_key = f"{target_element.filename}:{target_element.name}"
            covered = any(target_key in f"{f}:{n}" for f, n, _ in all_functions)

            if not covered:
                print(f"  [警告] 用户提供的文件未包含目标函数，尝试获取完整项目...")
            elif self.auto_fetch_all and len(file_contents) < 100:
                print(f"  [提示] 文件数量较少 ({len(file_contents)}), 建议开启 '自动获取全部' 以获取更完整的调用链")

            return graph, all_functions

        # 如果没有用户提供文件，自动获取全部 Python 文件
        print(f"  [自动] 用户未提供文件列表，获取仓库中所有 Python 文件...")

        try:
            python_files = self.fetcher.list_python_files(self.ref)
            print(f"  [找到] 共 {len(python_files)} 个 Python 文件")
        except Exception as e:
            print(f"Warning: 无法获取文件列表：{e}")
            return self._build_local_call_graph()

        if not python_files:
            return {}, []

        # 批量下载文件内容
        print(f"  [下载] 获取 {len(python_files)} 个文件内容...")
        file_contents = self.fetcher.get_multiple_files(python_files, self.ref)

        if not file_contents:
            return {}, []

        print(f"  [成功] 成功下载 {len(file_contents)} 个文件")

        # 构建调用图
        return self._analyze_files_content(file_contents)

    def _analyze_files_content(self, file_contents: Dict[str, str]) -> tuple[dict, list]:
        """
        分析已获取的文件内容，构建调用图。

        Args:
            file_contents: {filepath: content} 字典

        Returns:
            (graph, all_functions)
        """
        graph = {}
        all_functions = []

        for filepath, content in file_contents.items():
            try:
                tree = ast.parse(content)

                file_calls = {}

                class CallVisitor(ast.NodeVisitor):
                    def __init__(self):
                        self.current_func = None
                        self.calls = set()

                    def visit_FunctionDef(self, node):
                        old_func = self.current_func
                        self.current_func = node.name
                        self.generic_visit(node)
                        file_calls[(node.lineno, node.name)] = sorted(self.calls)
                        self.calls.clear()
                        self.current_func = old_func

                    def visit_AsyncFunctionDef(self, node):
                        old_func = self.current_func
                        self.current_func = f"async {node.name}"
                        self.generic_visit(node)
                        file_calls[(node.lineno, node.name)] = sorted(self.calls)
                        self.calls.clear()
                        self.current_func = old_func

                    def visit_Call(self, node):
                        if self.current_func:
                            called = self._get_called_name(node)
                            if called:
                                self.calls.add(called)
                        self.generic_visit(node)

                    def _get_called_name(self, node) -> Optional[str]:
                        if isinstance(node.func, ast.Name):
                            return node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            return node.func.attr
                        return None

                visitor = CallVisitor()
                visitor.visit(tree)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        all_functions.append((filepath, node.name, node.lineno))
                    elif isinstance(node, ast.AsyncFunctionDef):
                        all_functions.append((filepath, f"async {node.name}", node.lineno))

                for key, calls in file_calls.items():
                    if (filepath, key[1]) not in graph:
                        graph[(filepath, key[1])] = []
                    graph[(filepath, key[1])] = calls

            except Exception as e:
                print(f"Warning: 无法分析文件 {filepath}: {e}")

        return graph, all_functions

    def _find_usages_ripgrep(self, name: str) -> list[str]:
        """使用 ripgrep 查找名称的用法。"""
        usages = []

        try:
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

    def _get_called_name(self, node) -> Optional[str]:
        """从 AST 节点获取被调用的函数名。"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None

    def _build_context(
        self,
        element: CodeElement,
        context_files: list[str]
    ) -> str:
        """从引用文件构建完整上下文。"""
        context_parts = [f"=== 原文：{element.filename} ===\n{element.source}\n"]

        for filepath in context_files[:10]:
            if filepath == element.filename:
                continue

            # 优先从远程获取
            if self.fetcher:
                content = self.fetcher.get_file_content(filepath, self.ref)
                if content:
                    context_parts.append(f"\n=== 上下文：{filepath} ===\n{content[:2000]}")
                    continue

            # 尝试本地
            full_path = self.project_root / filepath
            if full_path.exists():
                try:
                    content = full_path.read_text()
                    context_parts.append(f"\n=== 上下文：{filepath} ===\n{content[:2000]}")
                except Exception:
                    pass

        return "\n".join(context_parts)
