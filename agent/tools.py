"""OpenAI Agents SDK function tools for static analysis and documentation."""

from agents import RunContextWrapper, function_tool

from agent.pipeline import run_decode_pipeline
from agent.run_context import DecodeRunContext


@function_tool(name_override="decode_code_pipeline")
def decode_code_pipeline_tool(context: RunContextWrapper[DecodeRunContext]) -> str:
    """Run the fixed, read-only Python code-understanding pipeline for this request."""
    run = context.context
    if run.pipeline_evidence is None:
        run.pipeline_evidence = run_decode_pipeline(
            run.code,
            run.surrounding_context,
            run.level,
        )
        run.record_tool_call("decode_code_pipeline")
    return run.pipeline_evidence.model_dump_json()
