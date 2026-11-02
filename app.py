"""Streamlit web demo for AI Code Decode Agent."""

from __future__ import annotations

import os
import uuid
from collections import Counter
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

# Load .env before importing agent modules so telemetry settings are visible.
load_dotenv()

from agent.analyzer import MAX_CODE_CHARACTERS, CodeAnalysisError  # noqa: E402
from agent.decoder import DecodeExecution, decode_code  # noqa: E402
from agent.export import to_markdown  # noqa: E402
from agent.observability import active_settings, record_user_feedback  # noqa: E402
from agent.quality import DecodeQualityError, example_syntax_error  # noqa: E402

st.set_page_config(page_title="AI Code Decode", page_icon="🔎", layout="wide")
st.title("AI Code Decode Agent")
st.caption("AI가 만든 Python 코드를 분석하고, 이해와 검증을 돕습니다.")


PIPELINE_TOOL_NAME = "decode_code_pipeline"
DOCUMENTATION_STATUS_LABELS = {
    "exact_match": "정확한 심볼 일치",
    "page_only": "페이지 확인 (심볼 발췌 없음)",
    "unsupported": "지원하지 않는 대상",
    "unavailable": "문서 조회 실패",
}


def _api_key() -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        secret_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        # External config fallback: a missing or malformed secrets.toml raises errors that
        # vary by Streamlit version, and it only means "no key in secrets".
        secret_key = None
    if secret_key:
        os.environ["OPENAI_API_KEY"] = str(secret_key)
        return str(secret_key)
    return None


def _clear_decode_state() -> None:
    for key in ("decode_result", "code_analysis", "decode_execution"):
        st.session_state.pop(key, None)


def _render_feedback(execution: DecodeExecution) -> None:
    """Ask whether the explanation helped and record it on the Langfuse trace."""
    if not execution.trace_id:
        return
    key = f"feedback-{execution.trace_id}"

    def _on_change() -> None:
        vote = st.session_state.get(key)
        if vote is not None:
            record_user_feedback(
                execution.trace_id, execution.root_observation_id, positive=vote == 1
            )

    st.caption("이 설명이 도움이 되었나요?")
    st.feedback("thumbs", key=key, on_change=_on_change)


def _session_id() -> str:
    """Return a stable anonymous ID that groups decode runs of this browser session."""
    if "langfuse_session_id" not in st.session_state:
        st.session_state["langfuse_session_id"] = str(uuid.uuid4())
    return st.session_state["langfuse_session_id"]


def _render_execution_evidence(execution: DecodeExecution) -> None:
    """Show which evidence the agent received without treating inner steps as tools."""
    if execution.tool_call_audit == [PIPELINE_TOOL_NAME]:
        st.success("Agent가 `decode_code_pipeline` Function Tool을 1회 호출했습니다.")
    else:
        st.warning(
            f"예상한 Tool 호출 이력과 다릅니다: {', '.join(execution.tool_call_audit) or '없음'}"
        )

    st.markdown("**고정 파이프라인 내부 단계**")
    st.markdown("- AST 정적 분석")
    st.markdown("- 분석 결과를 바탕으로 한 학습 계획 생성")
    st.markdown("- 선택된 학습 대상의 공식 Python 문서 조회")

    targets_by_id = {target.target_id: target for target in execution.analysis.learning_targets}
    st.markdown("**선택된 학습 대상**")
    if execution.learning_plan.primary_targets:
        for item in execution.learning_plan.primary_targets:
            target = targets_by_id[item.target_id]
            st.write(
                f"{item.explanation_order}. {target.name} (`{target.expression}`) — {item.reason}"
            )
    else:
        st.caption("학습 계획에서 우선 설명 대상을 선택하지 않았습니다.")

    documentation_counts = Counter(item.status for item in execution.documentation)
    summary = ", ".join(
        f"{DOCUMENTATION_STATUS_LABELS[status]} {count}건"
        for status, count in sorted(documentation_counts.items())
    )
    st.markdown("**문서 조회 결과**")
    st.write(summary or "문서 조회 대상이 없습니다.")
    for evidence in execution.documentation:
        label = DOCUMENTATION_STATUS_LABELS[evidence.status]
        source = f"[{evidence.title}]({evidence.url})" if evidence.url else evidence.title
        st.markdown(f"- `{evidence.module}.{evidence.symbol}` — {label}: {source}")

    if execution.trace_url:
        st.markdown(f"[Langfuse trace 열기]({execution.trace_url})")
    elif active_settings().enabled:
        st.caption(
            "Langfuse tracing이 활성화되어 있습니다. 기본 설정에서는 코드 원문 없이 "
            "구조 정보와 모델 사용량만 기록합니다."
        )
    else:
        st.caption("Trace를 보려면 `LANGFUSE_ENABLED=1`과 Langfuse 키를 설정하세요.")


