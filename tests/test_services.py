from datetime import date

from sania import guard, input_quality, language
from sania.agents.identity import looks_like_self_id
from sania.numbers import date_words, digit_words, money_words
from sania.state import CallState, Lang, Stage


# --- numbers -------------------------------------------------------------------------

def test_money_words_reads_every_place():
    assert money_words(500) == "five hundred rupees"
    assert money_words(850) == "eight hundred fifty rupees"
    assert money_words(1250) == "one thousand two hundred fifty rupees"
    assert money_words(44564) == "forty four thousand five hundred sixty four rupees"
    assert money_words(150000) == "one lakh fifty thousand rupees"
    assert money_words(12345678) == "one crore twenty three lakh forty five thousand six hundred seventy eight rupees"
    assert money_words(1234.5) == "one thousand two hundred thirty four rupees and fifty पैसे"


def test_identifiers_digit_by_digit_and_dates():
    assert digit_words("3094") == "three zero nine four"
    assert date_words(date(2026, 9, 15)) == "fifteenth September"
    assert date_words(date(2026, 9, 23)) == "twenty third September"


# --- S1 language -----------------------------------------------------------------------

def test_mirror_then_lock(profile):
    s = CallState(profile)
    language.observe(s, "Yes speaking, what is this about")
    assert s.language == Lang.ENGLISH
    language.observe(s, "Yes.")                       # too short: no vote, no lock
    language.observe(s, "मेरे पास पैसे नहीं थे")       # mirroring still follows the caller
    assert s.language == Lang.HINDI and not s.language_locked
    language.observe(s, "I will pay tomorrow")        # third real vote -> locked
    assert s.language_locked and s.language == Lang.ENGLISH
    language.observe(s, "कल कर दूँगा पक्का भाई")
    assert s.language == Lang.ENGLISH          # locked, no flip
    language.observe(s, "हिंदी में बोलो")
    assert s.language == Lang.HINDI            # explicit switch


def test_ack_words_do_not_vote():
    assert language.caller_language("ok") is None
    assert language.caller_language("haan kal kar dunga") == Lang.HINDI
    assert language.caller_language("amount galat hai, maine ek transaction nahi kiya") == Lang.HINDI
    assert language.caller_language("I will pay the amount tomorrow") == Lang.ENGLISH


# --- S2 guard --------------------------------------------------------------------------

def test_identity_leak_is_blocked(profile):
    s = CallState(profile)
    assert guard.check("आपका card payment due है.", s)
    s.verified = True
    assert not guard.check("आपका card payment due है.", s)


def test_third_amount_empathy_hedging_blocked(profile):
    s = CallState(profile, verified=True, stage=Stage.NEGOTIATION)
    assert guard.check("आधा अभी कर दीजिए.", s)
    assert guard.check("five thousand rupees कर दीजिए.", s)
    assert not guard.check("three thousand five hundred rupees आज कर दीजिए.", s)
    assert guard.check("मैं समझ सकती हूँ, minimum आज कर दीजिए.", s)
    assert guard.check("Let me check with the team.", s)
    assert guard.check("आपका MAD pending है.", s)
    assert guard.check("न्यूनतम भुगतान आज कर दीजिए.", s)       # formal Hindi
    assert guard.check("आज पेमेंट कर दीजिए.", s)               # banking word in Devanagari
    assert guard.check("I will process the payment for the full amount.", s)   # false payment claim
    assert guard.check("मैं reason जानने के लिए पूछ रहा हूँ.", s)             # masculine self-reference
    assert guard.check("It was a difficult situation, but pay today.", s)      # sympathy
    assert not guard.check("आप app या net banking से minimum pay कर दीजिए.", s)


def test_minimum_figure_said_once_unless_caller_names_an_amount(profile):
    s = CallState(profile, verified=True, stage=Stage.NEGOTIATION, mad_spoken=True)
    line = "Minimum three thousand five hundred rupees ही है, आज या कल."
    assert guard.check(line, s, "नहीं हो पाएगा")
    assert not guard.check(line, s, "I can pay only five hundred")


def test_autofix_punctuation_and_name(profile):
    s = CallState(profile)
    assert guard.autofix("Pay कर पाएंगे?", s, name_allowed=False) == "Pay कर पाएंगे."
    assert guard.autofix("राहुल जी, आज pay कीजिए.", s, name_allowed=False) == "आज pay कीजिए."
    assert guard.autofix("धन्यवाद राहुल.", s, name_allowed=True) == "धन्यवाद राहुल जी."
    assert guard.autofix("<|HINDI|> ठीक है - धन्यवाद ENDCALL", s, True) == "ठीक है धन्यवाद."
    assert guard.autofix("धन्यवाद <name> जी.", s, name_allowed=True) == "धन्यवाद राहुल जी."


# --- S3 input quality ------------------------------------------------------------------

def test_silence_twice_ends(profile):
    s = CallState(profile, stage=Stage.NEGOTIATION)
    assert input_quality.handle(s, "", 1.0).speech == "जी, सुन रहे हैं."
    assert input_quality.handle(s, "", 1.0).end_call


def test_bad_audio_retries_then_ends(profile):
    s = CallState(profile)
    for _ in range(2):
        assert not input_quality.handle(s, "garbled", 0.2).end_call
    assert input_quality.handle(s, "garbled", 0.2).end_call


# --- identity second key ---------------------------------------------------------------

def test_self_identification_rule(profile):
    assert looks_like_self_id("हाँ मैं ही हूँ", profile)
    assert looks_like_self_id("Rahul speaking", profile)
    assert looks_like_self_id("haan bolo kya kaam hai", profile)
    assert looks_like_self_id("हाजी बोलो", profile)  # Whisper's spelling of "हाँ जी बोलो"
    assert not looks_like_self_id("कौन बोल रहा है", profile)
    assert not looks_like_self_id("I'm not able to understand", profile)
    assert not looks_like_self_id("जी", profile)


def test_never_agrees_amount_is_wrong(profile):
    s = CallState(profile, verified=True, stage=Stage.DISPUTE)
    assert guard.check("जी, यह amount galat hai.", s)
    assert not guard.check("जी, इसमें कितना amount आपको गलत लग रहा है.", s)   # asking is fine


def test_no_promise_that_calls_stop(profile):
    s = CallState(profile, verified=True, stage=Stage.SAFETY)
    assert guard.check("ठीक है, calls सचमुच बंद कर दूँगी.", s)
    assert guard.check("We will not call you again.", s)
    assert not guard.check("ठीक है, आपकी बात note कर ली है.", s)
