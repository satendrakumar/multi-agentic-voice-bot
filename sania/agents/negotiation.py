"""Agent 4 — Negotiation, the core (docs/agents/04-negotiation.md).

Strategy lives in code: `next_move()` picks this turn's move from the call state
(minimum pivot, stall callout, one impact angle, one funds idea, binary date) and
hands the model a plain instruction. The model only reacts to what the caller just
said (agreement, a date, a smaller offer, a side topic) or phrases the move.
Small local models handle this far better than a long strategy prompt.
"""

from sania import prompts
from sania.agents.base import Agent
from sania.llm import BOOL, STRING, enum, nullable, obj
from sania.state import ALL_TOPICS, FUNDS_IDEAS, CallState, Lang

# Best-fitting angle first for each reason (docs: "fit their reason, don't default to सिबिल").
ANGLE_ORDER = {
    "stalling": ["cibil", "card_block", "escalation", "future_credit", "other_products"],
    "refusal": ["cibil", "escalation", "future_credit", "card_block", "other_products"],
    "hardship": ["future_credit", "card_block", "cibil", "other_products", "escalation"],
    "willing": ["card_block", "cibil", "future_credit", "other_products", "escalation"],
}


def next_move(state: CallState) -> tuple[str, str]:
    """(move id, instruction) for this turn. Instruction texts: prompts/<version>/negotiation_moves.toml."""
    moves = prompts.load_toml("negotiation_moves")
    reason = state.reason_class
    if reason == "willing" and "confirm_payment" not in state.questions_asked:
        return "confirm_payment", moves["confirm_payment"]
    if not state.mad_spoken:
        return "pivot_minimum", moves["pivot_minimum"].format(mad=state.profile.spoken()["mad_words"])
    if reason in ("stalling", "unknown") and state.callouts == 0:
        return "callout", moves["callout"]

    angles = [a for a in ANGLE_ORDER.get(reason, ANGLE_ORDER["stalling"]) if a not in state.angles_used]
    funds = [f for f in FUNDS_IDEAS if f not in state.funds_ideas_used]
    funds_first = reason == "hardship"  # hardship: solve the money problem before any consequence
    angle_turn = len(state.angles_used) < len(state.funds_ideas_used) + (0 if funds_first else 1)
    if angles and (angle_turn or not funds):
        return f"angle:{angles[0]}", moves["angle"].format(line=moves["angles"][angles[0]])
    if funds:
        return f"funds:{funds[0]}", moves["funds"][funds[0]]
    return "ask_date", moves["ask_date"]


class NegotiationAgent(Agent):
    name = "negotiation"
    handoffs = ("closing", "dispute", "servicing")
    signals_schema = obj(
        move_done=nullable(STRING),
        commitment=obj(
            amount=nullable(enum("OUT", "MAD")),
            ptp_date=nullable(STRING),
            mode=nullable(STRING),
            firm_today=BOOL,
        ),
        irritated=BOOL,
        topic=nullable(enum(*ALL_TOPICS)),
    )
    fallback_lines = {
        Lang.HINDI: "आज minimum clear कर पाएंगे, हाँ या नहीं.",
        Lang.ENGLISH: "Can you clear the minimum today, yes or no.",
    }

    def extra(self, state: CallState) -> dict:
        move_id, instruction = next_move(state)
        c = state.commitment
        return {
            "reason": state.reason_text or state.reason_class,
            "next_move": {"id": move_id, "do": instruction},
            "commitment_so_far": {"amount": c.amount, "ptp_date": c.ptp_date, "mode": c.mode},
        }
