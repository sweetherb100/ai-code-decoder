"""Configure managed Langfuse evaluation, generate experiments, then collect scores."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.week6.dataset import dataset_digest, digest, load_cases
from evals.week6.managed import (
    DEFAULT_JUDGES,
    evaluator_definitions,
    resume_setup,
    setup_evaluators,
    verify_setup,
)
from evals.week6.reporting import compare_runs, save_artifact, summarize


def build_parser() -> argparse.ArgumentParser:
    """Keep remote setup, generation and read-only collection explicit."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="오프라인 데이터셋·평가 설정 검사")
    setup = commands.add_parser(
        "setup", help="Langfuse 평가자·규칙 생성 (모델 연결 검사 비용 가능)"
    )
    setup.add_argument("--output", type=Path, required=True)
    setup.add_argument("--provider", default="openai")
    setup.add_argument("--environment", required=True)
    setup.add_argument("--primary-model", default=DEFAULT_JUDGES[0])
    setup.add_argument("--secondary-model", default=DEFAULT_JUDGES[1])
    setup.add_argument("--env-file", type=Path)
    resume = commands.add_parser("resume-setup", help="중단된 설정을 서버와 대조하여 재개")
    resume.add_argument("--setup", type=Path, required=True)
    resume.add_argument("--env-file", type=Path)
    for name in ("run", "controls"):
        run = commands.add_parser(name, help="앱/고정 답변 실험 실행; 서버에서 비동기 채점")
        run.add_argument("--name", required=True)
        run.add_argument("--output", required=True, type=Path)
        run.add_argument("--setup", type=Path)
        run.add_argument(
            "--max-requests",
            type=int,
            default=32,
            help="예상 기본 호출 수 예산; 서버 재시도/수동 규칙은 별도",
        )
        run.add_argument("--env-file", type=Path)
        if name == "run":
            run.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
            run.add_argument("--limit", type=int, default=4)
            run.add_argument("--case", action="append", default=[], dest="case_ids")
            run.add_argument("--prompt-label")
            run.add_argument("--generation-model")
    collect = commands.add_parser("collect", help="기존 실행 점수만 조회; 모델 호출 없음")
    collect.add_argument("artifact", type=Path)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--env-file", type=Path)
    usage = commands.add_parser("usage", help="judge 실행 trace의 토큰·추정 비용 조회")
    usage.add_argument("artifact", type=Path)
    usage.add_argument("--output", type=Path, required=True)
    usage.add_argument("--env-file", type=Path)
    compare = commands.add_parser("compare", help="완료된 두 실행의 변화 비교")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path)
    return parser


def _client(args: argparse.Namespace, *, environment: str | None = None):
    if args.env_file:
        from dotenv import load_dotenv

        if not args.env_file.is_file():
            raise ValueError("env file does not exist")
        load_dotenv(args.env_file, override=False)
    if not all(
        os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
    ):
        raise ValueError("Langfuse credentials and base URL required")
    os.environ.update(LANGFUSE_ENABLED="1", LANGFUSE_SAMPLE_RATE="1", LANGFUSE_CAPTURE_CONTENT="0")
    os.environ.setdefault("LANGFUSE_TIMEOUT", "60")
    if environment:
        os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = environment
    from agent.observability import init_observability, prompt_client

    init_observability()
    client = prompt_client()
    if client is None:
        raise RuntimeError("Langfuse initialization failed")
    return client


def _new_path(path: Path) -> None:
    if path.exists() or path.with_suffix(".partial.jsonl").exists():
        raise FileExistsError("choose a new output path; existing run/setup is preserved")


