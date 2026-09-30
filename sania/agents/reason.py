"""Agent 3 — Reason Discovery & Classification (docs/agents/03-reason-discovery.md)."""

from sania.agents.base import Agent
from sania.llm import STRING, enum, nullable, obj
from sania.state import ALL_TOPICS, REASON_CLASSES, CallState, Lang


class ReasonAgent(Agent):
    name = "reason"
    handoffs = ("negotiation", "dispute", "servicing", "closing")
    signals_schema = obj(
        reason_class=enum(*REASON_CLASSES),
        reason_text=nullable(STRING),
        topic=nullable(enum(*ALL_TOPICS)),
        question_intent=nullable(STRING),
    )
    fallback_lines = {
        Lang.HINDI: "जी, payment अब तक pending क्यों रह गया.",
        Lang.ENGLISH: "May I know why the payment is still pending.",
    }

    def extra(self, state: CallState) -> dict:
        return {"reason_asked": state.reason_asked}
