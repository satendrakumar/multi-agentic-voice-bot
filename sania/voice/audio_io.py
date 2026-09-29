"""Local microphone / speaker I/O with simple energy-based endpointing (sounddevice).

One input stream and one output stream are opened on first use and kept running
for the whole call, at each device's native sample rate. Starting a new CoreAudio
stream for every turn is what fails on macOS ("Internal PortAudio error -9986"),
so per turn we only read from / write to the already-running streams.
"""

import logging

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
        self._input = None
        self._output = None

    # --- streams -----------------------------------------------------------------------

    def _open(self, kind: str):
        rate = int(self.sd.query_devices(kind=kind)["default_samplerate"])
        cls = self.sd.InputStream if kind == "input" else self.sd.OutputStream
        stream = cls(samplerate=rate, channels=1, dtype="float32")
        stream.start()
        return stream

    def _reopen(self, kind: str):
        old = self._input if kind == "input" else self._output
        if old is not None:
            try:
                old.close()
            except self.sd.PortAudioError:
                pass
        stream = self._open(kind)
        if kind == "input":
            self._input = stream
        else:
            self._output = stream
        return stream

    def close(self) -> None:
        for stream in (self._input, self._output):
            if stream is not None:
                stream.close()
        self._input = self._output = None

    # --- AudioIO -----------------------------------------------------------------------

    def record_utterance(self) -> Audio:
        """Record until the caller stops talking. Returns empty Audio if nobody speaks."""
        np = self.np
        stream = self._input or self._reopen("input")
        stream.read(stream.read_available)  # drop audio buffered while Sania was speaking
        rate = int(stream.samplerate)
        block = int(rate * self.block_ms / 1000)
        blocks, started, quiet = [], False, 0
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
                stream = self._output or self._reopen("output")
                stream.write(audio.resample(int(stream.samplerate)).samples)
                return
            except self.sd.PortAudioError as e:
                log.warning("Playback failed (attempt %d), reopening the speaker: %s", attempt, e)
                self._output = None  # the next attempt opens a fresh stream at the current device rate
        log.error("Skipping this audio: the output device is not available")
