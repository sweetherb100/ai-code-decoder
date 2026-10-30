"""Concept and quiz guardrails added for the focus-and-check learning screens."""

import unittest

from agent.models import (
    ConceptExplanation,
    DecodeResult,
    DocumentationEvidence,
    LearningTarget,
    QuizOption,
    SourceReference,
    UnderstandingQuiz,
)
from agent.quality import (
    DecodeQualityError,
    drop_unverifiable_concepts,
    validate_decode_result,
)


def target(target_id='t1', module='asyncio', symbol='gather'):
    return LearningTarget(
        target_id=target_id, name=symbol, kind='function', module=module, symbol=symbol,
        expression=f'{module}.{symbol}(*tasks)', source='submitted_code', line=11, end_line=11,
        resolution='resolved', used_as_input_of=None,
    )


def evidence(source_id='doc-gather', module='asyncio', symbol='gather', status='exact_match'):
    return DocumentationEvidence(
        source_id=source_id, status=status, module=module, symbol=symbol,
        title='asyncio.gather', excerpt='Run awaitable objects concurrently.',
        url='https://docs.python.org/3/library/asyncio-task.html#asyncio.gather',
    )


def concept(target_id='t1', source_id='doc-gather', **overrides):
    values = dict(
        target_id=target_id, role='여러 코루틴을 동시에 실행합니다.', input='*tasks',
        output='results 리스트', connection='대기 시간을 겹치려는 의도로 보입니다.',
        related_lines=[10, 12], source_id=source_id, example='await asyncio.gather(a(), b())',
    )
    values.update(overrides)
    return ConceptExplanation(**values)


def quiz(correct=(True, False), labels=('약 3초', '약 9초')):
    return UnderstandingQuiz(question='sleep(3)이면 전체 시간은?', options=[
        QuizOption(label=label, correct=flag, feedback='이유 설명')
        for label, flag in zip(labels, correct)
    ])


def result(concepts=(), quiz_value=None, cite=True):
    source = [SourceReference(source_id='doc-gather', title='asyncio.gather',
                              url='https://docs.python.org/3/library/asyncio-task.html#asyncio.gather')]
    return DecodeResult(
        what=['요약'], why='해석', source=source if cite else [], example='e', check='무엇일까요?',
        concepts=list(concepts), quiz=quiz_value or quiz(),
    )


class ConceptQualityTests(unittest.TestCase):
    def assert_issue(self, value, code, targets=(target(),), docs=(evidence(),)):
        with self.assertRaises(DecodeQualityError) as caught:
            validate_decode_result(value, list(docs), list(targets))
        self.assertIn(code, caught.exception.issue_codes)

    def test_valid_concept_and_quiz_pass(self):
        value = result([concept()])
        self.assertIs(validate_decode_result(value, [evidence()], [target()]), value)

    def test_concept_without_source_is_allowed(self):
        value = result([concept(source_id=None)])
        self.assertIs(validate_decode_result(value, [evidence()], [target()]), value)

    def test_unknown_and_duplicate_targets_are_rejected(self):
        self.assert_issue(result([concept(target_id='other')]), 'unknown_concept_target')
        self.assert_issue(result([concept(), concept()]), 'duplicate_concept')

    def test_concept_cannot_borrow_another_targets_source(self):
        docs = [evidence(), evidence(source_id='doc-run', symbol='run')]
        targets = [target(), target('t2', symbol='run')]
        self.assert_issue(result([concept(target_id='t2', source_id='doc-gather')]),
                          'unverified_concept_source', targets, docs)
        self.assert_issue(result([concept(source_id='made-up')]), 'unverified_concept_source')

    def test_non_exact_documentation_is_not_citable_by_concepts(self):
        self.assert_issue(result([concept()], cite=False), 'unverified_concept_source',
                          docs=[evidence(status='page_only')])

    def test_empty_role_is_missing_field(self):
        self.assert_issue(result([concept(role=' ')]), 'missing_field')

    def test_quiz_needs_exactly_one_correct_answer(self):
        for value in (quiz((True, True)), quiz((False, False)), quiz((True,), ('하나',)),
                      quiz((True, False), ('같음', '같음'))):
            with self.subTest(options=[o.label for o in value.options]):
                self.assert_issue(result([concept()], quiz_value=value), 'invalid_quiz')

    def test_without_targets_only_source_ids_are_checked(self):
        value = result([concept(target_id='anything')])
        self.assertIs(validate_decode_result(value, [evidence()]), value)


class ConceptRepairTests(unittest.TestCase):
    def test_unknown_and_duplicate_concepts_are_dropped_not_failed(self):
        value = result([concept(), concept(), concept(target_id='async-syntax')])
        repaired, codes = drop_unverifiable_concepts(value, [evidence()], [target()])
        self.assertEqual([c.target_id for c in repaired.concepts], ['t1'])
        self.assertEqual(set(codes), {'duplicate_concept', 'unknown_concept_target'})
        self.assertIs(validate_decode_result(repaired, [evidence()], [target()]), repaired)

    def test_unverified_concept_source_is_cleared(self):
        value = result([concept(source_id='made-up')])
        repaired, codes = drop_unverifiable_concepts(value, [evidence()], [target()])
        self.assertIsNone(repaired.concepts[0].source_id)
        self.assertEqual(codes, ('unverified_concept_source',))

    def test_valid_result_is_returned_unchanged(self):
        value = result([concept()])
        repaired, codes = drop_unverifiable_concepts(value, [evidence()], [target()])
        self.assertIs(repaired, value)
        self.assertEqual(codes, ())


if __name__ == '__main__':
    unittest.main()
