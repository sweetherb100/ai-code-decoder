"""Static presentation must not invent execution or interpret submitted HTML."""

import unittest

from agent.analyzer import analyze_code
from agent.planner import build_learning_plan
from agent.visualization import (
    call_connections,
    highlighted_code,
    highlighted_lines,
    learning_targets,
)


class VisualizationTests(unittest.TestCase):
    def target(self, code, name, context=""):
        return next(t for t in analyze_code(code, context).learning_targets if t.name == name)

    def test_nested_call_passes_to_enclosing_call_not_assignment(self):
        code = 'result = print(sorted(items, reverse=True))'
        target = self.target(code, 'sorted')
        flow = call_connections(code, '', target)
        self.assertEqual(flow.inputs, ('items', 'reverse=True'))
        self.assertEqual(flow.output, 'print(...)의 인자로 전달')

    def test_direct_assignment_and_context_are_kept_separate(self):
        code, context = 'print(result)', 'result = sorted([3, 1])'
        target = self.target(code, 'sorted', context)
        flow = call_connections(code, context, target)
        self.assertEqual(flow.inputs, ('[3, 1]',))
        self.assertEqual(flow.output, 'result에 대입')

    def test_standalone_call_does_not_invent_result_value(self):
        code = 'print("hello")'
        flow = call_connections(code, '', self.target(code, 'print'))
        self.assertEqual(flow.output, '반환값을 변수에 저장하지 않음')

    def test_unknown_call_is_retained_when_plan_is_empty(self):
        analysis = analyze_code('custom(value)')
        plan = build_learning_plan(analysis.learning_targets, analysis.syntax, 'Beginner')
        self.assertEqual(learning_targets(analysis, plan), analysis.learning_targets)

    def test_html_is_escaped_and_multiline_selection_highlighted(self):
        code = 'result = sorted(\n    ["<script>alert(1)</script>"]\n)'
        markup = highlighted_code(code, self.target(code, 'sorted'))
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)
        self.assertEqual(markup.count('class="code-line selected"'), 3)

    def test_keyword_nested_call_and_invalid_source(self):
        code = 'print(value=sorted(items))'
        target = self.target(code, 'sorted')
        self.assertEqual(call_connections(code, '', target).output, 'print(...)의 인자로 전달')
        self.assertIsNone(call_connections('for', '', target))

    def test_focus_lines_mark_target_and_related_lines_only(self):
        code = 'items = ["<b>"]\nresult = sorted(items)\nprint(result)'
        markup = highlighted_lines(code, {2}, {1, 3, 2})
        self.assertNotIn('<b>', markup)
        self.assertEqual(markup.count('class="code-line selected"'), 1)
        self.assertEqual(markup.count('class="code-line related"'), 2)
        self.assertIn('focus-code', markup)

    def test_concept_markers_flag_only_the_focused_concept(self):
        markup = highlighted_lines('a = 1\nb = sorted(a)\nprint(dict(b))', {3},
                                   markers={2: ['A'], 3: ['B', 'C']}, active='C')
        self.assertEqual(markup.count('class="marker on">C<'), 1)
        self.assertEqual(markup.count('class="marker">B<'), 1)
        self.assertEqual(markup.count('class="marker">A<'), 1)
        self.assertEqual(markup.count('<span class="markers"></span>'), 1)

if __name__ == '__main__':
    unittest.main()
