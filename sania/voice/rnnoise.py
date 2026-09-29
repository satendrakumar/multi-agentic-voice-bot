"""Denoiser: xiph RNNoise (https://github.com/xiph/rnnoise) through the pyrnnoise bindings.

RNNoise works on 10 ms frames (480 samples) at 48 kHz, so audio is resampled to
48 kHz, denoised frame by frame, and resampled back.
"""

import numpy as np

from sania.voice.interfaces import Audio


class RNNoiseDenoiser:
    def __init__(self):
        from pyrnnoise import rnnoise

        self.rnnoise = rnnoise
        self.frame_size = rnnoise.FRAME_SIZE      # 480
        self.rate = rnnoise.SAMPLE_RATE           # 48000

    def __call__(self, audio: Audio) -> Audio:
        if audio.is_empty:
            return audio
        samples = np.clip(audio.resample(self.rate).samples, -1.0, 1.0)
        state = self.rnnoise.create()  # fresh state per utterance
        try:
            frames = [
                self.rnnoise.process_mono_frame(state, samples[i:i + self.frame_size])[0]
                for i in range(0, len(samples), self.frame_size)
            ]
        finally:
            self.rnnoise.destroy(state)
        cleaned = np.concatenate(frames).astype(np.float32) / 32767.0  # int16 -> float
        return Audio(cleaned, self.rate).resample(audio.sample_rate)
