"""
代码元素提取器 - 从 diff 中提取代码变更的元素信息。

主要用途：
- 从 git diff 中提取变更的类名、方法名
- 用于定位需要审查的代码范围
- 后续可据此获取完整的类文件发给 AI 审查
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List


@dataclass
class CodeElement:
    """表示一个代码元素（类、方法、函数）。"""
    name: str  # 元素名称（类名或方法名）
    element_type: str  # 'class', 'method', 'function'
    filename: str  # 文件名
    line_start: int  # 起始行号
    line_end: int  # 结束行号
    source: str  # 源代码片段
    parent_class: Optional[str] = None  # 所属类（如果是方法）


class ElementExtractor:
    """
    从 diff 或源代码中提取代码元素的工具类。

    职责：
    1. 根据文件类型选择提取策略（Python 用 AST，其他用正则）
    2. 从 diff 中提取变更的类名、方法名
    3. 返回元素列表供后续使用（如获取完整文件）
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
        # diff 格式 +++: b/trade-application/src/main/java/.../HouseDataLoader.java
        class_name = None
        for line in diff_content.split("\n"):
            if line.startswith("+++ b/") or line.startswith("--- a/"):
                # 取最后一段路径
                path_part = line.split("/", 1)[-1].strip()
                if path_part:
                    # 去掉后缀得到类名
                    if path_part.endswith(".java"):
                        class_name = path_part[:-5]  # 去掉 .java
                    elif path_part.endswith(".go"):
                        class_name = path_part[:-3]  # 去掉 .go
                    else:
                        class_name = path_part
                    break

        # 添加类名到结果
        if class_name:
            elements.append(CodeElement(
                name=class_name,
                element_type="class",
                filename=filename,
                line_start=0,  # Java 无法从 diff 准确获取行号
                line_end=0,
                source=f"class {class_name}"
            ))
            seen.add(f"class:{class_name}")

        # ====== 步骤2: 从新增行提取方法 ======
        # 遍历 diff 的每一行
        for line in diff_content.split("\n"):
            # 只处理新增的行（以 + 开头，但不是 +++）
            if not line.startswith("+") or line.startswith("+++"):
                continue

            # 去掉 + 前缀得到实际代码
            stripped = line.lstrip("+ ")

            # 跳过空行和注释
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # 用正则匹配方法定义
            # 匹配: public void methodName(...) 或 private static final String getName() 等
            method_match = re.match(
                r'(public|private|protected)?\s+(static\s+)?(final\s+)?'
                r'([\w<>\[\],\s]+?)\s+(\w+)\s*\([^)]*\)\s*(throws\s+\w+)?',
                stripped
            )

            if method_match:
                # group(4) 是返回类型，group(5) 是方法名
                return_type = method_match.group(4).strip()
                method_name = method_match.group(5)

                # 排除常见非业务方法（getter/setter/equals等）
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
        """
        从 diff 中提取新增行的行号。

        解析 diff 的 @@ -93,6 +93,10 @@ 格式，提取新增行的行号。

        Args:
            diff_content: git diff 内容

        Returns:
            新增行的行号列表
        """
        added_lines = []
        current_line = 0

        for line in diff_content.split("\n"):
            # @@ -93,6 +93,10 @@ 表示从第93行开始，新增6行变成10行
            if line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_line = int(match.group(1))
            # + 开头的是新增行（但 +++ 是文件路径，不是代码）
            elif line.startswith("+") and not line.startswith("+++"):
                added_lines.append(current_line)
                current_line += 1
            # - 开头是删除行，其他是上下文
            elif not line.startswith("-"):
                current_line += 1

        return added_lines

    @staticmethod
    def _extract_added_code(diff_content: str) -> Optional[str]:
        """
        从 diff 中提取新增的代码（去掉 + 前缀）。

        用于将 diff 转换为可被 AST 解析的代码。

        Args:
            diff_content: git diff 内容

        Returns:
            新增的代码字符串，如果无新增则返回 None
        """
        lines = []
        for line in diff_content.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                # 去掉 + 前缀
                lines.append(line[1:])
            elif not line.startswith("@@") and not line.startswith("-"):
                # 保留上下文行（让代码更完整）
                lines.append(line)

        return "\n".join(lines) if lines else None
