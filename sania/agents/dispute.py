"""Agent 5 — Dispute & Levers (docs/agents/05-dispute-levers.md)."""

from sania.agents.base import Agent
from sania.llm import BOOL, STRING, enum, nullable, obj
from sania.prompts import SUPPORT
from sania.state import DISPUTE_TOPICS, CallState, Lang


class DisputeAgent(Agent):
    name = "dispute"
    handoffs = ("negotiation", "closing")
    signals_schema = obj(
        topic=nullable(enum(*DISPUTE_TOPICS)),
        dispute_scope=nullable(enum("partial", "whole")),
        support_shared=BOOL,
        question_intent=nullable(STRING),
    )
    fallback_lines = {
        Lang.HINDI: "इसे customer care best handle करेगा, तब तक minimum आज clear कर दीजिए.",
        Lang.ENGLISH: "Customer care will best handle this, meanwhile please clear the minimum today.",
    }

    def extra(self, state: CallState) -> dict:
        return {
            "topic": state.topic,
            "support": SUPPORT,
            "support_shared": state.support_shared,
            "mad_spoken": state.mad_spoken,
            "return_to": "closing" if state.help_asked else "negotiation",
        }
