"""Claude API backend: one system prompt in, one JSON object out."""

import json
import logging

import anthropic

from sania import config

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def call_json(system: str, user: str, schema: dict, effort: str = "low",
              model: str = config.MODEL) -> dict | None:
    """Return the model's JSON answer, or None on any failure (callers use a fallback line)."""
    output_config = {"format": {"type": "json_schema", "schema": schema}}
    extra = {}
    if "haiku" not in model:  # Haiku 4.5 supports neither effort nor server-side fallbacks
        output_config["effort"] = effort
        # If a safety classifier declines, retry on a fallback model in the same call.
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        response = _get_client().beta.messages.create(
            model=model,
            max_tokens=config.MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config=output_config,
            **extra,
        )
    except anthropic.APIConnectionError as e:
        log.error("Claude API unreachable: %s", e)
        return None
    except anthropic.APIStatusError as e:
        log.error("Claude API error %s: %s", e.status_code, e.message)
        return None

    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("No usable answer (stop_reason=%s)", response.stop_reason)
        return None

    text = next((b.text for b in response.content if b.type == "text"), None)
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        log.warning("Model returned invalid JSON: %r", text)
        return None
