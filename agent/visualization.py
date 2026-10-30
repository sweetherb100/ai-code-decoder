"""Read-only source relationships for the learning interface; never evaluate code."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from html import escape

from agent.models import CodeAnalysis, LearningPlan, LearningTarget


@dataclass(frozen=True)
class CodeStep:
    """A statement and its location, independent of official API support."""

    label: str
    line: int
    end_line: int


@dataclass(frozen=True)
class CodeMap:
    steps: tuple[CodeStep, ...]
    dot: str
    omitted: int


def build_code_map(code: str, selected: int = 0) -> CodeMap:
    """Draw statement order and nested blocks, never a claimed execution trace."""
    tree = ast.parse(code)
    steps: list[CodeStep] = []
    edges: list[tuple[int, int, str]] = []
    limit = 16

    def snippet(node: ast.AST) -> str:
        return ' '.join((ast.get_source_segment(code, node) or ast.unparse(node)).split())[:48]

    def label(node: ast.stmt) -> str:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return '함수 정의 · ' + node.name
        if isinstance(node, ast.ClassDef):
            return '클래스 정의 · ' + node.name
        if isinstance(node, ast.If):
            return '조건 · ' + snippet(node.test)
        if isinstance(node, (ast.For, ast.AsyncFor)):
            return '반복 · ' + snippet(node.target) + ' in ' + snippet(node.iter)
        if isinstance(node, ast.While):
            return '반복 조건 · ' + snippet(node.test)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return '가져오기 · ' + snippet(node)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            return '저장 · ' + snippet(node)
        if isinstance(node, ast.Return):
            return '반환 · ' + (snippet(node.value) if node.value else 'None')
        if isinstance(node, (ast.Try, ast.TryStar)):
            return '예외 처리'
        return snippet(node)

    def visit_block(body: list[ast.stmt], parent: int | None = None, relation: str = '') -> None:
        previous = None
        for node in body:
            if len(steps) >= limit:
                return
            index = len(steps)
            steps.append(CodeStep(label(node), node.lineno, node.end_lineno or node.lineno))
            if previous is not None:
                edges.append((previous, index, '다음 문장'))
            elif parent is not None:
                edges.append((parent, index, relation))
            previous = index
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit_block(node.body, index, '함수 본문 · 호출 시')
            elif isinstance(node, ast.ClassDef):
                visit_block(node.body, index, '클래스 본문')
            elif isinstance(node, ast.If):
                visit_block(node.body, index, '참일 때')
                visit_block(node.orelse, index, '거짓일 때')
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                visit_block(node.body, index, '반복 본문')
                visit_block(node.orelse, index, '중단 없이 종료 시')
            elif isinstance(node, (ast.Try, ast.TryStar)):
                visit_block(node.body, index, '시도')
                for handler in node.handlers:
                    visit_block(handler.body, index, '예외 · ' + (snippet(handler.type) if handler.type else '전체'))
                visit_block(node.orelse, index, '예외 없을 때')
                visit_block(node.finalbody, index, '마무리')
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                visit_block(node.body, index, '블록 본문')
            elif isinstance(node, ast.Match):
                for case in node.cases:
                    visit_block(case.body, index, '패턴 · ' + snippet(case.pattern))

    visit_block(tree.body)
    total = sum(isinstance(node, ast.stmt) for node in ast.walk(tree))
    dot = ['digraph code {', 'graph [rankdir=TB bgcolor="transparent" nodesep=0.25 ranksep=0.3];',
           'node [shape=box style="rounded,filled" fontname="sans-serif" fontsize=12 color="#c9d1de" margin="0.16,0.10"];',
           'edge [color="#8a94a6" fontname="sans-serif" fontsize=9 fontcolor="#5b6577"];']
    for i, step in enumerate(steps):
        title = f'{i + 1}. {step.label}\n{step.line}행'
        color = '#e6ecfa' if i == selected else '#ffffff'
        dot.append(f'n{i} [label={json.dumps(title, ensure_ascii=False)} fillcolor="{color}"];')
    for source, target, text in edges:
        dot.append(f'n{source} -> n{target} [label={json.dumps(text, ensure_ascii=False)}];')
    dot.append('}')
    return CodeMap(tuple(steps), '\n'.join(dot), max(0, total - len(steps)))


@dataclass(frozen=True)
class CallConnections:
    """Source expressions, not runtime values or a predicted execution trace."""

    inputs: tuple[str, ...]
    output: str


def learning_targets(analysis: CodeAnalysis, plan: LearningPlan) -> list[LearningTarget]:
    """Show planned targets first, preserving unresolved targets for exploration."""
    by_id = {target.target_id: target for target in analysis.learning_targets}
    selected = [by_id[item.target_id] for item in sorted(
        plan.primary_targets, key=lambda item: item.explanation_order
    ) if item.target_id in by_id]
    selected_ids = {target.target_id for target in selected}
    return selected + [t for t in analysis.learning_targets if t.target_id not in selected_ids]


def highlighted_code(source: str, target: LearningTarget | None) -> str:
    """Escape submitted text before adding trusted line-number markup."""
    lines = []
    for number, line in enumerate(source.splitlines(), start=1):
        selected = bool(target and target.line and
                        target.line <= number <= (target.end_line or target.line))
        style = 'code-line selected' if selected else 'code-line'
        lines.append(
            f'<span class="{style}"><span class="line-number">{number}</span>'
            f'{escape(line)}</span>'
        )
    return '<div class="source-code">' + ''.join(lines) + '</div>'


def call_connections(
    code: str, context: str, target: LearningTarget
) -> CallConnections | None:
    """Describe a selected call's explicit arguments and its direct parent only."""
    source = context if target.source == 'surrounding_context' else code
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    call = next((node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and node.lineno == target.line
                 and ast.get_source_segment(source, node) == target.expression), None)
    if call is None:
        return None

    def segment(node: ast.AST) -> str:
        return ast.get_source_segment(source, node) or ast.unparse(node)

    inputs = [segment(arg) for arg in call.args]
    inputs.extend((f'{kw.arg}=' if kw.arg else '**') + segment(kw.value) for kw in call.keywords)
    # An attribute receiver is also an explicit input, but its value is unknown.
    if isinstance(call.func, ast.Attribute):
        inputs.insert(0, '호출 대상: ' + segment(call.func.value))
    parent = parents.get(id(call))
    if isinstance(parent, ast.keyword):
        parent = parents.get(id(parent))
    if isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is call:
        destinations = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
        output = ', '.join(segment(item) for item in destinations) + '에 대입'
    elif isinstance(parent, ast.Call) and parent.func is not call:
        output = segment(parent.func) + '(...)의 인자로 전달'
    elif isinstance(parent, ast.Return):
        output = '호출한 곳으로 반환'
    elif isinstance(parent, ast.Expr):
        output = '반환값을 변수에 저장하지 않음'
    else:
        output = '다른 표현식에서 사용 · 실제 값은 실행 없이 확인할 수 없음'
    return CallConnections(tuple(inputs), output)


def highlighted_lines(
    source: str,
    focus: set[int],
    related: set[int] = frozenset(),
    markers: dict[int, list[str]] | None = None,
    active: str = '',
) -> str:
    """Mark explained, connected and concept lines; submitted text is escaped.

    `markers` maps a line to every concept letter on it (two calls can share a
    line); the `active` letter is drawn as the selected one.
    """
    lines = []
    for number, line in enumerate(source.splitlines(), start=1):
        if number in focus:
            style = 'code-line selected'
        elif number in related:
            style = 'code-line related'
        else:
            style = 'code-line'
        marker = ''
        if markers is not None:
            badges = ''.join(
                f'<span class="marker{" on" if letter == active else ""}">{escape(letter)}</span>'
                for letter in markers.get(number, [])
            )
            marker = f'<span class="markers">{badges}</span>'
        lines.append(
            f'<span class="{style}">{marker}<span class="line-number">{number}</span>'
            f'{escape(line)}</span>'
        )
    # A <div>, not <pre>: Streamlit's markdown replaces <pre> and drops its class.
    return '<div class="source-code focus-code">' + ''.join(lines) + '</div>'