with st.sidebar:
    st.header("설명 설정")
    level = st.selectbox("설명 수준", ["Beginner", "Developer"], index=0)
    st.caption("코드는 실행하지 않습니다. Python AST로 정적으로 분석합니다.")

left, right = st.columns(2, gap="large")
with left:
    st.subheader("YOUR CODE")
    code = st.text_area(
        "분석할 Python 코드",
        height=330,
        placeholder='images = sorted(IMAGES_DIR.glob(f"image_{title}*rank*.png"))',
        label_visibility="collapsed",
        key="code_input",
    )
    context = st.text_area(
        "주변 코드 (선택)",
        height=130,
        placeholder="Why 설명에 도움이 되는 변수 선언이나 앞뒤 코드를 붙여 넣으세요.",
        key="context_input",
    )
    decode_clicked = st.button("Decode Code", type="primary", use_container_width=True)
    character_count = len(code) + len(context)
    character_usage = f"코드와 주변 코드 합계: {character_count:,} / {MAX_CODE_CHARACTERS:,}자"
    if character_count > MAX_CODE_CHARACTERS:
        st.warning(f"{character_usage} (한도 초과)")
    else:
        st.caption(character_usage)

if decode_clicked:
    _clear_decode_state()
    if not code.strip():
        st.error("분석할 Python 코드를 입력해 주세요.")
    elif not _api_key():
        st.error("OPENAI_API_KEY를 환경 변수, .env 파일 또는 Streamlit secrets에 설정해 주세요.")
    else:
        try:
            with st.status(
                "에이전트가 코드와 공식 문서를 분석하고 있습니다…", expanded=True
            ) as status:
                execution = decode_code(code, level, context, session_id=_session_id())
                decoded = execution.result
                analysis = execution.analysis
                st.write("에이전트 도구 호출 완료")
                st.write(f"발견한 학습 대상: {len(analysis.learning_targets)}개")
                status.update(label="코드 디코딩 완료", state="complete", expanded=False)
            st.session_state["decode_result"] = decoded
            st.session_state["code_analysis"] = analysis
            st.session_state["decode_execution"] = execution
            # Keep the decoded input so later edits in the text areas do not leak into exports.
            st.session_state["decode_input"] = {"code": code, "context": context}
        except CodeAnalysisError as exc:
            st.error(str(exc))
            _clear_decode_state()
        except DecodeQualityError as exc:
            st.error(str(exc))
            st.caption("도구 근거에 맞는 응답을 만들지 못했습니다. 다시 시도해 주세요.")
            _clear_decode_state()
        except Exception as exc:
            # UI top level: report any remaining failure to the user and keep the app running.
            st.error(f"디코딩에 실패했습니다: {exc}")
            st.caption("API 키, 모델 권한, 네트워크 연결을 확인한 뒤 다시 시도해 주세요.")
            _clear_decode_state()

with right:
    decoded = st.session_state.get("decode_result")
    analysis = st.session_state.get("code_analysis")
    execution = st.session_state.get("decode_execution")
    title_column, download_column = st.columns([3, 1], vertical_alignment="bottom")
    with title_column:
        st.subheader("DECODED")
    if decoded:
        decode_input = st.session_state.get("decode_input", {"code": "", "context": ""})
        created_at = datetime.now()
        with download_column:
            st.download_button(
                "Download",
                data=to_markdown(
                    decoded,
                    decode_input["code"],
                    decode_input["context"],
                    created_at,
                    MAX_CODE_CHARACTERS,
                ),
                file_name=f"decoded-{created_at:%Y%m%d-%H%M%S}.md",
                mime="text/markdown",
                use_container_width=True,
            )
    if not decoded:
        st.info("코드를 입력하고 Decode Code를 누르면 결과가 여기에 표시됩니다.")
    else:
        st.markdown("### What")
        for item in decoded.what:
            st.markdown(f"- {item}")
        st.markdown("### Why")
        st.write(decoded.why)
        st.markdown("### Source")
        if decoded.source:
            for source in decoded.source:
                st.markdown(f"- [{source.title}]({source.url})")
        else:
            st.write("지원되는 공식 문서 출처를 찾지 못했습니다.")
        st.markdown("### Example")
        st.code(decoded.example, language="python")
        syntax_error = example_syntax_error(decoded.example)
        if syntax_error:
            st.warning(f"❌ 문법 검사 실패 ({syntax_error})")
        else:
            st.caption("✅ 문법 검사 통과 (코드는 실행하지 않고 AST로만 확인했습니다)")
        st.markdown("### Check")
        st.info(decoded.check)
        if execution:
            _render_feedback(execution)
            with st.expander("실행 근거"):
                _render_execution_evidence(execution)
        if analysis:
            with st.expander("AST 분석 세부 정보"):
                st.json(analysis.model_dump())
