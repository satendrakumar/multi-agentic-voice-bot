"""Local microphone / speaker I/O with simple energy-based endpointing (sounddevice).

Audio is always recorded and played at each device's native sample rate and
converted in software. Asking CoreAudio for other rates (16 kHz mic, 24 kHz TTS)
makes it reconfigure the hardware between turns, which can fail with
"Internal PortAudio error -9986".
"""

import logging
import time

from sania.voice.interfaces import Audio

log = logging.getLogger(__name__)


class MicSpeakerIO:
    def __init__(self, sample_rate: int = 16_000, block_ms: int = 30, speech_threshold: float = 0.02,
                 end_silence_s: float = 0.8, no_speech_timeout_s: float = 5.0, max_utterance_s: float = 20.0):
        import numpy as np
        import sounddevice as sd

        self.np, self.sd = np, sd
        self.sample_rate = sample_rate             # rate of the Audio returned to STT
        self.block_ms = block_ms
        self.threshold = speech_threshold          # RMS level that counts as speech
        self.end_blocks = int(end_silence_s * 1000 / block_ms)
        self.timeout_blocks = int(no_speech_timeout_s * 1000 / block_ms)
        self.max_blocks = int(max_utterance_s * 1000 / block_ms)

    def _device_rate(self, kind: str) -> int:
        # Queried every time, so a headset plugged in mid-call is picked up.
        return int(self.sd.query_devices(kind=kind)["default_samplerate"])

    def record_utterance(self) -> Audio:
        """Record until the caller stops talking. Returns empty Audio if nobody speaks."""
        np = self.np
        rate = self._device_rate("input")
        block = int(rate * self.block_ms / 1000)
        blocks, started, quiet = [], False, 0
        with self.sd.InputStream(samplerate=rate, channels=1, dtype="float32") as stream:
            for i in range(self.max_blocks):
                chunk, _ = stream.read(block)
                loud = float(np.sqrt(np.mean(chunk**2))) > self.threshold
                if not started:
                    if loud:
                        started = True
                    elif i >= self.timeout_blocks:
                        return Audio(np.zeros(0, dtype="float32"), self.sample_rate)  # silence
                    else:
                        continue
                blocks.append(chunk[:, 0])
                quiet = 0 if loud else quiet + 1
                if quiet >= self.end_blocks:
                    break
        return Audio(np.concatenate(blocks), rate).resample(self.sample_rate)

    def play(self, audio: Audio) -> None:
        if audio.is_empty:
            return
        for attempt in (1, 2):
            try:
                out = audio.resample(self._device_rate("output"))
                self.sd.play(out.samples, out.sample_rate)
                self.sd.wait()
                return
            except self.sd.PortAudioError as e:
                log.warning("Playback failed (attempt %d): %s", attempt, e)
                self.sd.stop()
                time.sleep(0.3)  # give CoreAudio a moment to settle
        log.error("Skipping this audio: the output device is not available")
