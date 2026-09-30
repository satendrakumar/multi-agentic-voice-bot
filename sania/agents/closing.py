"""Agent 8 — Closing (docs/agents/08-closing.md)."""

from sania.agents.base import Agent
from sania.llm import BOOL, enum, nullable, obj
from sania.state import ALL_TOPICS, CallState, Lang


class ClosingAgent(Agent):
    name = "closing"
    handoffs = ("dispute", "servicing")
    signals_schema = obj(
        asked_help=BOOL,
        topic=nullable(enum(*ALL_TOPICS)),
    )
    fallback_lines = {
        Lang.HINDI: "ठीक है, धन्यवाद {name} जी, आपका दिन शुभ हो.",
        Lang.ENGLISH: "Alright, thank you {name} जी, have a good day.",
    }

    def validate(self, speech: str, state: CallState) -> list[str]:
        low = speech.lower()
        mode = (state.commitment.mode or "\u0000").lower()
        if mode in low or state.profile.spoken()["mad_words"] in low:
            return ["Do not repeat the commitment (amount, date or mode) back to the caller."]
        return []

    def extra(self, state: CallState) -> dict:
        if state.irritated:
            close_type = "irritated"
        elif state.commitment.complete():
            close_type = "committed"
        else:
            close_type = "no_commitment"
        return {"close_type": close_type, "help_asked": state.help_asked}
