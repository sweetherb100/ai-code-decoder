"""OpenAI Agents SDK function tools for static analysis and documentation."""

from agents import RunContextWrapper, function_tool

from agent.pipeline import run_decode_pipeline
from agent.run_context import DecodeRunContext


@function_tool(name_override="decode_code_pipeline", strict_mode=True)
def decode_code_pipeline_tool(context: RunContextWrapper[DecodeRunContext]) -> str:
    """Return verified learning evidence for the submitted Python code.

    This is a read-only tool: it never executes, rewrites, stores, or otherwise
    changes the submitted code. Use it exactly once before answering a request to
    explain the submitted Python code. Do not use it to run code, modify code,
    research APIs beyond the returned evidence, or answer unrelated questions.

    Static AST analysis has already validated the submitted code before the AI
    call. This tool performs two internal steps in this fixed order:
    deterministic learning-plan selection and official documentation lookup for
    each selected target. Built-ins and the standard library use Python's docs;
    supported third-party packages use their own official docs; other packages
    are unsupported. It returns JSON with:
    - analysis: imports, syntax, traceable learning targets, and analyzer notes;
    - learning_plan: selected target IDs and their explanation order; and
    - documentation: one evidence item per selected target.

    Interpret documentation.status as follows: exact_match is citable evidence;
    page_only, unsupported, and unavailable are not citable sources. Copy only
    source_id, title, and URL from exact_match items into the final response.

    This tool accepts no model-provided arguments. It reads the precomputed
    analysis and audience level from the trusted run context so those values
    cannot be changed by a tool call.
    """
    run = context.context
    run.begin_pipeline_tool_call()
    run.pipeline_evidence = run_decode_pipeline(
        run.analysis,
        run.level,
    )
    return run.pipeline_evidence.model_dump_json()
