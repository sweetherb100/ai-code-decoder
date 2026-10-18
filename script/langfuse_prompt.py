"""Langfuse text prompt를 불러와 Responses API에 사용하는 예제."""

from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client
from langfuse.openai import OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

langfuse = get_client()
client = OpenAI()

prompt_name = "three_line_poem_prompt"
word = "코코넛"

def main() -> None:
    prompt = langfuse.get_prompt(prompt_name)

    # Langfuse OpenAI wrapper의 Responses API 자동 추적
    response = client.responses.create(
        name="three_line_poem",
        input=prompt.compile(word=word),
        model=prompt.config["model"],
        temperature=prompt.config["temperature"],
        max_output_tokens=prompt.config["max_tokens"],
        text={
            "format": {
                "type": "json_schema",
                "name": "three_line_poem_schema",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "line1": {"type": "string"},
                        "line2": {"type": "string"},
                        "line3": {"type": "string"},
                    },
                    "required": ["line1", "line2", "line3"],
                    "additionalProperties": False,
                },
            }
        },
    )
    print(response.output_text)
    langfuse.flush()


if __name__ == "__main__":
    main()
