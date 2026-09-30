"""Agent 6 — Servicing / Special Cases (docs/agents/06-servicing-special-cases.md)."""

from sania.agents.base import Agent
from sania.llm import STRING, enum, nullable, obj
from sania.prompts import SUPPORT
from sania.state import SERVICING_TOPICS, CallState, Lang


class ServicingAgent(Agent):
    name = "servicing"
    handoffs = ("negotiation", "closing")
    signals_schema = obj(
        topic=nullable(enum(*SERVICING_TOPICS)),
        question_intent=nullable(STRING),
    )
    fallback_lines = {
        Lang.HINDI: "जी, इसके लिए customer care best help करेगा, धन्यवाद.",
        Lang.ENGLISH: "Customer care will best help you with this, thank you.",
    }

    def extra(self, state: CallState) -> dict:
        return {
            "topic": state.topic,
            "support": SUPPORT,
            "mad_spoken": state.mad_spoken,
            "return_to": "closing" if state.help_asked else "negotiation",
        }
