"""STT adapter: OpenAI Whisper large-v3-turbo via Hugging Face transformers.

Whisper's own language detection picks from ~100 languages, so a short or unclear
reply can come back as e.g. Italian. Here detection is restricted to the call's
languages (Hindi, English): one decoder step scores only those language tokens,
then the chunk is transcribed in the winner, reusing the same encoder output.
"""

from sania.state import Lang
from sania.voice.interfaces import Audio, Transcript

ALLOWED_LANGUAGES = ("hi", "en")


class WhisperSTT:
    def __init__(self, model_id: str = "openai/whisper-large-v3-turbo", device: str | None = None,
                 languages: tuple[str, ...] = ALLOWED_LANGUAGES):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()  # hides per-call deprecation / attention-mask notices

        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.torch, self.device = torch, device
        self.dtype = torch.float16 if device.startswith("cuda") else torch.float32
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, torch_dtype=self.dtype, use_safetensors=True
        ).to(device).eval()
        self.model.generation_config.forced_decoder_ids = None  # language/task are passed per call instead
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.sample_rate = self.processor.feature_extractor.sampling_rate  # 16 kHz

        lang_to_id = self.model.generation_config.lang_to_id  # e.g. "<|hi|>" -> token id
        self.language_ids = {code: lang_to_id[f"<|{code}|>"] for code in languages}

    def transcribe(self, audio: Audio, lang: Lang) -> Transcript:
        if audio.is_empty:
            return Transcript("")
        torch = self.torch
        audio = audio.resample(self.sample_rate)
        features = self.processor(audio.samples, sampling_rate=self.sample_rate, return_tensors="pt").input_features
        features = features.to(self.device, dtype=self.dtype)

        with torch.no_grad():
            encoder_outputs = self.model.get_encoder()(features)
            start = torch.tensor([[self.model.generation_config.decoder_start_token_id]], device=self.device)
            logits = self.model(encoder_outputs=encoder_outputs, decoder_input_ids=start).logits[0, -1]
            language = max(self.language_ids, key=lambda code: logits[self.language_ids[code]].item())
            ids = self.model.generate(encoder_outputs=encoder_outputs, language=language, task="transcribe")

        text = self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
        return Transcript(text)  # Whisper gives no confidence score here
