"""
Thin wrapper around the Groq API (free tier, OpenAI-compatible).

Get a free key at https://console.groq.com/keys
Set it: $env:GROQ_API_KEY="gsk_..."   (PowerShell)
        export GROQ_API_KEY=gsk_...  (bash)

Model is configurable via GROQ_MODEL env var — see
https://console.groq.com/docs/models for the current list. Defaults
to openai/gpt-oss-120b, a strong open-weight model well within the
free tier's rate limits for a project like this. Groq periodically
retires older models — if you get a "model_not_found" 404, check the
docs link above and update the default or set GROQ_MODEL yourself.
"""
from dotenv import load_dotenv
load_dotenv()
import os
import json
import re
from groq import Groq

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq()  # reads GROQ_API_KEY from env
    return _client


def call_json(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> dict:
    """
    Calls the model and parses a JSON object out of the response.
    Strips markdown code fences if the model wraps its JSON in them.
    """
    client = get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # last resort: grab the first {...} blob
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Model did not return valid JSON:\n{text}")
