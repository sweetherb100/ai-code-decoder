"""UI interactions use real static evidence and a mocked paid decoder call."""

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from agent.analyzer import analyze_code, CodeAnalysisError
from agent.decoder import DecodeExecution
from agent.models import (
    ConceptExplanation,
    DecodeResult,
    DocumentationEvidence,
    QuizOption,
    UnderstandingQuiz,
)
from agent.planner import build_learning_plan


CODE = 'numbers = [3, 1, 4, 2]\nresult = sorted(numbers)\nprint(result)'


QUIZ = UnderstandingQuiz(question='numbers는 정렬 후 어떻게 될까요?', options=[
    QuizOption(label='그대로 [3, 1, 4, 2]', correct=True, feedback='sorted는 새 리스트를 돌려줍니다.'),
    QuizOption(label='[1, 2, 3, 4]로 바뀜', correct=False, feedback='원본을 바꾸는 것은 list.sort입니다.'),
])


def concepts_for(analysis, plan):
    by_id = {t.target_id: t for t in analysis.learning_targets}
    return [ConceptExplanation(
        target_id=item.target_id, role='역할 설명 ' + by_id[item.target_id].name,
        input='입력 설명', output='출력 설명', connection='연결 해석으로 보입니다.',
        related_lines=[1], source_id=item.target_id, example='sorted([2, 1])',
    ) for item in plan.primary_targets]


def execution(code=CODE, context='', status='exact_match', with_concepts=False):
    analysis = analyze_code(code, context)
    plan = build_learning_plan(analysis.learning_targets, analysis.syntax, 'Beginner')
    docs = [DocumentationEvidence(
        source_id=t.target_id, status=status, module=t.module, symbol=t.symbol,
        title='Official ' + t.name, excerpt='Trusted excerpt for ' + t.name,
        url='https://docs.python.org/3/library/functions.html#' + t.symbol,
    ) for t in analysis.learning_targets]
    return DecodeExecution(
        result=DecodeResult(what=['숫자를 정렬한 뒤 출력합니다.'], why='정렬 결과를 확인합니다.',
                            source=[], example='sorted([2, 1])', check='원본이 바뀔까요?',
                            concepts=concepts_for(analysis, plan) if with_concepts else [], quiz=QUIZ),
        analysis=analysis, learning_plan=plan, documentation=docs,
        tool_call_audit=['decode_code_pipeline'],
    )


class VisualAppTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only', 'LANGFUSE_ENABLED': '0'})
        self.env.start()
        self.addCleanup(self.env.stop)
        # UI evidence rendering must not initialize the process-wide tracing SDK.
        settings = patch('agent.observability.active_settings', return_value=SimpleNamespace(enabled=False))
        settings.start()
        self.addCleanup(settings.stop)

    def start(self, result=None, level='Beginner', code=CODE, context=''):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        app.text_area(key='code_input').set_value(code)
        app.text_area(key='context_input').set_value(context)
        app.selectbox(key='audience_level').select(level)
        with patch('agent.decoder.decode_code', return_value=result or execution()):
            app.button(key='decode').click().run(timeout=20)
        self.assertFalse(app.exception)
        return app

    def test_example_load_does_not_call_decoder(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        with patch('agent.decoder.decode_code') as decode:
            app.button(key='load_example').click().run()
        self.assertIn('sorted', app.text_area(key='code_input').value)
        self.assertNotIn('decode_execution', app.session_state)
        decode.assert_not_called()

    def test_map_selection_does_not_call_decoder_again(self):
        for level in ('Beginner', 'Developer'):
            with self.subTest(level=level):
                app = self.start(level=level)
                with patch('agent.decoder.decode_code') as decode:
                    app.selectbox(key='map_step').select(1).run()
                    self.assertFalse(app.exception)
                    decode.assert_not_called()
                highlighted = next(x.value for x in app.markdown if 'class="source-code"' in x.value)
                self.assertIn('sorted(numbers)', highlighted)
                self.assertTrue(any('숫자를 정렬한 뒤 출력합니다.' in x.value for x in app.markdown))

    def test_preview_covers_assignments_without_api_key(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        app.text_area(key='code_input').set_value('price = 100\ncount = 3\ntotal = price * count')
        with patch('agent.decoder.decode_code') as decode:
            app.button(key='preview').click().run()
            decode.assert_not_called()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox(key='map_step').options), 3)
        self.assertTrue(app.get('graphviz_chart'))

    def test_edited_input_hides_old_result(self):
        app = self.start()
        app.button(key='back_to_input').click().run()
        self.assertEqual(app.text_area(key='code_input').value, CODE)
        self.assertTrue(app.button(key='resume'))
        app.text_area(key='code_input').set_value('print("changed")').run()
        self.assertTrue(any('입력이 바뀌었습니다' in x.value for x in app.info))
        self.assertFalse(any('숫자를 정렬한 뒤 출력합니다.' in x.value for x in app.markdown))

    def test_non_exact_document_is_not_shown_as_verified_excerpt(self):
        for status in ('unsupported', 'unavailable', 'page_only'):
            app = self.start(result=execution(status=status))
            self.assertFalse(any('Trusted excerpt' in x.value for x in app.text))
            self.assertTrue(app.warning)

    def test_decode_failure_clears_old_execution(self):
        app = self.start()
        app.button(key='back_to_input').click().run()
        with patch('agent.decoder.decode_code', side_effect=CodeAnalysisError('입력 오류')):
            app.button(key='decode').click().run()
        self.assertNotIn('decode_execution', app.session_state)
        self.assertTrue(any('입력 오류' in x.value for x in app.error))

    def test_no_calls_still_shows_whole_explanation(self):
        app = self.start(result=execution('value = 1'), code='value = 1')
        self.assertEqual(app.session_state['screen'], 'decode')
        self.assertTrue(app.get('graphviz_chart'))
        app.button(key='go_check').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('원본이 바뀔까요?' in x.value for x in app.info))

    def test_surrounding_code_selection_highlights_the_correct_source(self):
        code, context = 'print(result)', 'result = sorted([3, 1])'
        app = self.start(result=execution(code, context), code=code, context=context)
        app.radio(key='map_source').set_value('주변 코드').run()
        highlighted = next(x.value for x in app.markdown if 'class="source-code"' in x.value)
        self.assertIn('sorted([3, 1])', highlighted)
        self.assertNotIn('print(result)', highlighted)

    def test_empty_input_and_missing_key_never_call_decoder(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        with patch('agent.decoder.decode_code') as decode:
            app.button(key='decode').click().run()
            self.assertTrue(any('입력해 주세요' in x.value for x in app.error))
            app.text_area(key='code_input').set_value(CODE)
            with patch.dict(os.environ, {'OPENAI_API_KEY': ''}), patch('streamlit.runtime.secrets.Secrets.get', return_value=None):
                app.button(key='decode').click().run()
            self.assertTrue(any('OPENAI_API_KEY' in x.value for x in app.error))
            decode.assert_not_called()

    def test_screens_follow_input_focus_decode_check(self):
        app = self.start(result=execution(with_concepts=True))
        self.assertEqual(app.session_state['screen'], 'focus')
        self.assertTrue(any('"step current" aria-current="step">2 분석<' in x.value for x in app.markdown))
        focus = next(x.value for x in app.markdown if 'class="source-code focus-code"' in x.value)
        self.assertIn('class="marker on">A<', focus)
        self.assertTrue(any('AST 분석 완료' in x.value for x in app.markdown))
        app.button(key='go_decode').click().run()
        self.assertEqual(app.session_state['screen'], 'decode')
        app.button(key='go_check').click().run()
        self.assertEqual(app.session_state['screen'], 'check')
        self.assertTrue(any('"step current" aria-current="step">3 검증<' in x.value for x in app.markdown))
        app.button(key='back_to_decode').click().run()
        app.button(key='back_to_focus').click().run()
        self.assertEqual(app.session_state['screen'], 'focus')
        self.assertFalse(app.exception)

    def test_decode_panel_highlights_target_and_related_lines(self):
        app = self.start(result=execution(with_concepts=True))
        app.button(key='go_decode').click().run()
        focus = next(x.value for x in app.markdown if 'class="source-code focus-code"' in x.value)
        self.assertIn('class="code-line selected"', focus)
        self.assertIn('class="code-line related"', focus)
        self.assertIn('sorted(numbers)', focus)
        self.assertTrue(any('역할 설명' in x.value for x in app.markdown))
        self.assertTrue(any('Fact' in x.value for x in app.markdown))
        self.assertTrue(any('Assumption' in x.value for x in app.markdown))

    def test_chosen_concept_survives_screen_changes_without_new_decode(self):
        app = self.start(result=execution(with_concepts=True))
        options = app.radio(key='concept_pick').options
        last = len(options) - 1
        with patch('agent.decoder.decode_code') as decode:
            app.radio(key='concept_pick').set_value(last).run()
            app.button(key='go_decode').click().run()
            self.assertFalse(app.exception)
            decode.assert_not_called()
        self.assertEqual(app.session_state['concept_index'], last)
        self.assertTrue(any('역할 설명 print' in x.value for x in app.markdown))
        app.button(key='back_to_focus').click().run()
        self.assertEqual(app.radio(key='concept_pick').value, last)

    def test_quiz_answer_shows_matching_feedback(self):
        app = self.start(result=execution(with_concepts=True))
        app.button(key='go_decode').click().run()
        app.button(key='go_check').click().run()
        app.radio(key='quiz_answer').set_value(1).run()
        self.assertTrue(any('list.sort' in x.value for x in app.warning))
        app.radio(key='quiz_answer').set_value(0).run()
        self.assertTrue(any('새 리스트' in x.value for x in app.success))

    def test_next_concept_and_new_decode_reset_the_check(self):
        app = self.start(result=execution(with_concepts=True))
        app.button(key='go_decode').click().run()
        app.button(key='go_check').click().run()
        app.radio(key='quiz_answer').set_value(1).run()
        app.button(key='next_concept').click().run()
        self.assertEqual(app.session_state['screen'], 'focus')
        self.assertEqual(app.session_state['concept_index'], 1)
        app.button(key='back_to_input').click().run()
        with patch('agent.decoder.decode_code', return_value=execution(with_concepts=True)):
            app.button(key='decode').click().run(timeout=20)
        self.assertEqual(app.session_state['concept_index'], 0)
        self.assertNotIn('quiz_answer', app.session_state)


if __name__ == '__main__':
    unittest.main()
