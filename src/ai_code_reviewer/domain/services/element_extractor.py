"""
代码元素提取器 - 领域服务。

职责：
1. 根据文件类型选择提取策略（Python 用 AST，其他用正则）
2. 从 diff 中提取变更的类名、方法名
3. 返回元素列表供后续使用

本模块属于 Domain Layer，不依赖任何外部基础设施。
"""

import ast
import re
from typing import List

from ..entities import CodeElement


class ElementExtractor:
    """
    代码元素提取领域服务。

    这是一个无状态的服务类，负责从 diff 内容中提取代码变更元素。
    """

    @staticmethod
    def extract_from_diff(diff_content: str, filename: str) -> List[CodeElement]:
        """
        入口方法：根据文件类型提取 diff 中的代码元素。

        Args:
            diff_content: git diff 内容
            filename: 变更的文件名

        Returns:
            代码元素列表（通常包含类名，可能包含方法名）
        """
        is_python = filename.endswith('.py')

        if is_python:
            return ElementExtractor._extract_python_from_diff(diff_content, filename)
        else:
            return ElementExtractor._extract_java_from_diff(diff_content, filename)

    @staticmethod
    def _extract_python_from_diff(diff_content: str, filename: str) -> List[CodeElement]:
        """
        从 Python diff 中提取元素。

        原理：
        1. 从 diff 中提取新增代码行
        2. 用 AST 解析新增代码
        3. 识别 ClassDef、FunctionDef 等节点

        Args:
            diff_content: git diff 内容
            filename: 文件名

        Returns:
            包含的类名和函数名列表
        """
        elements = []

        # 解析 diff 获取新增行号
        added_lines = ElementExtractor._parse_diff_lines(diff_content)
        if not added_lines:
            return elements

        # 提取新增代码（去掉 + 前缀）
        new_code = ElementExtractor._extract_added_code(diff_content)
        if not new_code:
            return elements

        # 用 AST 解析 Python 代码
        try:
            tree = ast.parse(new_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    elements.append(CodeElement(
                        name=node.name,
                        element_type="class",
                        filename=filename,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno + 1),
                        source=ast.get_source_segment(new_code, node) or ""
                    ))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    elements.append(CodeElement(
                        name=node.name,
                        element_type="function",
                        filename=filename,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno + 1),
                        source=ast.get_source_segment(new_code, node) or ""
                    ))
        except SyntaxError:
            # 解析失败返回空列表
            pass

        return elements

    @staticmethod
    def _extract_java_from_diff(diff_content: str, filename: str) -> List[CodeElement]:
        """
        从 Java/Go diff 中提取元素。

        原理：
        1. 从 diff 头部 "+++ b/.../XXX.java" 提取类名
        2. 遍历新增行（+ 开头），用正则匹配方法定义

        Args:
            diff_content: git diff 内容
            filename: 文件名

        Returns:
            包含的类名和方法名列表
        """
        elements = []
        seen = set()  # 用于去重

        # ====== 步骤1: 从 diff 头部提取类名 ======
        class_name = None
        for line in diff_content.split("\n"):
            if line.startswith("+++ b/") or line.startswith("--- a/"):
                path_part = line.split("/", 1)[-1].strip()
                if path_part:
                    if path_part.endswith(".java"):
                        class_name = path_part[:-5]
                    elif path_part.endswith(".go"):
                        class_name = path_part[:-3]
                    else:
                        class_name = path_part
                    break

        if class_name:
            elements.append(CodeElement(
                name=class_name,
                element_type="class",
                filename=filename,
                line_start=0,
                line_end=0,
                source=f"class {class_name}"
            ))
            seen.add(f"class:{class_name}")

        # ====== 步骤2: 从新增行提取方法 ======
        for line in diff_content.split("\n"):
            if not line.startswith("+") or line.startswith("+++"):
                continue

            stripped = line.lstrip("+ ")

            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            method_match = re.match(
                r'(public|private|protected)?\s+(static\s+)?(final\s+)?'
                r'([\w<>\[\],\s]+?)\s+(\w+)\s*\([^)]*\)\s*(throws\s+\w+)?',
                stripped
            )

            if method_match:
                return_type = method_match.group(4).strip()
                method_name = method_match.group(5)

                if method_name and method_name[0].islower() and method_name not in ('get', 'set', 'toString', 'hashCode', 'equals', 'main'):
                    key = f"method:{method_name}"
                    if key not in seen:
                        seen.add(key)
                        elements.append(CodeElement(
                            name=method_name,
                            element_type="method",
                            filename=filename,
                            line_start=0,
                            line_end=0,
                            source=stripped[:150]
                        ))

        return elements

    @staticmethod
    def _parse_diff_lines(diff_content: str) -> List[int]:
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

    @staticmethod
    def _extract_added_code(diff_content: str) -> str:
        """从 diff 中提取新增的代码（去掉 + 前缀）。"""
        lines = []
        for line in diff_content.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(line[1:])
            elif not line.startswith("@@") and not line.startswith("-"):
                lines.append(line)

        return "\n".join(lines) if lines else ""
