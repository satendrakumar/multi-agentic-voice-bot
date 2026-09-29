"""S3 — Input Quality Handler: silence and unclear audio, handled without an LLM."""

from dataclasses import dataclass

from sania import config
from sania.state import CallState, Lang, Stage


@dataclass
class QuickReply:
    speech: str
    end_call: bool = False


LINES = {
    "listening": {Lang.HINDI: "जी, सुन रहे हैं.", Lang.ENGLISH: "Hello, are you there."},
    "bye": {Lang.HINDI: "ठीक है, धन्यवाद.", Lang.ENGLISH: "Alright, thank you."},
    "repeat": {
        Lang.HINDI: "जी, आवाज़ साफ़ नहीं आई, फिर से बोलिए.",
        Lang.ENGLISH: "Sorry, the voice was not clear, please say that again.",
    },
    "call_later": {Lang.HINDI: "थोड़ी देर में call करती हूँ.", Lang.ENGLISH: "I will call you back in a while."},
}


def handle(state: CallState, text: str, confidence: float) -> QuickReply | None:
    """Return a reply for silence / bad audio, or None if the input is usable."""
    lang = state.language

    if not text.strip():
        state.silence_count += 1
        if state.silence_count >= 2:
            return QuickReply(LINES["bye"][lang], end_call=True)
        if state.stage == Stage.IDENTITY and state.profile.name_dev:
            name = state.profile.name_dev
            ask = f"क्या आप {name} जी बोल रहे हैं." if lang == Lang.HINDI else f"Am I speaking with {name} जी."
            return QuickReply(ask)
        return QuickReply(LINES["listening"][lang])

    if confidence < config.LOW_CONFIDENCE:
        state.bad_audio_retries += 1
        if state.bad_audio_retries > 2:
            return QuickReply(LINES["call_later"][lang], end_call=True)
        return QuickReply(LINES["repeat"][lang])

    state.silence_count = 0
    state.bad_audio_retries = 0
    return None
