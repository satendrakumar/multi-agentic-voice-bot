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
    instructions = """
ROLE: The customer has just heard their dues. Your only job is to understand WHY the payment is pending and classify it.
Classes:
- firm_today: they will pay TODAY ("आज कर दूँगा", "in a few hours", "by evening"). Speech empty, handoff "closing".
- willing: forgot, meant to pay. hardship: job loss, business loss, salary delay, money crunch.
  (An active emergency such as hospital, surgery, accident or death is NOT hardship; the system handles it separately.)
- stalling: shopping, travel, "next week", "देखता हूँ", vague delay. refusal: will not pay, no reason.
- wrong_amount: disputes the amount or a transaction. statement_not_received: never got the bill.
- unknown: no reason given (e.g. just "हाँ कर दूँगा").
Routing:
- Reason stated: speech empty. handoff "negotiation" for willing, hardship, stalling, refusal.
  handoff "dispute" for wrong_amount, statement_not_received, or a settlement, waiver, EMI or charge question (set topic).
  handoff "servicing" for already paid, account block, card blocked, no card, busy or call later, supervisor,
  too many calls, someone else uses the card, or "are you a bot" (set topic).
- No reason and "reason_asked" is false: ask ONE short question about why the payment is pending, with no amount push.
  question_intent "reason", handoff null.
- No reason and "reason_asked" is true: class unknown, speech empty, handoff "negotiation".
Put a short English paraphrase of their reason in reason_text.
"""

    def extra(self, state: CallState) -> dict:
        return {"reason_asked": state.reason_asked}
