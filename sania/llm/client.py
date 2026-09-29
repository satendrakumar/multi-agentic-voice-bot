"""Generic LLM client using the standard OpenAI SDK.

Works with any OpenAI-compatible server: local vLLM (default, Qwen/Qwen3.5-4B on
http://localhost:8000/v1), OpenAI, or others. Set SANIA_LLM_BASE_URL / SANIA_MODEL.

JSON is requested with `response_format` json_schema (vLLM enforces it with
structured outputs). The schema is also written into the prompt and the reply is
parsed leniently, in case a server ignores the constraint.
"""

import json
import logging
import re

import openai

from sania import config

log = logging.getLogger(__name__)


def parse_json(text: str | None, schema: dict) -> dict | None:
    """Extract the JSON object from a reply (ignoring thinking and code fences) and check its keys."""
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or any(key not in data for key in schema.get("required", [])):
        return None
    return data


class LLMClient:
    def __init__(self, base_url: str = config.LLM_BASE_URL, api_key: str = config.LLM_API_KEY):
        self.client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=60.0, max_retries=1)

    def __call__(self, system: str, user: str, schema: dict, effort: str = "low",
                 model: str = config.MODEL) -> dict | None:
        """`effort` is not used by OpenAI-compatible servers."""
        system += "\n\nReply with ONLY one JSON object that matches this JSON schema:\n" + json.dumps(schema)
        extra_body = {}
        if config.LLM_THINKING is not None:  # Qwen chat-template switch, understood by vLLM
            extra_body["chat_template_kwargs"] = {"enable_thinking": config.LLM_THINKING}
        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=config.LLM_MAX_TOKENS,
                temperature=0.7,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "reply", "schema": schema, "strict": True},
                },
                extra_body=extra_body or None,
                stream=True,
            )
            # The whole JSON is needed before anything is spoken: the guard checks it first.
            text = "".join(chunk.choices[0].delta.content or "" for chunk in stream if chunk.choices)
        except openai.APIConnectionError as e:
            log.error("LLM server unreachable at %s: %s", self.client.base_url, e)
            return None
        except openai.APIStatusError as e:
            log.error("LLM server error %s: %s", e.status_code, e.message)
            return None

        data = parse_json(text, schema)
        if data is None:
            log.warning("LLM returned no valid JSON: %r", text)
        return data
