"""OpenAI Agents SDK function tools for static analysis and documentation."""

import json
from typing import Literal

from agents import function_tool

from agent.analyzer import analyze_code
from agent.documentation import lookup_documentation
from agent.models import LearningTarget
from agent.planner import build_learning_plan


@function_tool(name_override="analyze_code")
def analyze_code_tool(code: str, surrounding_context: str) -> str:
    """Statically analyze Python source and return traceable learning targets."""
    return analyze_code(code, surrounding_context).model_dump_json()


@function_tool(name_override="build_learning_plan")
def build_learning_plan_tool(
    learning_targets: list[LearningTarget],
    syntax: list[str],
    level: Literal["Beginner", "Developer"],
) -> str:
    """Choose up to three resolved targets and an explanation order from analysis results."""
    return build_learning_plan(
        learning_targets,
        syntax,
        level,
    ).model_dump_json()


@function_tool(name_override="lookup_documentation")
def lookup_documentation_tool(module: str, symbol: str) -> str:
    """Look up a Python builtin or standard-library symbol in official Python documentation."""
    return json.dumps(lookup_documentation(module, symbol), ensure_ascii=False)
