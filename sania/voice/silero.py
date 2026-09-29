"""Chunker: Silero VAD (https://github.com/snakers4/silero-vad).

Finds the speech segments, drops everything else (silence and noise), then merges
neighbouring segments into chunks up to `max_chunk_s` so the STT model gets whole
phrases with context rather than single words.
"""

import numpy as np

from sania.voice.interfaces import Audio

VAD_RATE = 16_000  # Silero supports 8 kHz and 16 kHz


class SileroVADChunker:
    def __init__(self, max_chunk_s: float = 15.0, threshold: float = 0.5,
                 min_silence_ms: int = 300, speech_pad_ms: int = 100):
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad

        self.torch = torch
        self.get_speech_timestamps = get_speech_timestamps
        self.model = load_silero_vad()
        self.max_chunk_s = max_chunk_s
        self.threshold = threshold
        self.min_silence_ms = min_silence_ms
        self.speech_pad_ms = speech_pad_ms

    def __call__(self, audio: Audio) -> list[Audio]:
        if audio.is_empty:
            return []
        audio = audio.resample(VAD_RATE)
        spans = self.get_speech_timestamps(
            self.torch.from_numpy(np.ascontiguousarray(audio.samples)),
            self.model,
            threshold=self.threshold,
            sampling_rate=VAD_RATE,
            min_silence_duration_ms=self.min_silence_ms,
            speech_pad_ms=self.speech_pad_ms,
            max_speech_duration_s=self.max_chunk_s,
        )
        max_len = int(self.max_chunk_s * VAD_RATE)
        chunks: list[tuple[int, int]] = []
        for span in spans:
            start, end = span["start"], span["end"]
            if chunks and end - chunks[-1][0] <= max_len:
                chunks[-1] = (chunks[-1][0], end)  # merge with the previous chunk
            else:
                chunks.append((start, end))
        return [Audio(audio.samples[a:b], VAD_RATE) for a, b in chunks]
