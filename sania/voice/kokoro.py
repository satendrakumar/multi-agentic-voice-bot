"""TTS adapter: hexgrad/Kokoro-82M, a lightweight TTS (82M parameters, 24 kHz).

Hindi uses espeak-ng for phonemes (`brew install espeak-ng` / `apt install espeak-ng`).
Voices from the model's VOICES.md: hf_alpha is a female Hindi voice; af_heart is
the highest-rated female English voice. One model is shared by both languages.
"""

import numpy as np

from sania.state import Lang
from sania.voice.interfaces import Audio

REPO_ID = "hexgrad/Kokoro-82M"
LANG_CODES = {Lang.HINDI: "h", Lang.ENGLISH: "a"}   # kokoro: h = Hindi, a = American English
VOICES = {Lang.HINDI: "hf_alpha", Lang.ENGLISH: "af_heart"}
SAMPLE_RATE = 24_000


class KokoroTTS:
    def __init__(self, voices: dict[Lang, str] = VOICES, speed: float = 1.0):
        import logging

        from kokoro import KPipeline

        # espeak-ng logs "language switch flags ..." for every mixed Hindi/English line.
        logging.getLogger("phonemizer").setLevel(logging.ERROR)

        hindi = KPipeline(lang_code=LANG_CODES[Lang.HINDI], repo_id=REPO_ID)
        english = KPipeline(lang_code=LANG_CODES[Lang.ENGLISH], repo_id=REPO_ID, model=hindi.model)
        self.pipelines = {Lang.HINDI: hindi, Lang.ENGLISH: english}
        self.voices = voices
        self.speed = speed

    def synthesize(self, text: str, lang: Lang) -> Audio:
        results = self.pipelines[lang](text, voice=self.voices[lang], speed=self.speed)
        pieces = [r.audio.cpu().numpy() for r in results if r.audio is not None]
        samples = np.concatenate(pieces) if pieces else np.zeros(0)
        return Audio(samples.astype(np.float32), SAMPLE_RATE)
