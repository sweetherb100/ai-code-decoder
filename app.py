"""Streamlit web demo for AI Code Decode Agent."""

from __future__ import annotations

import os

from dotenv import load_dotenv
import streamlit as st

from agent.analyzer import CodeAnalysisError, MAX_CODE_CHARACTERS, analyze_code
from agent.decoder import decode_code


load_dotenv()

st.set_page_config(page_title="AI Code Decode", page_icon="🔎", layout="wide")
st.title("AI Code Decode Agent")
st.caption("AI가 만든 Python 코드를 분석하고, 이해와 검증을 돕습니다.")


def _api_key() -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        secret_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        secret_key = None
    if secret_key:
        os.environ["OPENAI_API_KEY"] = str(secret_key)
        return str(secret_key)
    return None


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
    st.caption(f"코드와 주변 코드 합계 한도: {MAX_CODE_CHARACTERS:,}자")

if decode_clicked:
    st.session_state.pop("decode_result", None)
    st.session_state.pop("code_analysis", None)
    if not code.strip():
        st.error("분석할 Python 코드를 입력해 주세요.")
    elif not _api_key():
        st.error("OPENAI_API_KEY를 환경 변수, .env 파일 또는 Streamlit secrets에 설정해 주세요.")
    else:
        try:
            analysis = analyze_code(code, context)
            with st.status("에이전트가 코드와 공식 문서를 분석하고 있습니다…", expanded=True) as status:
                st.write("Python 문법 구조 확인 완료")
                st.write(f"발견한 학습 대상: {len(analysis.learning_targets)}개")
                decoded = decode_code(code, level, context)
                status.update(label="코드 디코딩 완료", state="complete", expanded=False)
            st.session_state["decode_result"] = decoded
            st.session_state["code_analysis"] = analysis
        except CodeAnalysisError as exc:
            st.error(str(exc))
            st.session_state.pop("decode_result", None)
            st.session_state.pop("code_analysis", None)
        except Exception as exc:
            st.error(f"디코딩에 실패했습니다: {exc}")
            st.caption("API 키, 모델 권한, 네트워크 연결을 확인한 뒤 다시 시도해 주세요.")

with right:
    st.subheader("DECODED")
    decoded = st.session_state.get("decode_result")
    analysis = st.session_state.get("code_analysis")
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
        st.markdown("### Check")
        st.info(decoded.check)
        if analysis:
            with st.expander("AST 분석 세부 정보"):
                st.json(analysis.model_dump())
