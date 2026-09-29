from datetime import date

import pytest

from sania.state import Profile


@pytest.fixture
def profile():
    return Profile(
        name="Rahul", card_name="Millennia", card_last4="1234", out=70000, mad=3500,
        due_date=date(2026, 9, 15), today=date(2026, 9, 29), name_dev="राहुल",
    )


class FakeLLM:
    """Scripted stand-in for the Claude API. Replies are queued per agent name."""

    def __init__(self):
        self.replies: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []

    def add(self, agent: str, speech: str = "", signals: dict | None = None,
            handoff: str | None = None, end_call: bool = False):
        self.replies.setdefault(agent, []).append(
            {"speech": speech, "signals": signals or {}, "handoff": handoff, "end_call": end_call}
        )

    def __call__(self, system: str, user: str, schema: dict, effort: str, model: str):
        agent = system.split("\n", 1)[0].removeprefix("AGENT: ").strip()
        self.calls.append((agent, user))
        if agent == "classifier":
            queue = self.replies.get("classifier")
            return queue.pop(0) if queue else {"hardstop": None, "confidence": 0.0}
        queue = self.replies.get(agent)
        return queue.pop(0) if queue else None


@pytest.fixture
def fake_llm():
    return FakeLLM()
