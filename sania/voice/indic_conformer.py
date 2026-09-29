"""STT adapter: AI4Bharat IndicConformer (ai4bharat/indic-conformer-600m-multilingual).

Gated model: accept the terms on Hugging Face and log in (`hf auth login`) first.
"""

from sania.state import Lang
from sania.voice.interfaces import Audio, Transcript

MODEL_SAMPLE_RATE = 16_000


class IndicConformerSTT:
    # IndicConformer covers 22 Indian languages but not English, so both modes use
    # Hindi; English speech comes back in Devanagari script.
    LANGUAGE_CODES = {Lang.HINDI: "hi", Lang.ENGLISH: "hi"}

    def __init__(self, model_id: str = "ai4bharat/indic-conformer-600m-multilingual", decoding: str = "ctc"):
        import torch
        from transformers import AutoModel

        self.torch = torch
        self.decoding = decoding  # "ctc" (faster) or "rnnt"
        self.model = AutoModel.from_pretrained(model_id, trust_remote_code=True)

    def transcribe(self, audio: Audio, lang: Lang) -> Transcript:
        if audio.is_empty:
            return Transcript("")
        wav = self.torch.tensor(audio.samples, dtype=self.torch.float32).unsqueeze(0)  # (1, samples)
        if audio.sample_rate != MODEL_SAMPLE_RATE:
            import torchaudio

            wav = torchaudio.functional.resample(wav, audio.sample_rate, MODEL_SAMPLE_RATE)
        text = self.model(wav, self.LANGUAGE_CODES[lang], self.decoding)
        return Transcript(str(text).strip())  # the model gives no confidence score
