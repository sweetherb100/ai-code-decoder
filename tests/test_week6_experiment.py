"""Experiment CLI and generation provenance checks."""

import json

import pytest


def test_decoder_exposes_actual_prompt_and_usage(fake_openai, stub_docs, span_exporter):
    from agent.decoder import decode_code

    execution = decode_code("value = 1", "Beginner")
    assert execution.run_metadata["promptVersion"].startswith("fallback-")
    assert execution.run_metadata["model"] == "gpt-4.1-mini"
    assert execution.usage["requests"] == 2
    assert execution.usage["total_tokens"] == 2560


def test_no_overwrite_of_saved_result(tmp_path):
    from evals.week6.reporting import save_artifact

    target = tmp_path / "result.json"
    save_artifact(target, {"sentinel": 1})
    with pytest.raises(FileExistsError):
        save_artifact(target, {"sentinel": 2})
    assert json.loads(target.read_text()) == {"sentinel": 1}


def test_managed_dataset_refuses_unapproved_content_before_writes():
    from evals.week6.dataset import load_cases
    from evals.week6.langfuse_runner import sync_dataset

    case = load_cases()[0].model_copy(update={"code": "PRIVATE_CUSTOM_CODE"})
    with pytest.raises(ValueError, match="shipped"):
        sync_dataset(None, [case])


def test_cli_validate_needs_no_keys_or_network():
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith(("OPENAI", "LANGFUSE"))}
    completed = subprocess.run(
        [sys.executable, "scripts/week6/run_eval.py", "validate"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["cases"] == 24
    assert output["splits"] == {"dev": 16, "holdout": 8}


def test_cli_budget_error_does_not_create_output(tmp_path):
    import subprocess
    import sys

    output = tmp_path / "run.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/week6/run_eval.py",
            "run",
            "--name",
            "test",
            "--output",
            str(output),
            "--max-requests",
            "0",
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "budget" in completed.stderr
    assert not output.exists()


def test_manifest_uses_repository_identity_when_called_from_elsewhere(tmp_path, monkeypatch):
    import importlib.util
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("week6_cli", root / "scripts/week6/run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    monkeypatch.chdir(tmp_path)
    assert module._manifest()["commit"] == expected
