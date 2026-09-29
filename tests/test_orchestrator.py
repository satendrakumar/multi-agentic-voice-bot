from sania.orchestrator import Orchestrator
from sania.state import Stage

DISCLOSURE = (
    "जी, मैं सानिया HDFC Bank collections से recorded line पर बात कर रही हूँ, आपके Millennia credit card "
    "ending one two three four पे seventy thousand rupees का payment due है, आज pay कर पाएंगे."
)
VERIFIED = {"identity": "VERIFIED", "identity_evidence": "हाँ"}
UNCLEAR = {"identity": "UNCLEAR", "identity_evidence": ""}


def negotiation_signals(**overrides):
    signals = {
        "ask_level": "OUT", "angle_used": None, "angle_deepened": None, "funds_idea_used": None,
        "callout": False, "commitment": {"amount": None, "ptp_date": None, "mode": None, "firm_today": False},
        "new_reason_class": None, "irritated": False, "topic": None, "question_intent": "ask",
    }
    signals.update(overrides)
    return signals


def test_start_is_fixed_greeting(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    assert bot.start() == "<|HINDI|> Hello, क्या मैं राहुल जी से बात कर रही हूँ."


def test_confusion_never_unlocks(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    # The model wrongly says VERIFIED, but the caller only asked a question.
    fake_llm.add("identity", "", VERIFIED, handoff="disclosure")
    reply = bot.respond("कौन बोल रहा है")
    assert not bot.state.verified
    assert "rupees" not in reply and "card" not in reply
    assert bot.state.stage == Stage.IDENTITY


def test_leaky_identity_reply_is_replaced(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    leak = "आपके card पे seventy thousand rupees due है, क्या आप राहुल जी हैं."
    fake_llm.add("identity", leak, UNCLEAR)
    fake_llm.add("identity", leak, UNCLEAR)  # the retry leaks again
    reply = bot.respond("समझ नहीं आया")
    assert "rupees" not in reply
    assert "HDFC collections" in reply


def test_verified_then_disclosure_same_turn(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    fake_llm.add("identity", "", VERIFIED, handoff="disclosure")
    fake_llm.add("disclosure", DISCLOSURE, {}, handoff="reason")
    reply = bot.respond("हाँ मैं ही बोल रहा हूँ")
    assert bot.state.verified
    assert "recorded line" in reply and "seventy thousand rupees" in reply
    assert bot.state.out_spoken
    assert bot.state.stage == Stage.REASON


def test_distress_ends_immediately(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    bot.state.verified, bot.state.stage = True, Stage.NEGOTIATION
    fake_llm.add("classifier")
    fake_llm.replies["classifier"] = [{"hardstop": "distress", "confidence": 0.95}]
    fake_llm.add("negotiation", "आज minimum कर दीजिए.", negotiation_signals())
    fake_llm.add("safety", "आप अभी family का ध्यान रखिए, बाद में app से payment कर दीजिएगा.", {}, end_call=True)
    reply = bot.respond("papa hospital में हैं, surgery चल रही है")
    assert reply.endswith("ENDCALL") and reply.count("ENDCALL") == 1
    assert "minimum" not in reply
    assert bot.ended


def test_voicemail_fixed_english_line(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    reply = bot.respond("Please leave a message after the tone")
    assert reply == "<|ENGLISH|> Sorry for the inconvenience. Thank you. ENDCALL"


def test_angles_tracked_and_commitment_goes_to_closing(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    s = bot.state
    s.verified, s.stage, s.reason_class = True, Stage.NEGOTIATION, "stalling"

    fake_llm.add("negotiation", "Minimum pending रहा तो card block हो सकता है, आज या कल.",
                 negotiation_signals(angle_used="card_block", callout=True, ask_level="MAD"))
    bot.respond("next week कर दूँगा")
    assert s.angles_used == ["card_block"] and s.callouts == 1

    # Full commitment -> negotiation stays silent, closing speaks in the same turn.
    fake_llm.add("negotiation", "ठीक है.", negotiation_signals(
        commitment={"amount": "MAD", "ptp_date": "2026-10-01", "mode": "upi", "firm_today": False}))
    fake_llm.add("closing", "ठीक है, note कर लिया है, कुछ और help चाहिए.", {"asked_help": True, "topic": None})
    reply = bot.respond("ठीक है, first को UPI से minimum कर दूँगा")
    assert "कुछ और help चाहिए" in reply
    assert s.stage == Stage.CLOSING and s.help_asked

    fake_llm.add("closing", "धन्यवाद राहुल जी, आपका दिन शुभ हो.", {"asked_help": False, "topic": None}, end_call=True)
    reply = bot.respond("नहीं, बस")
    assert reply == "<|HINDI|> धन्यवाद राहुल जी, आपका दिन शुभ हो. ENDCALL"


def test_failed_disclosure_still_moves_on(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    fake_llm.add("identity", "", VERIFIED, handoff="disclosure")  # disclosure has no reply -> fails
    reply = bot.respond("हाँ मैं ही हूँ")
    assert "recorded line" in reply and "seventy thousand rupees" in reply  # template fallback
    assert bot.state.stage == Stage.REASON


def test_parse_json_is_lenient():
    from sania.llm.client import parse_json
    schema = {"required": ["speech", "end_call"]}
    assert parse_json('<think>hmm</think>```json\n{"speech": "hi", "end_call": false}\n```', schema) == {
        "speech": "hi", "end_call": False}
    assert parse_json('{"speech": "hi"}', schema) is None  # missing key
    assert parse_json("not json", schema) is None


def test_model_failure_uses_fallback(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    reply = bot.respond("हम्म क्या")  # no scripted reply -> the LLM "fails"
    assert reply == "<|HINDI|> जी, HDFC collections से call है, क्या आप राहुल जी बोल रहे हैं."
