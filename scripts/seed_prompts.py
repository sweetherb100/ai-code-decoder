"""Create a new version of the system prompt in Langfuse from the local template.

The new version only gets the `staging` label. Promote it to `production` in the
Langfuse UI after checking docs/quality-evaluation.md; roll back by moving the
`production` label to an earlier version. This script never touches production.

Usage:
    python scripts/seed_prompts.py --message "describe the change"
    python scripts/seed_prompts.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.prompts import (  # noqa: E402
    LOCAL_PROMPT_CONFIG,
    LOCAL_PROMPT_VERSION,
    LOCAL_SYSTEM_PROMPT_TEMPLATE,
    PROMPT_NAME,
)

LABEL = "staging"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--message", default=f"seed from local template ({LOCAL_PROMPT_VERSION})")
    parser.add_argument("--dry-run", action="store_true", help="print what would be created")
    args = parser.parse_args()

    print(f"prompt: {PROMPT_NAME}  label: {LABEL}  local: {LOCAL_PROMPT_VERSION}")
    print(f"config: {json.dumps(LOCAL_PROMPT_CONFIG, ensure_ascii=False)}")
    if args.dry_run:
        print(LOCAL_SYSTEM_PROMPT_TEMPLATE)
        return 0

    load_dotenv()
    from langfuse import Langfuse

    client = Langfuse(tracing_enabled=False)
    created = client.create_prompt(
        name=PROMPT_NAME,
        type="text",
        prompt=LOCAL_SYSTEM_PROMPT_TEMPLATE,
        config=LOCAL_PROMPT_CONFIG,
        labels=[LABEL],
        commit_message=args.message,
    )
    print(f"created version {created.version} with label '{LABEL}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
