import pytest

np = pytest.importorskip("numpy")  # voice extra: uv sync --extra voice

from sania.state import Lang  # noqa: E402
from sania.voice import Audio, Transcript, VoiceSession, split_reply  # noqa: E402
from sania.voice.preprocess import NoiseReduceDenoiser, PreprocessedSTT, SilenceChunker  # noqa: E402

SR = 16_000


def tone(seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def quiet(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float32)


class RecordingSTT:
    def __init__(self):
        self.chunks = []

    def transcribe(self, audio, lang):
        self.chunks.append(audio)
        return Transcript(f"part{len(self.chunks)}", confidence=0.9)


# --- chunking & denoising ----------------------------------------------------------

def test_chunker_splits_at_pauses_and_drops_silence():
    audio = Audio(np.concatenate([quiet(0.5), tone(1.0), quiet(0.6), tone(0.8), quiet(1.0)]), SR)
    chunks = SilenceChunker()(audio)
    assert len(chunks) == 2
    assert 0.9 < len(chunks[0].samples) / SR < 1.8


def test_chunker_caps_chunk_length():
    chunks = SilenceChunker(max_chunk_s=2.0)(Audio(tone(5.0), SR))
    assert len(chunks) == 3
    assert all(len(c.samples) / SR <= 2.0 for c in chunks)


def test_pure_noise_gives_no_chunks():
    noise = (0.003 * np.random.default_rng(0).standard_normal(SR * 2)).astype(np.float32)
    assert SilenceChunker()(Audio(noise, SR)) == []


def test_denoiser_reduces_background_noise():
    rng = np.random.default_rng(0)
    noisy = np.concatenate([quiet(1.0), tone(1.0), quiet(1.0)]) + 0.02 * rng.standard_normal(SR * 3)
    cleaned = NoiseReduceDenoiser()(Audio(noisy.astype(np.float32), SR))
    noise_before = np.sqrt(np.mean(noisy[: SR // 2] ** 2))
    noise_after = np.sqrt(np.mean(cleaned.samples[: SR // 2] ** 2))
    assert noise_after < noise_before / 2
    assert len(cleaned.samples) == len(noisy)


def test_preprocessed_stt_joins_chunks():
    inner = RecordingSTT()
    stt = PreprocessedSTT(inner, denoiser=NoiseReduceDenoiser())
    audio = Audio(np.concatenate([tone(1.0), quiet(0.6), tone(1.0)]), SR)
    result = stt.transcribe(audio, Lang.HINDI)
    assert result.text == "part1 part2" and result.confidence == 0.9
    assert stt.transcribe(Audio(quiet(2.0), SR), Lang.HINDI).text == ""  # silence -> empty


def test_resample_keeps_duration():
    audio = Audio(tone(1.0), SR)
    assert len(audio.resample(48_000).samples) == 48_000
    assert len(audio.resample(48_000).resample(SR).samples) == SR


def test_rnnoise_removes_background_noise():
    pytest.importorskip("pyrnnoise")
    from sania.voice.rnnoise import RNNoiseDenoiser

    noise = (0.05 * np.random.default_rng(1).standard_normal(SR * 2)).astype(np.float32)
    cleaned = RNNoiseDenoiser()(Audio(noise, SR))
    assert cleaned.sample_rate == SR and abs(len(cleaned.samples) - len(noise)) < 100
    assert np.sqrt(np.mean(cleaned.samples**2)) < np.sqrt(np.mean(noise**2)) / 3


def test_silero_finds_no_speech_in_noise_or_silence():
    pytest.importorskip("silero_vad")
    from sania.voice.silero import SileroVADChunker

    vad = SileroVADChunker()
    noise = (0.01 * np.random.default_rng(2).standard_normal(SR * 2)).astype(np.float32)
    assert vad(Audio(noise, SR)) == []
    assert vad(Audio(quiet(1.0), SR)) == []


def test_registry_rejects_unknown_names():
    from sania.voice.registry import build_stt

    with pytest.raises(ValueError, match="Available: whisper, indic_conformer"):
        build_stt("nope")


# --- session -----------------------------------------------------------------------

def test_split_for_tts_pieces():
    from sania.voice.session import split_for_tts
    assert split_for_tts("ठीक है. धन्यवाद.") == ["ठीक है.", "धन्यवाद."]
    long = "जी, मैं सानिया HDFC Bank collections से recorded line पर बात कर रही हूँ, आपके card पे payment due है, आज pay कर पाएंगे."
    pieces = split_for_tts(long)
    assert len(pieces) > 1 and " ".join(pieces) == long


def test_split_reply():
    assert split_reply("<|ENGLISH|> Thank you. ENDCALL") == (Lang.ENGLISH, "Thank you.")
    assert split_reply("<|HINDI|> जी, सुन रहे हैं.") == (Lang.HINDI, "जी, सुन रहे हैं.")


class StubBot:
    def __init__(self, replies):
        self.replies, self.heard = list(replies), []
        self.state = type("S", (), {"language": Lang.HINDI})()

    @property
    def ended(self):
        return not self.replies

    def start(self):
        return "<|HINDI|> Hello."

    def respond(self, text, confidence):
        self.heard.append((text, confidence))
        return self.replies.pop(0)


class FakeTTS:
    def __init__(self):
        self.spoken = []

    def synthesize(self, text, lang):
        self.spoken.append((lang, text))
        return Audio(tone(0.1), SR)


class FakeIO:
    def __init__(self):
        self.played = 0

    def record_utterance(self):
        return Audio(tone(0.5), SR)

    def play(self, audio):
        self.played += 1

    def close(self):
        self.closed = True


def test_voice_session_round_trip():
    bot, tts, io = StubBot(["<|ENGLISH|> Bye. ENDCALL"]), FakeTTS(), FakeIO()
    VoiceSession(bot, stt=PreprocessedSTT(RecordingSTT()), tts=tts, io=io).run()
    assert bot.heard == [("part1", 0.9)]
    assert tts.spoken == [(Lang.HINDI, "Hello."), (Lang.ENGLISH, "Bye.")]  # tag picks the voice, no ENDCALL
    assert io.played == 2
    assert io.closed  # devices released when the call ends


def test_long_reply_is_spoken_in_pieces():
    long = "<|HINDI|> जी, मैं सानिया HDFC Bank collections से recorded line पर बात कर रही हूँ, आपके card पे payment due है."
    bot, tts, io = StubBot([]), FakeTTS(), FakeIO()
    VoiceSession(bot, stt=RecordingSTT(), tts=tts, io=io)._speak(long)
    assert len(tts.spoken) > 1 and io.played == len(tts.spoken)
