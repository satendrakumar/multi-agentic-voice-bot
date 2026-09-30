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
        "move_done": None, "commitment": {"amount": None, "ptp_date": None, "mode": None, "firm_today": False},
        "irritated": False, "topic": None,
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
    s.mad_spoken, s.callouts = True, 1

    # Code picks the move; the model reports it back in move_done.
    from sania.agents.negotiation import next_move
    assert next_move(s)[0] == "angle:cibil"   # stalling -> best-fitting angle first
    fake_llm.add("negotiation", "Minimum pending रहा तो सिबिल पे असर पड़ेगा, आज या कल.",
                 negotiation_signals(move_done="angle:cibil"))
    bot.respond("next week कर दूँगा")
    assert s.angles_used == ["cibil"]
    assert next_move(s)[0] == "funds:savings_family"   # angles and funds ideas alternate

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


def test_next_move_policy(profile):
    from sania.agents.negotiation import next_move
    from sania.state import CallState
    s = CallState(profile, verified=True, reason_class="hardship")
    assert next_move(s)[0] == "pivot_minimum" and "three thousand five hundred rupees" in next_move(s)[1]
    s.mad_spoken = True
    assert next_move(s)[0] == "funds:savings_family"          # hardship: money solution before consequences
    s.funds_ideas_used.append("savings_family")
    assert next_move(s)[0] == "angle:future_credit"           # then the angle that fits hardship
    s.angles_used = ["cibil", "card_block", "future_credit", "escalation", "other_products"]
    s.funds_ideas_used = ["savings_family", "alt_mode", "salary_anchor"]
    assert next_move(s)[0] == "ask_date"                      # everything used: ask for a firm date


def test_reason_is_asked_only_once(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    bot.state.verified, bot.state.stage, bot.state.reason_asked = True, Stage.REASON, True
    reason = {"reason_class": "unknown", "reason_text": None, "topic": None, "question_intent": "reason"}
    fake_llm.add("reason", "please tell me the reason why the payment is pending.", reason)
    fake_llm.add("negotiation", "आज minimum कर दीजिए.", negotiation_signals(move_done="pivot_minimum"))
    bot.respond("It's not a bad thing")
    assert bot.state.stage == Stage.NEGOTIATION     # second reason ask was replaced by negotiation


def test_closing_question_never_ends_the_call(profile, fake_llm):
    bot = Orchestrator(profile, llm=fake_llm)
    bot.start()
    bot.state.verified, bot.state.stage = True, Stage.CLOSING
    fake_llm.add("closing", "Noted. Do you need any other help.", {"asked_help": False, "topic": None}, end_call=True)
    reply = bot.respond("ok")
    assert not reply.endswith("ENDCALL") and bot.state.help_asked
    fake_llm.add("closing", "Is there anything else I can help with.", {"asked_help": True, "topic": None})
    reply = bot.respond("no")
    assert reply.endswith("ENDCALL") and "help" not in reply.lower()   # second ask replaced by the goodbye


def test_annoyance_is_not_opt_out(fake_llm):
    from sania.agents.safety import HardStopClassifier
    fake_llm.replies["classifier"] = [{"hardstop": "opt_out", "confidence": 0.9}] * 2
    classifier = HardStopClassifier()
    assert classifier.classify("बोला ना next week", fake_llm) is None
    assert classifier.classify("मुझे call मत करो", fake_llm) == "opt_out"
