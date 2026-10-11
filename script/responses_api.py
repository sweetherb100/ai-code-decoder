import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
load_dotenv(Path(__file__).parent.parent / ".env")

client = OpenAI()

response = client.responses.create(
    model="gpt-4.1-mini",
    instructions="간결하고 정확하게 답하세요.",
    input="Responses API를 한 문장으로 설명해줘.",
)

print(response.output_text)