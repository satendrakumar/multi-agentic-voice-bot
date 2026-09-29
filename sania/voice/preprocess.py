"""Audio clean-up before STT: remove noise, then split into speech chunks.

`PreprocessedSTT` wraps any SpeechToText, so preprocessing works with every model
and the denoiser / chunker can be replaced on their own. Defaults (see registry):
RNNoise denoiser (rnnoise.py) + Silero VAD chunker (silero.py). The simple
implementations below need only numpy/scipy and serve as lightweight alternatives.
"""

from typing import Protocol

import numpy as np

from sania.state import Lang
from sania.voice.interfaces import Audio, SpeechToText, Transcript


class Denoiser(Protocol):
    def __call__(self, audio: Audio) -> Audio: ...


class Chunker(Protocol):
    def __call__(self, audio: Audio) -> list[Audio]:
        """Speech segments only; silence and noise are dropped."""
        ...


class NoiseReduceDenoiser:
    """High-pass filter (removes hum and rumble) + spectral-gating noise reduction."""

    def __init__(self, highpass_hz: float = 80.0, strength: float = 0.8):
        self.highpass_hz = highpass_hz
        self.strength = strength  # 0..1, how much of the noise to remove

    def __call__(self, audio: Audio) -> Audio:
        if audio.is_empty:
            return audio
        import noisereduce
        from scipy.signal import butter, sosfilt

        sos = butter(4, self.highpass_hz, btype="highpass", fs=audio.sample_rate, output="sos")
        filtered = sosfilt(sos, audio.samples)
        with np.errstate(divide="ignore", invalid="ignore"):  # exact digital silence divides by zero
            cleaned = noisereduce.reduce_noise(y=filtered, sr=audio.sample_rate, prop_decrease=self.strength)
        return Audio(np.nan_to_num(cleaned).astype(np.float32), audio.sample_rate)


class SilenceChunker:
    """Split audio at pauses into chunks no longer than `max_chunk_s`.

    Cutting inside pauses avoids splitting words. Chunks without speech (pure noise)
    are dropped so the STT model never hallucinates text from them.
    """

    def __init__(self, max_chunk_s: float = 15.0, min_pause_s: float = 0.3, frame_ms: int = 30,
                 speech_threshold: float = 0.01, min_speech_s: float = 0.2):
        self.max_chunk_s = max_chunk_s
        self.min_pause_s = min_pause_s
        self.frame_ms = frame_ms
        self.threshold = speech_threshold  # frame RMS that counts as speech
        self.min_speech_s = min_speech_s

    def __call__(self, audio: Audio) -> list[Audio]:
        if audio.is_empty:
            return []
        frame = int(audio.sample_rate * self.frame_ms / 1000)
        n_frames = len(audio.samples) // frame
        frames = audio.samples[: n_frames * frame].reshape(n_frames, frame)
        speech = np.sqrt(np.mean(frames**2, axis=1)) > self.threshold

        max_frames = int(self.max_chunk_s * 1000 / self.frame_ms)
        pause_frames = int(self.min_pause_s * 1000 / self.frame_ms)
        min_speech = int(self.min_speech_s * 1000 / self.frame_ms)

        chunks, start, quiet = [], 0, 0
        for i in range(n_frames):
            quiet = 0 if speech[i] else quiet + 1
            at_pause = quiet >= pause_frames
            too_long = i - start + 1 >= max_frames
            if at_pause or too_long:
                cut = i - quiet // 2 if at_pause else i + 1  # cut in the middle of the pause
                if cut > start:
                    chunks.append((start, cut))
                start, quiet = cut, 0
        if start < n_frames:
            chunks.append((start, n_frames))

        return [
            Audio(audio.samples[a * frame: b * frame], audio.sample_rate)
            for a, b in chunks
            if speech[a:b].sum() >= min_speech
        ]


class PreprocessedSTT:
    """Denoise -> chunk -> transcribe each chunk -> join. Wraps any SpeechToText."""

    def __init__(self, stt: SpeechToText, denoiser: Denoiser | None = None, chunker: Chunker | None = None):
        self.stt = stt
        self.denoiser = denoiser
        self.chunker = chunker or SilenceChunker()

    def transcribe(self, audio: Audio, lang: Lang) -> Transcript:
        if self.denoiser:
            audio = self.denoiser(audio)
        parts = [self.stt.transcribe(chunk, lang) for chunk in self.chunker(audio)]
        parts = [p for p in parts if p.text]
        if not parts:
            return Transcript("")  # no speech -> the Orchestrator treats it as silence
        text = " ".join(p.text for p in parts)
        return Transcript(text, confidence=min(p.confidence for p in parts))
