"""Replay scripted callers against the real LLM, to compare prompt versions.

    uv run python scripts/simulate_calls.py                   # all scenarios
    uv run python scripts/simulate_calls.py hardship dispute  # some of them
    SANIA_PROMPT_VERSION=v2 uv run python scripts/simulate_calls.py

An empty caller line is silence. Guard regenerations and fallbacks are logged.
"""

import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sania import Orchestrator, Profile, config  # noqa: E402

RAHUL = dict(name="Rahul", card_name="Millennia", card_last4="1234", out=70000, mad=3500, due_date=date(2026, 9, 15))
PRIYA = dict(name="Priya", card_name="Regalia", card_last4="3094", out=44564, mad=850, due_date=date(2026, 9, 10))

SCENARIOS = {
    # The caller from a real voice test: short English replies, then Hindi, a garbled word, off-topic.
    "voice_test": (RAHUL, ["speaking.", "Yes.", "It's not a bad thing.", "",
                           "हां मैं यही हूँ मेरे पास पैसे नहीं थे चलिए नहीं कर पाया", "Medipaskar.", "",
                           "Yes, I am here.", "suggest me some movie good movie"]),
    "hardship": (RAHUL, ["हाँ जी बोलो", "salary नहीं आई अभी तक", "पैसे ही नहीं हैं",
                         "पाँच सौ कर देता हूँ", "ठीक है, तीन तारीख को UPI से minimum कर दूँगा", "नहीं, बस"]),
    "stalling": (RAHUL, ["कौन बोल रहा है", "हाँ मैं ही राहुल बोल रहा हूँ", "अभी नहीं, next week देखता हूँ",
                         "बोला ना next week", "ठीक है कल app से minimum कर दूँगा", "नहीं"]),
    "dispute": (PRIYA, ["haan ji bolo", "amount galat hai, maine ek transaction nahi kiya",
                        "do hazaar ka hai jo maine nahi kiya", "haan note kar liya",
                        "theek hai, kal PayZapp se minimum kar dungi", "nahi bas"]),
}


def run(name: str) -> None:
    profile_args, turns = SCENARIOS[name]
    bot = Orchestrator(Profile(**profile_args, today=date(2026, 9, 29)))
    print(f"\n=== {name}  (prompts {config.PROMPT_VERSION}, model {config.MODEL})")
    print(f"sania  > {bot.start()}")
    for text in turns:
        if bot.ended:
            break
        started = time.time()
        reply = bot.respond(text)
        print(f"caller > {text or '<silence>'}")
        print(f"sania  > {reply}   [{bot.state.stage.value}, {time.time() - started:.1f}s]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="   ! %(message)s")
    logging.getLogger("sania.orchestrator").setLevel(logging.INFO)
    for scenario in sys.argv[1:] or SCENARIOS:
        run(scenario)
