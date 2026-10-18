"""Langfuse dataset의 각 입력을 prompt 기반 evaluator로 채점하는 예제."""

import json
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from langfuse import Evaluation, get_client
from langfuse.openai import OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

langfuse = get_client()
client = OpenAI()

DATASET_NAME = "bucket_list"
EVALUATION_PROMPT_NAME = "bucket_list_evaluation"


def evaluate_item(*, item, **_kwargs):
    """Dataset item마다 Responses API로 평가 결과를 생성."""
    prompt = langfuse.get_prompt(EVALUATION_PROMPT_NAME)
    # if isinstance(item.input, Mapping):
    #     dataset_input = json.dumps(item.input, ensure_ascii=False)
    # else:
    #     dataset_input = str(item.input)

    response = client.responses.create(
        name="bucket_list_evaluation",
        input=prompt.compile(input=item.input),
        model=prompt.config["model"],
        temperature=prompt.config["temperature"],
        max_output_tokens=prompt.config["max_tokens"],
        text={
            "format": {
                "type": "json_schema",
                "name": "bucket_list_evaluation_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer", "enum": [0, 1]},
                        "reason": {"type": "string"},
                    },
                    "required": ["score", "reason"],
                    "additionalProperties": False,
                },
            }
        },
    )

    return json.loads(response.output_text)


def record_score(*, output, **_kwargs):
    """Task 결과의 0/1 점수를 Langfuse experiment score로 반환."""
    return Evaluation(
        name=EVALUATION_PROMPT_NAME,
        value=output["score"],
        comment=output["reason"],
    )


def main() -> None:
    try:
        dataset = langfuse.get_dataset(DATASET_NAME)
        result = dataset.run_experiment(
            name="bucket_list evaluation",
            description="bucket_list_evaluation prompt로 각 dataset 입력을 0 또는 1로 평가",
            task=evaluate_item,
            evaluators=[record_score]
        )
        print(result.format())
    finally:
        langfuse.flush()


if __name__ == "__main__":
    main()
