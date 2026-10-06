"""OpenAI Agents SDK function tools for static analysis and documentation."""

import json

from agents import function_tool

from agent.analyzer import analyze_code
from agent.documentation import lookup_documentation


@function_tool(name_override="analyze_code")
def analyze_code_tool(code: str, surrounding_context: str) -> str:
    """Statically analyze Python source and return imports, calls, syntax, and learning targets."""
    return analyze_code(code, surrounding_context).model_dump_json()


@function_tool(name_override="lookup_documentation")
def lookup_documentation_tool(module: str, symbol: str) -> str:
    """Look up a Python builtin or standard-library symbol in official Python documentation."""
    return json.dumps(lookup_documentation(module, symbol), ensure_ascii=False)
