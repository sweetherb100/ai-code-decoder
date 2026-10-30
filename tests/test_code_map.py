import unittest

from agent.visualization import build_code_map


class CodeMapTests(unittest.TestCase):
    def test_assignments_are_visible_without_any_function_call(self):
        result = build_code_map('price = 100\ncount = 3\ntotal = price * count')
        self.assertEqual(len(result.steps), 3)
        self.assertEqual([s.line for s in result.steps], [1, 2, 3])
        self.assertIn('total', result.dot)

    def test_control_blocks_are_labeled_not_flattened(self):
        result = build_code_map('if ready:\n    print(1)\nelse:\n    print(2)')
        self.assertEqual(len(result.steps), 3)
        self.assertIn('참일 때', result.dot)
        self.assertIn('거짓일 때', result.dot)

    def test_function_body_is_distinguished_from_top_level_execution(self):
        result = build_code_map('def f():\n    return 1\nf()')
        self.assertIn('함수 정의', result.dot)
        self.assertIn('함수 본문', result.dot)

    def test_large_maps_are_bounded_and_report_omission(self):
        result = build_code_map('\n'.join(f'x{i} = {i}' for i in range(50)))
        self.assertLessEqual(len(result.steps), 16)
        self.assertGreater(result.omitted, 0)

    def test_quotes_are_dot_escaped_and_selected_node_is_highlighted(self):
        result = build_code_map('print("hello")', selected=0)
        self.assertIn('fillcolor="#e6ecfa"', result.dot)
        self.assertIn('\\"hello\\"', result.dot)

    def test_exception_group_handler_is_not_omitted(self):
        result = build_code_map('try:\n    work()\nexcept* ValueError:\n    recover()')
        self.assertEqual(len(result.steps), 3)
        self.assertEqual(result.omitted, 0)
        self.assertIn('예외 · ValueError', result.dot)
