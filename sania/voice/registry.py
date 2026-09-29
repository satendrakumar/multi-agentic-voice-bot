"""Pick STT / TTS / denoiser / VAD implementations by name. Add new models here.

Selected with SANIA_STT, SANIA_TTS, SANIA_DENOISER and SANIA_VAD (see sania/config.py).
Imports are lazy so only the chosen models' dependencies need to be installed.
"""

from collections.abc import Callable

from sania.voice.interfaces import SpeechToText, TextToSpeech


def _whisper() -> SpeechToText:
    from sania.voice.whisper import WhisperSTT
    return WhisperSTT()


def _indic_conformer() -> SpeechToText:
    from sania.voice.indic_conformer import IndicConformerSTT
    return IndicConformerSTT()


def _kokoro() -> TextToSpeech:
    from sania.voice.kokoro import KokoroTTS
    return KokoroTTS()


def _indic_parler() -> TextToSpeech:
    from sania.voice.indic_parler import IndicParlerTTS
    return IndicParlerTTS()


def _rnnoise():
    from sania.voice.rnnoise import RNNoiseDenoiser
    return RNNoiseDenoiser()


def _noisereduce():
    from sania.voice.preprocess import NoiseReduceDenoiser
    return NoiseReduceDenoiser()


def _silero(max_chunk_s: float):
    from sania.voice.silero import SileroVADChunker
    return SileroVADChunker(max_chunk_s=max_chunk_s)


def _energy(max_chunk_s: float):
    from sania.voice.preprocess import SilenceChunker
    return SilenceChunker(max_chunk_s=max_chunk_s)


STT_MODELS: dict[str, Callable] = {"whisper": _whisper, "indic_conformer": _indic_conformer}
TTS_MODELS: dict[str, Callable] = {"kokoro": _kokoro, "indic_parler": _indic_parler}
DENOISERS: dict[str, Callable] = {"rnnoise": _rnnoise, "noisereduce": _noisereduce, "none": lambda: None}
VADS: dict[str, Callable] = {"silero": _silero, "energy": _energy}


def _pick(table: dict, name: str, kind: str) -> Callable:
    if name not in table:
        raise ValueError(f"Unknown {kind} {name!r}. Available: {', '.join(table)}")
    return table[name]


def build_stt(name: str, denoiser: str = "rnnoise", vad: str = "silero", max_chunk_s: float = 15.0) -> SpeechToText:
    """The named STT model, wrapped with noise removal and VAD chunking."""
    from sania.voice.preprocess import PreprocessedSTT

    return PreprocessedSTT(
        _pick(STT_MODELS, name, "STT")(),
        denoiser=_pick(DENOISERS, denoiser, "denoiser")(),
        chunker=_pick(VADS, vad, "VAD")(max_chunk_s),
    )


def build_tts(name: str) -> TextToSpeech:
    return _pick(TTS_MODELS, name, "TTS")()
