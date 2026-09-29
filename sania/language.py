"""S1 — Language & Style Manager.

Mirrors the caller's language for the first three bot turns, then locks it.
Only an explicit request ("in English", "हिंदी में बोलो") switches after the lock.
"""

import re

from sania import config
from sania.llm import LLM, STRING, obj
from sania.state import CallState, Lang

# Common names, so most calls need no LLM call for transliteration.
NAME_TABLE = {
    "rahul": "राहुल", "priya": "प्रिया", "amit": "अमित", "neha": "नेहा", "rohit": "रोहित",
    "anjali": "अंजलि", "vikas": "विकास", "pooja": "पूजा", "sanjay": "संजय", "kavita": "कविता",
    "satendra": "सतेंद्र", "suresh": "सुरेश", "ramesh": "रमेश", "sunita": "सुनीता", "arjun": "अर्जुन",
}

# One-word acknowledgements never vote for a language.
ACK_WORDS = {"ok", "okay", "yes", "no", "haan", "han", "ha", "ji", "hmm", "hm", "हाँ", "हां", "जी", "हम्म", "नहीं", "ओके"}

# Romanised Hindi words count as HINDI ("kal kar dunga").
ROMAN_HINDI = {
    "kal", "aaj", "abhi", "baad", "kab", "kaise", "kya", "kyun", "kyon", "kaun", "kuch", "aur", "lekin",
    "hai", "hain", "tha", "thi", "the", "ho", "hoon", "hun", "hu", "hoga", "hogi", "hua", "hui", "gaya", "gayi",
    "kar", "karna", "karo", "kiya", "kiye", "karunga", "karungi", "dunga", "dungi", "de", "dena", "diya",
    "liya", "liye", "sakta", "sakti", "sakte", "raha", "rahi", "rahe", "chahiye", "bolo", "bol", "samajh", "pata",
    "main", "mein", "maine", "mujhe", "mera", "meri", "mere", "aap", "aapka", "ye", "yeh", "wo", "woh", "jo",
    "nahi", "nahin", "haan", "ji", "bhi", "sirf", "bas", "theek", "thik", "galat", "sahi", "wala", "wali",
    "ka", "ki", "ke", "ko", "se", "pe", "par", "toh", "ek", "sau", "hazaar", "hazar", "paisa", "paise",
    "thoda", "bhai", "maaf", "kaam",
}

TO_ENGLISH = re.compile(r"\b(in english|speak english|english please|english me|english में)|इंग्लिश में", re.I)
TO_HINDI = re.compile(r"\b(in hindi|speak hindi|hindi me|hindi में)|हिंदी में|हिन्दी में", re.I)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def transliterate_name(name: str, llm: LLM) -> str | None:
    """Return the Devanagari form of the name, or None (agents then say आप)."""
    key = name.strip().lower()
    if key in NAME_TABLE:
        return NAME_TABLE[key]
    answer = llm(
        system="Transliterate the Indian person name into Devanagari script. Return only the name.",
        user=name,
        schema=obj(devanagari=STRING),
        effort="low",
        model=config.FAST_MODEL,
    )
    dev = (answer or {}).get("devanagari", "").strip()
    if dev and all(DEVANAGARI.match(ch) or ch == " " for ch in dev):
        return dev
    return None


def caller_language(text: str) -> Lang | None:
    """Dominant language of an utterance, or None when it is too short to tell."""
    tokens = [t for t in re.findall(r"[\wऀ-ॿ]+", text.lower()) if t not in ACK_WORDS]
    if len(tokens) < 2:
        return None
    hindi = sum(1 for t in tokens if DEVANAGARI.search(t) or t in ROMAN_HINDI)
    return Lang.HINDI if hindi >= len(tokens) - hindi else Lang.ENGLISH


def observe(state: CallState, text: str) -> None:
    """Update the call language from a caller utterance."""
    if TO_ENGLISH.search(text):
        state.language, state.language_locked = Lang.ENGLISH, True
        return
    if TO_HINDI.search(text):
        state.language, state.language_locked = Lang.HINDI, True
        return
    if state.language_locked:
        return
    lang = caller_language(text)
    if lang:
        state.language = lang
    if state.turn_no >= 3:
        state.language_locked = True


def tag(lang: Lang) -> str:
    return f"<|{lang.value}|>"
