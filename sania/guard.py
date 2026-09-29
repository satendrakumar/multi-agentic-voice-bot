"""S2 — Response Compliance Guard.

`autofix` silently repairs formatting. `check` returns a list of hard violations;
the Orchestrator regenerates once on a violation, then falls back to a safe line.
"""

import re

from sania.prompts import SUPPORT
from sania.state import CallState, Lang, Stage

EMPATHY = [
    "समझ सकती हूँ", "समझती हूँ", "i understand", "i can understand", "कोई बात नहीं",
    "no problem", "sorry to hear", "दुख हुआ",
]
HEDGING = [
    "check करवा", "let me check", "i'll check", "i will check", "team से confirm",
    "confirm करके बताती", "waiver करवा", "reverse करवा",
]
JARGON = ["positive entry", "part payment", "bucket", "delinquent"]
JARGON_CAPS = re.compile(r"\b(MAD|PTP)\b")
THREATS = ["charges बढ़", "interest बढ़", "increasing charges", "legal action", "police", "court"]
ACCOUNT_WORDS = [
    "card", "ending", "due", "amount", "payment", "outstanding", "minimum", "rupees",
    "सिबिल", "cibil", "balance", "statement",
]
# Words that signal a money figure other than the two allowed amounts.
OTHER_AMOUNT = ["rupees", "हज़ार", "हजार", "thousand", "lakh", "आधा", "half", "instalment", "installment", "किश्त", "जितना हो सके"]
PAY_ROUTES = ["upi", "net banking", "payzapp", "link", "आज pay"]
# Formal Hindi (and Devanagari spellings of banking words) that must be said in English instead.
SHUDDH_HINDI = [
    "भुगतान", "न्यूनतम", "राशि", "सहायता", "समस्या", "विकल्प", "खाता", "संख्या", "कृपया",
    "पेमेंट", "कार्ड", "अमाउंट", "मिनिमम", "ड्यू", "स्टेटमेंट", "क्रेडिट", "कस्टमर", "ट्रांजैक्शन", "ट्रान्सएक्शन",
]


def autofix(speech: str, state: CallState, name_allowed: bool) -> str:
    """Repair punctuation, name usage and spelling rules without changing meaning."""
    text = speech.strip()
    text = re.sub(r"^<\|\w+\|>\s*", "", text)          # the language tag is added later
    text = re.sub(r"\s*ENDCALL\s*$", "", text)          # ENDCALL is added by the Orchestrator
    text = text.replace("?", ".").replace("!", ".").replace("।", ".")

    name = state.profile.name_dev
    if name:
        your = "your" if state.language == Lang.ENGLISH else "आपका"
        text = re.sub(rf"{name}(\s*जी)?\s*['’]s", your, text)          # never possessive
        if name_allowed:
            text = re.sub(rf"{name}(?!\s*जी)", f"{name} जी", text)      # never a bare name
        else:
            text = re.sub(rf"{name}(\s*जी)?\s*,?\s*", "", text)          # not on this turn

    text = re.sub(r"\bnetbanking\b", "net banking", text, flags=re.I)
    text = re.sub(r"\bautopay\b", "auto pay", text, flags=re.I)
    text = re.sub(r"\bcreditcard\b", "credit card", text, flags=re.I)
    cibil = "CIBIL" if state.language == Lang.ENGLISH else "सिबिल"
    text = re.sub(r"\bcibil\b|सिबिल", cibil, text, flags=re.I)

    text = re.sub(r"[^\w\sऀ-ॿ.,]", " ", text).replace("_", " ")   # only . and ,
    text = re.sub(r"\s+([.,])", r"\1", text)
    text = re.sub(r"([.,])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if text and not text.endswith("."):
        text += "."
    return text


def check(speech: str, state: CallState, user_text: str = "") -> list[str]:
    """Hard violations that must not reach the caller."""
    low = speech.lower()
    spoken = state.profile.spoken()
    problems = []

    if not state.verified and any(w in low for w in ACCOUNT_WORDS):
        problems.append("Identity not verified: do not mention any card, amount or payment detail.")
    if re.search(r"[\[\]{}]|\bNAME\b|\bOUT\b|\bDUE_DATE\b|\bCARD_", speech):
        problems.append("Placeholder text found. Use real values only.")
    if re.search(r"\d", speech):
        problems.append("Write numbers as English words, never digits.")

    # Only the outstanding and the minimum may be spoken as amounts.
    rest = low.replace(spoken["out_words"], "").replace(spoken["mad_words"], "")
    if state.topic != "already_paid" and any(w in rest for w in OTHER_AMOUNT):
        problems.append("Only the outstanding or the minimum amount may be named. No other figure.")

    if state.stage != Stage.SAFETY and any(p in low for p in EMPATHY):
        problems.append("No empathy lines. Respond to the fact and go to the solution.")
    if any(p in low for p in HEDGING):
        problems.append("No hedging like 'let me check'. Say customer care will best handle it.")
    if JARGON_CAPS.search(speech) or any(j in low for j in JARGON):
        problems.append("Internal jargon used. Say 'minimum' or describe the effect.")
    if any(t in low for t in THREATS):
        problems.append("No threats and never say charges are increasing.")

    # Repeating the minimum figure is fine when the caller asks for it or offers another amount.
    caller_amount = re.search(
        r"\d|minimum|मिनिमम|kitna|कितना|hundred|thousand|\bsau\b|hazaa?r|सौ|हज़ार|हजार", user_text.lower()
    )
    if state.mad_spoken and spoken["mad_words"] in low and not caller_amount:
        problems.append("The minimum figure was already said. Just say 'the minimum'.")
    if state.out_spoken and spoken["out_words"] in low:
        problems.append("The outstanding figure was already said. Say 'the full amount'.")

    without_name = rest.replace(state.profile.name_dev or "\u0000", "").replace("जी", "")
    if state.language == Lang.ENGLISH and re.search(r"[ऀ-ॿ]", without_name):
        problems.append("Language is ENGLISH: speak 100 percent English (the name may stay in Devanagari).")
    if state.language == Lang.HINDI and any(w in speech for w in SHUDDH_HINDI):
        problems.append("Use everyday Hinglish: banking words in English Latin script (payment, minimum, card, amount, help, option), no formal Hindi.")
    if state.topic == "account_block" and any(r in low for r in PAY_ROUTES):
        problems.append("Account block: the debit note is the only route. No UPI, net banking or pay today.")
    # Numbers read as words are long; account values and support contacts don't count toward the limit.
    for value in [*SUPPORT.values(), *spoken.values()]:
        low = low.replace(value.lower(), "")
    if len(low.split()) > 45:
        problems.append("Too long. Use one to three short sentences.")
    return problems
