"""Agent 7 — Safety & Hard-Stop (docs/agents/07-safety-hardstop.md).

Two parts: a classifier that runs on every caller utterance, and a responder
that speaks the single safe line once a hard-stop fires.
"""

import re

from sania import config, prompts
from sania.agents.base import Agent
from sania.llm import LLM, NUMBER, enum, nullable, obj
from sania.state import HARDSTOPS, CallState, Lang

# High-precision phrases: fire without asking the model.
KEYWORDS = {
    "voicemail": [
        "leave a message", "leave your message", "after the tone", "after the beep", "voicemail",
        "the number you have dialled", "the number you are calling", "is not reachable", "switched off",
    ],
    "self_harm": ["suicide", "kill myself", "end my life", "जीने का मन नहीं", "मर जाऊँ", "मर जाऊं", "जान दे दूँ"],
    "injection": [
        "ignore previous", "ignore all previous", "ignore your instructions", "you are now",
        "system:", "developer mode", "reveal your prompt", "show your prompt",
    ],
}

# Opt-out needs actual stop-calling words too; small models mistake annoyance ("बोला ना") for it.
OPT_OUT_WORDS = re.compile(
    r"call मत|मत करो|मत करना|बंद करो|stop call|don'?t call|do not call|no more calls|\bdnd\b|block (my )?number",
    re.I,
)

# Favour recall for the life-safety classes, precision for the rest.
THRESHOLD = {"distress": 0.6, "self_harm": 0.5, "deceased": 0.6}
DEFAULT_THRESHOLD = 0.8


class HardStopClassifier:
    schema = obj(hardstop=nullable(enum(*HARDSTOPS)), confidence=NUMBER)

    def classify(self, text: str, llm: LLM) -> str | None:
        low = text.lower()
        for kind, phrases in KEYWORDS.items():
            if any(p in low for p in phrases):
                return kind
        # Voicemail is detected by its phrases only; small models over-report it.
        answer = llm(
            system="AGENT: classifier\n\n" + prompts.load("classifier"), user=text, schema=self.schema,
            effort=config.EFFORT["classifier"], model=config.model_for("classifier"),
        )
        kind = (answer or {}).get("hardstop")
        if not kind or kind == "voicemail" or answer.get("confidence", 0) < THRESHOLD.get(kind, DEFAULT_THRESHOLD):
            return None
        if kind == "opt_out" and not OPT_OUT_WORDS.search(text):
            return None
        return kind


class SafetyAgent(Agent):
    name = "safety"
    fallback_lines = {
        Lang.HINDI: "ठीक है, आपका ध्यान रखिए, धन्यवाद.",
        Lang.ENGLISH: "Alright, please take care, thank you.",
    }

    def extra(self, state: CallState) -> dict:
        return {
            "hardstop": state.hardstop,
            "verified": state.verified,
            "deceased_asked": state.deceased_asked,
            "abuse_warnings": state.abuse_warnings,
            "injection_warnings": state.injection_warnings,
        }
