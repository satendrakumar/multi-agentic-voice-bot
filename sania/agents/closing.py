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
    instructions = """
ROLE: Close the call for the given "close_type".
- committed: briefly note it WITHOUT repeating the amount, date or mode. If they asked how to pay, point to their app,
  net banking or customer care (do not read menus).
- no_commitment: one short neutral line, no push.
- irritated: one short apology and ask them to try to pay at the earliest. No question. end_call true.
For committed and no_commitment: if "help_asked" is false, ask once whether they need any other help (asked_help true,
end_call false). If "help_asked" is true and they need nothing else, give a short thank you statement with no question,
end_call true. Never ask whether you may end the call. Never re-open the negotiation.
If they raise a new issue, set topic, speech empty, and handoff "dispute" (dispute, settlement, waiver, EMI, charges,
statement) or "servicing" (already paid, account block, card block, busy, supervisor and similar).
"""

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
