"""Agent 2 — Account Disclosure (docs/agents/02-account-disclosure.md)."""

from sania.agents.base import Agent
from sania.state import CallState, Lang


class DisclosureAgent(Agent):
    name = "disclosure"
    handoffs = ("reason",)
    fallback_lines = {
        Lang.HINDI: (
            "जी, मैं सानिया HDFC Bank collections से recorded line पर बात कर रही हूँ, आपके {card_name} "
            "credit card ending {card_last4_words} पे {out_words} का payment {due_date_words} से due है, "
            "आज pay कर पाएंगे."
        ),
        Lang.ENGLISH: (
            "I am Sania from HDFC Bank collections on a recorded line, your {card_name} credit card ending "
            "{card_last4_words} has {out_words} due since {due_date_words}, can you pay it today."
        ),
    }

    def fallback(self, state: CallState) -> str:
        return self.fallback_lines[state.language].format(**state.profile.spoken())

    def extra(self, state: CallState) -> dict:
        return {"example": self.fallback(state)}

    def validate(self, speech: str, state: CallState) -> list[str]:
        low = speech.lower()
        spoken = state.profile.spoken()
        required = {
            "your name": "सानिया" in speech or "sania" in low,
            "HDFC": "hdfc" in low,
            "the words recorded line": "recorded line" in low,
            "the card last four digits": spoken["card_last4_words"] in low,
            "the outstanding amount": spoken["out_words"] in low,
            f"the due date in English words ({spoken['due_date_words']})": spoken["due_date_words"].lower() in low,
        }
        return [f"Disclosure must include {what}." for what, ok in required.items() if not ok]
