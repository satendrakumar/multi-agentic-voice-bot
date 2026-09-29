"""Model-agnostic voice interfaces. The session only depends on these.

To plug in another STT / TTS / audio device, implement the matching protocol and
register it in sania/voice/registry.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sania.state import Lang

if TYPE_CHECKING:
    import numpy as np


@dataclass
class Audio:
    samples: np.ndarray      # mono float32 in [-1, 1]
    sample_rate: int

    @property
    def is_empty(self) -> bool:
        return len(self.samples) == 0

    def resample(self, target_rate: int) -> Audio:
        """Return this audio at `target_rate` (polyphase resampling, needs scipy)."""
        if self.is_empty:
            return Audio(self.samples, target_rate)
        if target_rate == self.sample_rate:
            return self
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(target_rate, self.sample_rate)
        samples = resample_poly(self.samples, target_rate // g, self.sample_rate // g)
        return Audio(samples.astype("float32"), target_rate)


@dataclass
class Transcript:
    text: str
    confidence: float = 1.0  # models without a score report 1.0


class SpeechToText(Protocol):
    def transcribe(self, audio: Audio, lang: Lang) -> Transcript: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str, lang: Lang) -> Audio: ...


class AudioIO(Protocol):
    def record_utterance(self) -> Audio:
        """Block until the caller finishes speaking; return empty Audio on silence."""
        ...

    def play(self, audio: Audio) -> None: ...
