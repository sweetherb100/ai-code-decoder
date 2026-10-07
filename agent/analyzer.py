"""Static Python AST analysis. User code is parsed but never executed."""

from __future__ import annotations

import ast
import builtins

from agent.models import CodeAnalysis, LearningTarget


class CodeAnalysisError(ValueError):
    """Raised when Python source cannot be parsed or is too large."""


MAX_CODE_CHARACTERS = 20_000


def _attribute_parts(node: ast.AST) -> list[str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return list(reversed(parts))


def analyze_code(code: str, surrounding_context: str = "") -> CodeAnalysis:
    """Extract imports, calls, syntax, and learning targets without executing code."""
    if len(code) + len(surrounding_context) > MAX_CODE_CHARACTERS:
        raise CodeAnalysisError(
            f"코드가 너무 깁니다. {MAX_CODE_CHARACTERS:,}자 이하로 입력해 주세요."
        )
    try:
        code_tree = ast.parse(code)
    except SyntaxError as exc:
        location = f"{exc.lineno}행" if exc.lineno else "위치 미상"
        raise CodeAnalysisError(f"Python 문법 오류 ({location}): {exc.msg}") from exc
    trees = [code_tree]
    if surrounding_context.strip():
        try:
            trees.append(ast.parse(surrounding_context))
        except SyntaxError as exc:
            location = f"{exc.lineno}행" if exc.lineno else "위치 미상"
            raise CodeAnalysisError(
                f"주변 코드의 Python 문법 오류 ({location}): {exc.msg}"
            ) from exc
    tree = ast.Module(
        body=[statement for parsed in trees for statement in parsed.body],
        type_ignores=[item for parsed in trees for item in parsed.type_ignores],
    )

    imports: list[str] = []
    imported_names: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                local_name = alias.asname or alias.name.split(".")[0]
                imported_names[local_name] = (alias.name, None)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
            for alias in node.names:
                if alias.name != "*":
                    imported_names[alias.asname or alias.name] = (module, alias.name)

    targets: dict[tuple[str, str, str], LearningTarget] = {}

    # Infer a small number of common Path variables from assignments such as
    # IMAGES_DIR = Path("images"). This lets a later IMAGES_DIR.glob(...) call
    # resolve to the official pathlib documentation without executing the code.
    variable_types: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        parts = _attribute_parts(value.func)
        if not parts:
            continue
        imported = imported_names.get(parts[0])
        if not imported:
            continue
        module, imported_symbol = imported
        if imported_symbol == "Path" or (not imported_symbol and parts[-1] == "Path"):
            assigned_value = (module, "Path")
            destinations = node.targets if isinstance(node, ast.Assign) else [node.target]
            for destination in destinations:
                if isinstance(destination, ast.Name):
                    variable_types[destination.id] = assigned_value

    def add_target(name: str, kind: str, module: str, symbol: str) -> None:
        key = (name, module, symbol)
        targets.setdefault(
            key,
            LearningTarget(name=name, kind=kind, module=module, symbol=symbol),
        )

    call_names: list[str] = []
    has_fstring = False
    has_comprehension = False
    has_async = False
    has_unpacking = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            parts = _attribute_parts(node.func)
            if not parts:
                continue
            call_names.append(".".join(parts))
            root = parts[0]
            if root in imported_names:
                module, imported_symbol = imported_names[root]
                if imported_symbol:
                    suffix = ".".join(parts[1:])
                    symbol = ".".join([imported_symbol, suffix]).strip(".")
                else:
                    module_parts = module.split(".")
                    consumed = (
                        len(module_parts)
                        if parts[: len(module_parts)] == module_parts
                        else 1
                    )
                    symbol = ".".join(parts[consumed:]) or module.rsplit(".", 1)[-1]
                add_target(".".join(parts), "method" if len(parts) > 1 else "function", module, symbol)
            elif root in variable_types and len(parts) > 1:
                module, type_name = variable_types[root]
                symbol = ".".join([type_name, *parts[1:]])
                add_target(".".join(parts), "method", module, symbol)
            elif callable(getattr(builtins, root, None)):
                symbol = ".".join(parts)
                add_target(".".join(parts), "function" if len(parts) == 1 else "method", "builtins", symbol)
            elif len(parts) > 1 and parts[0][0:1].isupper():
                # Best-effort resolution for common imported type calls such as Path.glob.
                add_target(".".join(parts), "method", "", ".".join(parts[1:]))
            else:
                add_target(".".join(parts), "function", "", ".".join(parts))
        elif isinstance(node, ast.JoinedStr):
            has_fstring = True
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            has_comprehension = True
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            has_async = True
        elif isinstance(node, (ast.Starred,)):
            has_unpacking = True

    syntax: list[str] = []
    if has_fstring:
        syntax.append("f-string")
    if has_comprehension:
        syntax.append("comprehension")
    if has_async:
        syntax.append("async/await")
    if has_unpacking:
        syntax.append("unpacking with *")

    notes: list[str] = []
    if not targets and not syntax and not imports:
        notes.append("No calls, imports, or tracked syntax forms were found.")

    return CodeAnalysis(
        imports=sorted(set(imports)),
        functions=sorted(set(call_names)),
        syntax=syntax,
        learning_targets=list(targets.values()),
        notes=notes,
    )
