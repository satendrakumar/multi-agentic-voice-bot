"""LLM interface shared by all agents, plus JSON-schema helpers.

An LLM is any callable (system, user, schema, effort, model) -> dict | None that
returns a JSON object matching `schema`, or None on failure (callers then use a
fallback line). The backend is chosen with SANIA_LLM:

  openai  any OpenAI-compatible server, e.g. local vLLM (default)  sania/llm/client.py
  claude  Anthropic Claude API                                      sania/llm/claude.py
"""

from typing import Protocol

from sania import config


class LLM(Protocol):
    def __call__(self, system: str, user: str, schema: dict, effort: str, model: str) -> dict | None: ...


def get_llm() -> LLM:
    if config.LLM_BACKEND == "openai":
        from sania.llm.client import LLMClient
        return LLMClient()
    if config.LLM_BACKEND == "claude":
        from sania.llm.claude import call_json
        return call_json
    raise ValueError(f"Unknown SANIA_LLM {config.LLM_BACKEND!r}. Use 'openai' or 'claude'.")


# --- JSON schema helpers -------------------------------------------------------------

def obj(**properties: dict) -> dict:
    """A strict object schema where every property is required."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def enum(*values: str) -> dict:
    return {"type": "string", "enum": list(values)}


STRING = {"type": "string"}
BOOL = {"type": "boolean"}
NUMBER = {"type": "number"}
