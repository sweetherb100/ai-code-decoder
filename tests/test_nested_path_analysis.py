"""Inline constructor methods must retain their official documentation target."""

import pytest

from agent.analyzer import analyze_code
from agent.planner import build_learning_plan


@pytest.mark.parametrize(
    "prefix,call",
    [
        ("from pathlib import Path", "Path"),
        ("from pathlib import Path as P", "P"),
        ("import pathlib as p", "p.Path"),
    ],
)
def test_inline_path_method_is_resolved_and_ordered_before_consumer(prefix, call):
    analysis = analyze_code(f'{prefix}\nfiles = sorted({call}("images").glob("*.png"))')
    target = next(t for t in analysis.learning_targets if t.symbol == "Path.glob")
    assert target.module == "pathlib"
    assert target.resolution == "resolved"
    assert target.used_as_input_of == "sorted"
    assert ".glob(" in target.expression
    plan = build_learning_plan(analysis.learning_targets, analysis.syntax, "Beginner")
    assert plan.primary_targets[0].target_id == target.target_id


def test_unknown_constructor_is_not_claimed_as_pathlib():
    analysis = analyze_code('from private_lib import Path\nPath("x").glob("*")')
    assert not any(t.module == "pathlib" for t in analysis.learning_targets)


@pytest.mark.parametrize(
    "binding", ["Path = factory", 'def f(Path):\n    return Path("x").glob("*")']
)
def test_rebound_path_constructor_does_not_get_new_inline_resolution(binding):
    analysis = analyze_code("from pathlib import Path\n" + binding + '\nPath("x").glob("*")')
    assert not any(
        t.symbol == "Path.glob" and t.module == "pathlib" for t in analysis.learning_targets
    )


def test_factory_attribute_is_not_a_path_constructor():
    analysis = analyze_code('from pathlib import Path\nfactory().Path("x").glob("*")')
    assert not any(t.symbol == "Path.glob" for t in analysis.learning_targets)