def execute(args: argparse.Namespace) -> int:
    """Generate only; a separate collection command confirms server score completion."""
    from evals.week6.controls import load_controls, run_control
    from evals.week6.experiment import run_case, validate_run
    from evals.week6.langfuse_runner import run_experiment, sync_dataset
    from evals.week6.models import EvalCase

    controls = load_controls() if args.command == "controls" else []
    if controls:
        cases = [EvalCase.model_validate(c["case"]) for c in controls]
    else:
        if args.limit <= 0:
            raise ValueError("limit must be positive")
        all_cases = load_cases()
        if set(args.case_ids) - {c.case_id for c in all_cases}:
            raise ValueError("unknown case ID")
        cases = [
            c
            for c in all_cases
            if (args.split == "all" or c.split == args.split)
            and (not args.case_ids or c.case_id in args.case_ids)
        ][: args.limit]
    try:
        budget = validate_run(
            cases,
            list(DEFAULT_JUDGES),
            max_requests=args.max_requests,
            generation=not bool(controls),
        )
    except ValueError:
        print("사례 또는 예상 호출 예산(budget)을 확인하세요.", file=sys.stderr)
        return 1
    _new_path(args.output)
    if not args.setup:
        raise ValueError("--setup is required; run setup first")
    lock = json.loads(args.setup.read_text())
    if getattr(args, "prompt_label", None):
        os.environ["LANGFUSE_PROMPT_LABEL"] = args.prompt_label
    if getattr(args, "generation_model", None):
        os.environ["OPENAI_MODEL"] = args.generation_model
    client = _client(args, environment=lock["environment"])
    verify_setup(client, lock)
    if not controls and not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required for app generation")
    if not controls:
        from agents import set_default_openai_client
        from openai import AsyncOpenAI

        set_default_openai_client(AsyncOpenAI(max_retries=0, timeout=90))
    artifact = {
        "schema_version": 2,
        "run_name": f"{args.name}-{uuid4().hex[:12]}",
        "suite": args.command,
        "started_at": datetime.now(UTC).isoformat(),
        "manifest": _manifest(),
        "setup": lock,
        "protocol": {
            "dataset_hash": dataset_digest(cases),
            "setup": lock,
            "controls_hash": digest(controls) if controls else None,
        },
        "planned_base_requests": budget,
        "expected_cases": len(cases),
        "records": [],
        "status": "pending",
        "experiment_id": None,
        "experiment_url": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_suffix(".partial.jsonl").open("x", encoding="utf-8") as journal:
        journal.write(json.dumps({"header": artifact}, ensure_ascii=False) + "\n")
        journal.flush()

        def append(record):
            artifact["records"].append(record)
            journal.write(json.dumps(record, ensure_ascii=False) + "\n")
            journal.flush()

        by_id = {c["case"]["case_id"]: c for c in controls}

        def execute_case(case):
            return run_control(by_id[case.case_id]) if controls else run_case(case)

        try:
            result, _ = run_experiment(
                client,
                cases,
                run_name=artifact["run_name"],
                data=sync_dataset(client, cases, controls=bool(controls)),
                metadata={"evaluationProtocol": lock["protocol"]},
                on_record=append,
                execute_case=execute_case,
            )
            artifact.update(
                experiment_id=result.experiment_id, experiment_url=result.experiment_url
            )
        except Exception as exc:
            # The boundary persists partial progress without exposing raw SDK errors.
            artifact.update(status="error", generation_error=type(exc).__name__)
        finally:
            artifact["finished_at"] = datetime.now(UTC).isoformat()
            artifact["summary"] = summarize(artifact["records"])
            save_artifact(args.output, artifact)
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "output": str(args.output),
                "experiment_url": artifact["experiment_url"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if artifact["status"] == "error" else 0


def _manifest() -> dict:
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    root = Path(__file__).resolve().parents[2]
    # Include uncommitted source in the identity: HEAD alone is not enough.
    files = sorted(
        p
        for folder in ("agent", "evals/week6", "scripts/week6")
        for p in (root / folder).glob("*")
        if p.suffix in (".py", ".md", ".json", ".jsonl")
    )
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "source_hash": digest({str(p.relative_to(root)): p.read_text() for p in files}),
        "python": sys.version.split()[0],
        "packages": {
            n: importlib.metadata.version(n) for n in ("openai", "langfuse", "openai-agents")
        },
    }


def main() -> int:
    """Dispatch explicit setup, generation and collection operations."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "validate":
            cases = load_cases()
            definitions = evaluator_definitions(list(DEFAULT_JUDGES), "openai")
            print(
                json.dumps(
                    {
                        "cases": len(cases),
                        "dataset_hash": dataset_digest(cases),
                        "splits": dict(Counter(c.split for c in cases)),
                        "evaluators": [
                            d.model_dump(mode="json", by_alias=True) for d in definitions
                        ],
                    }
                )
            )
            return 0
        if args.command == "compare":
            result = compare_runs(
                json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text())
            )
            if args.output:
                save_artifact(args.output, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "resume-setup":
            lock = json.loads(args.setup.read_text())

            def persist_recovered(value):
                temporary = args.setup.with_suffix(".tmp")
                temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
                temporary.replace(args.setup)

            lock = resume_setup(_client(args), lock, on_progress=persist_recovered)
            print(json.dumps({"status": lock["status"], "setup": str(args.setup)}))
            return 0
        if args.command == "setup":
            _new_path(args.output)
            client = _client(args)
            # Reserve the path before remote writes. A failed setup is never retried
            # invisibly: its journal identifies created resources for inspection.
            save_artifact(args.output, {"status": "creating"})

            def persist(lock):
                temporary = args.output.with_suffix(".tmp")
                temporary.write_text(json.dumps(lock, ensure_ascii=False, indent=2))
                temporary.replace(args.output)

            lock = setup_evaluators(
                client,
                [args.primary_model, args.secondary_model],
                args.provider,
                args.environment,
                protocol=uuid4().hex,
                on_progress=persist,
            )
            print(
                json.dumps(
                    {
                        "status": lock["status"],
                        "output": str(args.output),
                        "LANGFUSE_EVALUATION_PROTOCOL": lock["protocol"],
                    }
                )
            )
            return 0
        if args.command == "usage":
            from evals.week6.usage import collect_usage

            _new_path(args.output)
            result = collect_usage(_client(args), json.loads(args.artifact.read_text()))
            save_artifact(args.output, result)
            print(json.dumps({k: v for k, v in result.items() if k != "observations"}))
            return 0
        if args.command == "collect":
            from evals.week6.collection import collect_once

            _new_path(args.output)
            artifact = json.loads(args.artifact.read_text())
            result = collect_once(_client(args), artifact, artifact["setup"])
            result["summary"] = summarize(result["records"])
            save_artifact(args.output, result)
            print(
                json.dumps(
                    {"status": result["status"], "summary": result["summary"]}, ensure_ascii=False
                )
            )
            return 0 if result["status"] == "complete" else 2
        return execute(args)
    except (ValueError, FileExistsError) as exc:
        # Only local validation errors should be presented verbatim.
        print(f"평가 설정 오류: {type(exc).__name__}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"평가 실행 실패: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
