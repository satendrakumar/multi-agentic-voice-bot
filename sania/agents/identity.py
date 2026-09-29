"""Agent 1 — Greeting & Identity Verification (docs/agents/01-greeting-identity.md)."""

import re

from sania.agents.base import Agent
from sania.llm import STRING, enum, obj
from sania.state import Lang, Profile

T1 = "Hello, क्या मैं {name} जी से बात कर रही हूँ."


class IdentityAgent(Agent):
    name = "identity"
    handoffs = ("disclosure",)
    signals_schema = obj(
        identity=enum("VERIFIED", "UNCLEAR", "DENIED", "WRONG_NUMBER", "THIRD_PARTY"),
        identity_evidence=STRING,
    )
    fallback_lines = {
        Lang.HINDI: "जी, HDFC collections से call है, क्या आप {name} जी बोल रहे हैं.",
        Lang.ENGLISH: "This is HDFC collections calling for {name} जी, am I speaking with {name} जी.",
    }
    instructions = """
ROLE: You handle ONLY identity verification at the start of the call. You know only the customer's name.
You know nothing about the account and must never talk about payments, cards, amounts or dates.

Decide what "caller_just_said" means:
- VERIFIED only if the caller clearly confirms they ARE the customer (हाँ, yes, speaking, मैं ही हूँ, or says their own name).
  A yes followed by an invitation to continue also counts ("हाँ जी बोलो", "haan bolo kya hai", "yes tell me").
  Then speech is empty and handoff is "disclosure". Put the caller's exact confirming words in identity_evidence.
- UNCLEAR if it is a question back ("who is this", "कौन", "क्यों"), confusion ("समझ नहीं आया", "I don't understand"),
  off-topic, or a bare "जी" / "बोलो" without a yes. Re-ask if you are speaking with <name> जी (always say the name),
  in fresh words that fit their reply. Never ask them to tell you their name.
  You may only say that it is HDFC collections calling for <name> जी. Nothing else. No filler word.
- DENIED or WRONG_NUMBER: one polite line that the call reached the wrong person, wish them a good day, end_call true.
- THIRD_PARTY (someone who knows the customer, e.g. spouse, relative): ask them to have <name> जी call HDFC,
  thank them, end_call true. Share no reason and no detail, even if they ask.
When in doubt, choose UNCLEAR.
"""


# Second key for verification: a simple rule must agree with the model.
AFFIRM_WORDS = {
    "haan", "han", "haa", "हाँ", "हां", "yes", "yeah", "yep", "speaking",
    "हाजी", "हांजी", "हाँजी", "haanji", "haji",  # STT often merges "हाँ जी" into one word
}
AFFIRM_PHRASES = ["मैं ही", "main hi", "बोल रहा", "बोल रही", "bol raha", "bol rahi", "that's me", "this is"]
DOUBT_WORDS = {"कौन", "kaun", "who", "क्यों", "kyun", "kyon", "why", "sorry", "नहीं", "nahi", "nahin", "not", "no"}
DOUBT_PHRASES = ["समझ नहीं", "samajh nahi", "understand"]


def looks_like_self_id(text: str, profile: Profile) -> bool:
    """True only if the utterance explicitly confirms identity and shows no doubt."""
    low = text.lower()
    words = set(re.findall(r"[\wऀ-ॿ]+", low))
    if words & DOUBT_WORDS or any(p in low for p in DOUBT_PHRASES):
        return False
    says_name = profile.name.lower() in low or (profile.name_dev or "\u0000") in text
    return says_name or bool(words & AFFIRM_WORDS) or any(p in low for p in AFFIRM_PHRASES)
