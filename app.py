"""Streamlit web demo for AI Code Decode Agent."""

from __future__ import annotations

from collections import Counter
from html import escape
import os
from pathlib import Path
import uuid

from openai import APIConnectionError, AuthenticationError, RateLimitError
from dotenv import load_dotenv
import streamlit as st

# Load .env before importing agent modules so telemetry settings are visible.
load_dotenv()

from agent.analyzer import CodeAnalysisError, MAX_CODE_CHARACTERS, analyze_code  # noqa: E402
from agent.decoder import DecodeExecution, decode_code  # noqa: E402
from agent.observability import active_settings, record_user_feedback  # noqa: E402
from agent.quality import DecodeQualityError  # noqa: E402
from agent.visualization import build_code_map, highlighted_code, highlighted_lines  # noqa: E402

st.set_page_config(page_title="AI Code Decode", page_icon="🔎", layout="wide")
st.markdown('<style>' + Path(__file__).with_name('ui_styles.css').read_text() + '</style>', unsafe_allow_html=True)


PIPELINE_TOOL_NAME = "decode_code_pipeline"
RESULT_WIDGET_KEYS = ('concept_pick', 'concept_index', 'quiz_answer', 'own_words')
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
        secret_key = None
    if secret_key:
        os.environ["OPENAI_API_KEY"] = str(secret_key)
        return str(secret_key)
    return None


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
        st.success(
            "Agent가 `decode_code_pipeline` Function Tool을 1회 호출했습니다."
        )
    else:
        st.warning(
            "예상한 Tool 호출 이력과 다릅니다: "
            f"{', '.join(execution.tool_call_audit) or '없음'}"
        )

    st.markdown("**고정 파이프라인 내부 단계**")
    st.markdown("- AST 정적 분석")
    st.markdown("- 분석 결과를 바탕으로 한 학습 계획 생성")
    st.markdown("- 선택된 학습 대상의 공식 Python 문서 조회")

    targets_by_id = {
        target.target_id: target for target in execution.analysis.learning_targets
    }
    st.markdown("**선택된 학습 대상**")
    if execution.learning_plan.primary_targets:
        for item in execution.learning_plan.primary_targets:
            target = targets_by_id[item.target_id]
            st.write(
                f"{item.explanation_order}. {target.name} "
                f"(`{target.expression}`) — {item.reason}"
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
        source = (
            f"[{evidence.title}]({evidence.url})"
            if evidence.url
            else evidence.title
        )
        st.markdown(
            f"- `{evidence.module}.{evidence.symbol}` — {label}: {source}"
        )

    if execution.trace_url:
        st.markdown(f"[Langfuse trace 열기]({execution.trace_url})")
    elif active_settings().enabled:
        st.caption(
            "Langfuse tracing이 활성화되어 있습니다. 기본 설정에서는 코드 원문 없이 "
            "구조 정보와 모델 사용량만 기록합니다."
        )
    else:
        st.caption(
            "Trace를 보려면 `LANGFUSE_ENABLED=1`과 Langfuse 키를 설정하세요."
        )


EXAMPLE_CODE = 'numbers = [3, 1, 4, 2]\nresult = sorted(numbers)\nprint(result)'


def _clear_result() -> None:
    for key in ('decode_result', 'code_analysis', 'decode_execution', 'decoded_input', 'preview_input',
                *RESULT_WIDGET_KEYS):
        st.session_state.pop(key, None)


def _load_example() -> None:
    st.session_state['code_input'] = EXAMPLE_CODE
    st.session_state['context_input'] = ''
    _clear_result()


def _clear_code() -> None:
    st.session_state['code_input'] = ''


def _reset_map() -> None:
    st.session_state['map_step'] = 0


def _render_sources(execution) -> None:
    if not execution.documentation:
        st.caption('공식 문서 조회 대상이 없습니다. 직접 작성한 함수나 지원하지 않는 API의 동작은 문서로 단정하지 않습니다.')
    seen = set()
    for doc in execution.documentation:
        if (doc.module, doc.symbol) in seen:
            continue
        seen.add((doc.module, doc.symbol))
        st.markdown('**' + doc.module + '.' + doc.symbol + '**')
        if doc.status == 'exact_match':
            st.text(doc.excerpt)
            st.link_button('공식 문서 열기 ↗', doc.url)
        else:
            st.warning(DOCUMENTATION_STATUS_LABELS[doc.status])
            st.caption('일치하는 문서 근거가 없어 출처로 사용하지 않습니다.')


def _badge(label: str, kind: str) -> None:
    """Static label only: never pass model or user text here."""
    st.markdown(f'<span class="badge {kind}">{label}</span>', unsafe_allow_html=True)


def _doc_for(execution, target):
    for doc in execution.documentation:
        if (doc.module, doc.symbol) == (target.module, target.symbol):
            return doc
    return None


def _render_code_map(code: str, context: str) -> None:
    if context.strip():
        map_source = st.radio('표시할 코드', ['입력 코드', '주변 코드'], horizontal=True,
                              key='map_source', on_change=_reset_map)
    else:
        map_source = '입력 코드'
    source = context if map_source == '주변 코드' else code
    overview = build_code_map(source)
    st.session_state.setdefault('map_step', 0)
    if st.session_state['map_step'] >= len(overview.steps):
        _reset_map()
    if overview.steps:
        code_column, map_column = st.columns([1, 1.2], gap='large')
        with code_column:
            st.markdown('**코드**')
            index = st.selectbox('살펴볼 부분', range(len(overview.steps)), key='map_step',
                                 format_func=lambda i: f'{overview.steps[i].line}행 · {overview.steps[i].label}')
            st.markdown(highlighted_code(source, overview.steps[index]), unsafe_allow_html=True)
        with map_column:
            st.markdown('**전체 구조**')
            st.caption('화살표는 문장 순서와 블록 관계입니다. 실제 실행 경로나 계산된 값은 아닙니다.')
            st.graphviz_chart(build_code_map(source, index).dot, width='stretch', height=270)
        if overview.omitted:
            st.caption(f'복잡한 코드는 앞부분 16개 문장을 표시합니다. {overview.omitted}개 문장은 생략되었습니다. 더 작은 코드로 나누어 확인하세요.')
    else:
        st.info('주석이나 빈 줄만 있어 표시할 문장이 없습니다.')


SCREENS = ('input', 'focus', 'decode', 'check')
SCREEN_STAGE = {'input': 1, 'focus': 2, 'decode': 2, 'check': 3}
CONCEPT_LETTERS = 'ABCDEFGHIJ'


def _render_header(screen: str) -> None:
    stage = SCREEN_STAGE[screen]
    steps = []
    for number, label in enumerate(('발견', '분석', '검증'), start=1):
        state = 'current' if number == stage else 'done' if number < stage else ''
        mark = ' ✓' if number < stage else ''
        current = ' aria-current="step"' if number == stage else ''
        steps.append(f'<span class="step {state}"{current}>{number} {label}{mark}</span>')
    st.markdown(
        '<div class="app-header"><div class="brand"><span class="brand-mark" aria-hidden="true">&lt;/&gt;</span>'
        '<strong>AI Code Decoder</strong></div>'
        '<nav class="stepper" aria-label="진행 단계">' + '<span class="step-line"></span>'.join(steps) + '</nav>'
        '<div class="privacy"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"></rect>'
        '<path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg> 코드는 실행되지 않으며, '
        '분석을 위해 OpenAI API로 전송됩니다</div></div>',
        unsafe_allow_html=True,
    )


def _screen_title(title: str, subtitle: str = '') -> None:
    """Static copy only: callers escape any user or model text they pass."""
    sub = f'<p class="screen-sub">{subtitle}</p>' if subtitle else ''
    st.markdown(f'<div class="screen-title"><h2>{title}</h2>{sub}</div>', unsafe_allow_html=True)


# --- navigation -------------------------------------------------------------
# Widgets that are not drawn on a screen lose their state, so the decoded input
# and the chosen concept live in plain session keys and are restored on return.

def _go(screen: str) -> None:
    st.session_state['screen'] = screen


def _go_input() -> None:
    decoded = st.session_state.get('decoded_input')
    if decoded:
        code, context, level = decoded
        st.session_state['code_input'] = code
        st.session_state['context_input'] = context
        st.session_state['audience_level'] = level
    _go('input')


def _store_concept() -> None:
    st.session_state['concept_index'] = st.session_state.get('concept_pick') or 0


def _next_concept(count: int) -> None:
    st.session_state['concept_index'] = (st.session_state.get('concept_index', 0) + 1) % max(count, 1)
    st.session_state.pop('quiz_answer', None)
    _go('focus')


def _execution_concepts(execution):
    """Concepts the analysis can locate, paired with their learning targets."""
    targets = {target.target_id: target for target in execution.analysis.learning_targets}
    return [(c, targets[c.target_id]) for c in execution.result.concepts if c.target_id in targets]


def _current_concept(pairs):
    index = st.session_state.get('concept_index', 0)
    if index >= len(pairs):
        index = 0
        st.session_state['concept_index'] = 0
    return index, pairs[index]


def _source_for(target, code: str, context: str) -> str:
    return context if target.source == 'surrounding_context' else code


def _focus_lines(target) -> set[int]:
    if not target.line:
        return set()
    return set(range(target.line, (target.end_line or target.line) + 1))


def _code_card(title: str, markup: str, note: str = '') -> None:
    note_html = f'<span>{note}</span>' if note else ''
    st.markdown(
        f'<div class="code-card"><div class="code-card-head"><strong>{escape(title)}</strong>{note_html}</div>'
        f'{markup}</div>',
        unsafe_allow_html=True,
    )


# --- 01 코드 입력 -------------------------------------------------------------

def _render_input_screen() -> None:
    _screen_title('이해하고 싶은 AI 코드를 붙여넣으세요',
                  '코드 전체를 설명하지 않습니다. 분석 후 집중할 부분을 직접 고르게 됩니다.')
    editor, side = st.columns([1.7, 1], gap='large')
    with editor, st.container(key='editor_card'):
        line_count = len(st.session_state.get('code_input', '').splitlines())
        with st.container(key='editor_head', horizontal=True, vertical_alignment='center', gap='small'):
            st.markdown(f'<div class="file-meta"><strong>main.py</strong>'
                        f'<span class="chip">Python · {line_count}줄</span></div>', unsafe_allow_html=True)
            st.button('예제 불러오기', key='load_example', on_click=_load_example)
            st.button('지우기', key='clear_code', on_click=_clear_code)
        code = st.text_area('Python 코드', height=420, key='code_input', placeholder=EXAMPLE_CODE,
                            label_visibility='collapsed')
    with side, st.container(key='context_card'):
        st.markdown('<div class="aside-title">주변 맥락</div>', unsafe_allow_html=True)
        context = st.text_area('주변 코드 (선택)', height=120, key='context_input',
                               placeholder='예: 이 코드가 쓰는 변수 선언이나 함수 정의')
        level = st.selectbox('설명 수준', ['Beginner', 'Developer'], key='audience_level')
        st.markdown(
            f'<div class="scope-box"><strong>지원 범위 (MVP)</strong><p>Python 표준 라이브러리만 설명합니다. '
            f'외부 패키지 호출은 ‘미확인’으로 표시됩니다. 최대 {MAX_CODE_CHARACTERS:,}자.</p></div>',
            unsafe_allow_html=True,
        )
        decode_clicked = st.button('코드 분석 시작 →', key='decode', type='primary', width='stretch')
        preview_clicked = st.button('AI 없이 구조만 먼저 보기', key='preview', type='tertiary',
                                    width='stretch')

    snapshot = (code, context, level)
    if decode_clicked or preview_clicked:
        _run_analysis(code, context, level, decode_clicked)
        return

    decoded = st.session_state.get('decoded_input')
    if decoded and st.session_state.get('decode_execution'):
        if decoded == snapshot:
            st.button('이전 분석 결과로 돌아가기 →', key='resume', on_click=_go, args=('focus',))
        else:
            st.info('입력이 바뀌었습니다. 코드 분석을 다시 눌러주세요.')
    elif st.session_state.get('preview_input'):
        if st.session_state['preview_input'] == snapshot:
            st.markdown('#### 코드의 구조를 먼저 살펴보세요')
            _render_code_map(code, context)
            st.caption('구조 지도는 API 없이 생성했습니다. 코드 분석을 누르면 핵심 개념 설명과 이해도 점검이 추가됩니다.')
        else:
            st.info('입력이 바뀌었습니다. 구조 보기 또는 코드 분석을 다시 눌러주세요.')


def _run_analysis(code: str, context: str, level: str, with_ai: bool) -> None:
    _clear_result()
    _reset_map()
    st.session_state['map_source'] = '입력 코드'
    try:
        if not code.strip():
            raise CodeAnalysisError('분석할 Python 코드를 입력해 주세요.')
        analyze_code(code, context)
        st.session_state['preview_input'] = (code, context, level)
        if not with_ai:
            st.rerun()
        if not _api_key():
            st.error('OPENAI_API_KEY를 환경 변수, .env 파일 또는 Streamlit secrets에 설정해 주세요. '
                     '구조만 먼저 보기는 키 없이 사용할 수 있습니다.')
            return
        with st.spinner('공식 문서를 확인하고 설명을 작성하고 있습니다…'):
            execution = decode_code(code, level, context, session_id=_session_id())
        st.session_state['decode_execution'] = execution
        st.session_state['decoded_input'] = (code, context, level)
        st.session_state['concept_index'] = 0
        _go('focus' if _execution_concepts(execution) else 'decode')
        st.rerun()
    except CodeAnalysisError as exc:
        st.error(str(exc))
    except DecodeQualityError as exc:
        st.error('공식 문서 근거 검증을 통과하지 못했습니다. 구조만 먼저 보기는 사용할 수 있으며 AI 분석은 다시 시도해 주세요.')
        with st.expander('검증 실패 이유'):
            st.caption('검증 코드: ' + (', '.join(exc.issue_codes) or '없음'))
            st.text(str(exc))
    except AuthenticationError:
        st.error('OpenAI가 API 키 인증을 거부했습니다. 키를 확인하고 서버를 재시작해 주세요.')
    except RateLimitError:
        st.error('OpenAI 사용량 또는 요청 한도에 도달했습니다. 계정의 API 사용 한도를 확인해 주세요.')
    except APIConnectionError:
        st.error('OpenAI에 연결하지 못했습니다. 네트워크 연결을 확인하고 다시 시도해 주세요.')
    except Exception as exc:
        st.error('AI 분석을 완료하지 못했습니다. 구조만 먼저 보기로 코드 구조를 확인할 수 있습니다.')
        with st.expander('오류 진단'):
            st.text(type(exc).__name__)


# --- 02 집중 영역 선택 --------------------------------------------------------

def _analysis_strip(execution) -> None:
    analysis = execution.analysis
    unresolved = sum(t.resolution == 'unresolved' for t in analysis.learning_targets)
    parts = [f'함수 {len(analysis.functions)}개']
    if analysis.imports:
        parts.append('사용 모듈: ' + ', '.join(analysis.imports[:4]))
    parts.append(f'미확인 호출 {unresolved}개' if unresolved else '미확인 호출 없음')
    st.markdown(
        '<div class="analysis-strip"><span class="badge fact">Fact</span><strong>AST 분석 완료</strong>'
        f'<span>· 문법 오류 없음 · {escape(" · ".join(parts))}</span></div>',
        unsafe_allow_html=True,
    )


def _render_focus_screen(execution, code: str, context: str) -> None:
    pairs = _execution_concepts(execution)
    if not pairs:
        _go('decode')
        st.rerun()
    st.button('← 코드 수정', key='back_to_input', on_click=_go_input, type='tertiary')
    _screen_title('어디에 집중할까요?',
                  '엔진이 이 코드에서 먼저 알아야 할 핵심 개념을 추렸습니다. 하나를 골라 Decode 하세요.')
    _analysis_strip(execution)
    index, (concept, target) = _current_concept(pairs)
    source = _source_for(target, code, context)
    markers: dict[int, list[str]] = {}
    for i, (_, other) in enumerate(pairs):
        if other.line and other.source == target.source:
            markers.setdefault(other.line, []).append(CONCEPT_LETTERS[i])

    code_column, pick_column = st.columns([1.5, 1], gap='large')
    with code_column:
        title = '주변 코드' if target.source == 'surrounding_context' else 'main.py'
        _code_card(title, highlighted_lines(source, _focus_lines(target), markers=markers,
                                            active=CONCEPT_LETTERS[index]),
                   '읽기 전용 · 실행하지 않음')
    with pick_column, st.container(key='concept_cards'):
        st.markdown(f'<div class="aside-title">핵심 개념 {len(pairs)}개</div>', unsafe_allow_html=True)
        labels = []
        captions = []
        for item, item_target in pairs:
            # Letter badge and the "추천" pill are drawn by CSS; markdown code keeps it mono.
            expression = item_target.expression.replace('`', "'")
            line = f' · L{item_target.line}' if item_target.line else ''
            labels.append(f'`{expression}`{line}')
            captions.append(item.role)
        st.radio('핵심 개념', range(len(pairs)), index=index, key='concept_pick',
                 format_func=lambda i: labels[i], captions=captions,
                 on_change=_store_concept, label_visibility='collapsed')
        st.caption('선택한 부분의 역할과 연결만 먼저 보여드립니다. 공식 문서와 예제는 필요할 때 펼쳐 볼 수 있어요.')
        st.button('선택한 부분 Decode →', key='go_decode', type='primary', width='stretch',
                  on_click=_go, args=('decode',))


# --- 03 Decode 설명 ---------------------------------------------------------

def _render_concept_panel(execution, concept, target) -> None:
    line = f'L{target.line}' if target.line else '위치 미상'
    st.markdown(f'<span class="line-chip">{line}</span>', unsafe_allow_html=True)
    st.code(target.expression, language='python', wrap_lines=True)
    st.markdown('<div class="legend-inline"><span class="badge fact">Fact</span> AST · 공식 문서로 확인된 내용'
                '<span class="badge assumption">Assumption</span> AI의 해석 · 추정</div>',
                unsafe_allow_html=True)
    _badge('[What] 역할 — Fact', 'fact')
    st.write(concept.role)
    io_in, io_out = st.columns(2)
    with io_in, st.container(border=True, key='io_input'):
        st.caption('입력')
        st.write(concept.input)
    with io_out, st.container(border=True, key='io_output'):
        st.caption('출력')
        st.write(concept.output)
    with st.container(border=True, key='why_box'):
        _badge('[Why] 내 코드와 연결 — Assumption', 'assumption')
        st.write(concept.connection)
        related = sorted(set(concept.related_lines) - _focus_lines(target))
        if related:
            st.caption('연결된 줄: ' + ', '.join(f'L{n}' for n in related))
    doc = _doc_for(execution, target)
    if doc and doc.status == 'exact_match' and concept.source_id == doc.source_id:
        _badge('[Source] 근거 — 출처 일치 확인', 'fact')
        st.link_button(doc.title + ' ↗', doc.url)
    else:
        _badge('[Source] 근거 — 확인된 문서 없음', 'assumption')
        status = DOCUMENTATION_STATUS_LABELS.get(doc.status) if doc else None
        st.caption((status + ' · ' if status else '') + '이 개념은 공식 문서로 확인하지 못했습니다.')
    with st.expander('[Example] 최소 예제 보기'):
        st.code(concept.example, language='python', wrap_lines=True)
    if doc and doc.status == 'exact_match':
        with st.expander('[More] 공식 문서 발췌 펼치기'):
            st.text(doc.excerpt)


def _render_overview(execution) -> None:
    decoded = execution.result
    _badge('[What] 핵심 설명 — Fact', 'fact')
    for item in decoded.what:
        st.write(item)
    with st.container(border=True, key='overview_why'):
        _badge('[Why] 코드와 맥락에 대한 해석 — Assumption', 'assumption')
        st.write(decoded.why)


def _render_decode_screen(execution, code: str, context: str) -> None:
    pairs = _execution_concepts(execution)
    if pairs:
        st.button('← 다른 개념 고르기', key='back_to_focus', on_click=_go, args=('focus',), type='tertiary')
    else:
        st.button('← 코드 수정', key='back_to_input', on_click=_go_input, type='tertiary')

    if pairs:
        _, (concept, target) = _current_concept(pairs)
        source = _source_for(target, code, context)
        focus = _focus_lines(target)
        code_column, panel_column = st.columns([1.15, 1], gap='large')
        with code_column:
            title = '주변 코드' if target.source == 'surrounding_context' else 'main.py'
            _code_card(title, highlighted_lines(source, focus, set(concept.related_lines) - focus))
            st.markdown('<div class="legend"><span class="key selected"></span>설명 대상'
                        '<span class="key related"></span>연결된 주변 코드</div>', unsafe_allow_html=True)
        with panel_column, st.container(border=True, key='decode_panel'):
            _render_concept_panel(execution, concept, target)
            st.divider()
            st.caption('이해했는지 한 문제로 확인해 볼까요?')
            st.button('이해도 점검 →', key='go_check', type='primary', width='stretch',
                      on_click=_go, args=('check',))
    else:
        with st.container(border=True, key='overview_panel'):
            _render_overview(execution)
            with st.expander('[Example] 설명용 예제 (실행하지 않음)'):
                st.code(execution.result.example, language='python', wrap_lines=True)
            st.button('이해도 점검 →', key='go_check', type='primary', width='stretch',
                      on_click=_go, args=('check',))

    if pairs:
        with st.expander('코드 전체 해석'):
            _render_overview(execution)
            st.code(execution.result.example, language='python', wrap_lines=True)
    with st.expander('전체 코드 구조 지도'):
        _render_code_map(code, context)
    with st.expander(f'공식 문서 근거 · {sum(d.status == "exact_match" for d in execution.documentation)}개 확인'):
        _render_sources(execution)
    with st.expander('분석 진단 정보'):
        _render_execution_evidence(execution)


# --- 04 이해도 점검 -----------------------------------------------------------

def _render_check_screen(execution) -> None:
    decoded = execution.result
    pairs = _execution_concepts(execution)
    st.button('← 설명으로 돌아가기', key='back_to_decode', on_click=_go, args=('decode',), type='tertiary')
    current = _current_concept(pairs)[1][1] if pairs else None
    title = '이해도 점검' + (f' · <code>{escape(current.expression)}</code>' if current else '')
    _screen_title(title)

    quiz_column, side_column = st.columns([1.6, 1], gap='large')
    with quiz_column:
        with st.container(border=True, key='quiz_panel'):
            _badge('[Check] 동작 예측', 'check')
            st.markdown(f'<p class="quiz-question">{escape(decoded.quiz.question)}</p>', unsafe_allow_html=True)
            options = decoded.quiz.options
            picked = st.radio('답 선택', range(len(options)), index=None, key='quiz_answer',
                              format_func=lambda i: options[i].label, horizontal=True,
                              label_visibility='collapsed')
            if picked is not None and picked < len(options):
                option = options[picked]
                if option.correct:
                    st.success('맞아요. ' + option.feedback)
                else:
                    st.warning('다시 생각해 볼까요? ' + option.feedback)
                    st.button('설명 다시 보기', key='review', on_click=_go, args=('decode',))
        with st.container(border=True, key='own_words_panel'):
            _badge('[Check] 내 언어로 설명하기', 'check')
            st.info(decoded.check)
            st.text_area('내 설명', key='own_words', height=90, label_visibility='collapsed',
                         placeholder='역할, 입력과 출력, 주변 코드와의 연결을 한두 문장으로 적어 보세요.')
            st.caption('작성한 내용은 저장하거나 전송하지 않습니다.')
            _render_feedback(execution)
    with side_column, st.container(border=True, key='progress_panel'):
        st.markdown('**이 코드의 핵심 개념**')
        if pairs:
            current_index = st.session_state.get('concept_index', 0)
            rows = []
            for i, (_, target) in enumerate(pairs):
                state = 'on' if i == current_index else ''
                tag = '<em>점검 중</em>' if i == current_index else ''
                rows.append(f'<li class="{state}"><span class="dot"></span><code>{escape(target.expression)}</code>{tag}</li>')
            st.markdown('<ul class="concept-progress">' + ''.join(rows) + '</ul>', unsafe_allow_html=True)
            if len(pairs) > 1:
                st.button('다음 개념 Decode', key='next_concept', width='stretch',
                          on_click=_next_concept, args=(len(pairs),))
        else:
            st.caption('이 코드에는 따로 고를 핵심 개념이 없어 전체 설명으로 점검했습니다.')
        st.button('새 코드 분석하기', key='new_code', width='stretch', on_click=_go_input)


# --- router -----------------------------------------------------------------

screen = st.session_state.get('screen', 'input')
execution = st.session_state.get('decode_execution')
decoded_input = st.session_state.get('decoded_input')
if screen != 'input' and (execution is None or decoded_input is None):
    screen = 'input'
    st.session_state['screen'] = 'input'

_render_header(screen)
if screen == 'input':
    _render_input_screen()
else:
    code, context, _ = decoded_input
    if screen == 'focus':
        _render_focus_screen(execution, code, context)
    elif screen == 'decode':
        _render_decode_screen(execution, code, context)
    else:
        _render_check_screen(execution)
