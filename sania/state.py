"""Call state shared by all agents. Only the Orchestrator writes to it."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from sania.numbers import date_words, digit_words, money_words


class Stage(str, Enum):
    IDENTITY = "identity"
    DISCLOSURE = "disclosure"
    REASON = "reason"
    NEGOTIATION = "negotiation"
    DISPUTE = "dispute"
    SERVICING = "servicing"
    SAFETY = "safety"
    CLOSING = "closing"
    END = "end"


class Lang(str, Enum):
    HINDI = "HINDI"
    ENGLISH = "ENGLISH"


IMPACT_ANGLES = ["cibil", "card_block", "future_credit", "escalation", "other_products"]
FUNDS_IDEAS = ["savings_family", "alt_mode", "salary_anchor"]

REASON_CLASSES = [
    "firm_today", "willing", "hardship", "stalling", "refusal",
    "wrong_amount", "statement_not_received", "unknown",
]
DISPUTE_TOPICS = ["wrong_amount", "settlement", "waiver", "emi", "unknown_figure", "statement"]
SERVICING_TOPICS = [
    "already_paid", "account_block", "card_block", "no_card", "phone_mismatch",
    "third_party_card", "followups", "busy", "supervisor", "human_or_ai",
]
ALL_TOPICS = DISPUTE_TOPICS + SERVICING_TOPICS
HARDSTOPS = ["distress", "self_harm", "deceased", "abuse", "opt_out", "injection", "voicemail"]


@dataclass
class Profile:
    """Customer data from the dialler. Read-only during the call."""

    name: str
    card_name: str
    card_last4: str
    out: float
    mad: float
    due_date: date
    today: date
    name_dev: str | None = None  # Devanagari name; filled by the language manager

    def spoken(self) -> dict:
        """Account values already converted to spoken words."""
        return {
            "card_name": self.card_name,
            "card_last4_words": digit_words(self.card_last4),
            "out_words": money_words(self.out),
            "mad_words": money_words(self.mad),
            "due_date_words": date_words(self.due_date),
            "today": self.today.isoformat(),
        }


@dataclass
class Commitment:
    amount: str | None = None      # "OUT" or "MAD" — never a number
    ptp_date: str | None = None    # ISO date
    mode: str | None = None
    firm_today: bool = False

    def complete(self) -> bool:
        return self.firm_today or bool(self.amount and self.ptp_date and self.mode)


@dataclass
class CallState:
    profile: Profile
    stage: Stage = Stage.IDENTITY
    prev_stage: Stage | None = None
    turn_no: int = 0                     # bot turns spoken so far

    verified: bool = False
    identity_reasks: int = 0

    language: Lang = Lang.HINDI
    language_locked: bool = False
    language_votes: int = 0             # caller replies long enough to show a language

    reason_class: str = "unknown"
    reason_text: str | None = None
    reason_asked: bool = False

    ask_level: str = "OUT"               # OUT -> MAD -> DATE
    out_spoken: bool = False
    mad_spoken: bool = False
    angles_used: list[str] = field(default_factory=list)
    angles_deepened: list[str] = field(default_factory=list)
    funds_ideas_used: list[str] = field(default_factory=list)
    callouts: int = 0
    ptp_history: list[str] = field(default_factory=list)
    questions_asked: list[str] = field(default_factory=list)
    commitment: Commitment = field(default_factory=Commitment)
    negotiation_turns: int = 0

    topic: str | None = None             # side topic for dispute / servicing
    support_shared: bool = False

    hardstop: str | None = None
    abuse_warnings: int = 0
    injection_warnings: int = 0
    deceased_asked: bool = False

    silence_count: int = 0
    bad_audio_retries: int = 0

    irritated: bool = False
    help_asked: bool = False
    closing_turns: int = 0

    transcript: list[dict] = field(default_factory=list)   # {"role", "text"}

    @property
    def ended(self) -> bool:
        return self.stage == Stage.END

    def remaining(self, options: list[str], used: list[str]) -> list[str]:
        return [o for o in options if o not in used]
