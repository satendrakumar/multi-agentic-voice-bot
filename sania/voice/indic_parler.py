"""TTS adapter: AI4Bharat Indic Parler-TTS (ai4bharat/indic-parler-tts).

Gated model: accept the terms on Hugging Face and log in (`hf auth login`) first.
The voice is chosen with a text description; Divya (Hindi) and Mary (Indian English)
are among the model card's recommended speakers and suit Sania's female persona.
"""

from sania.state import Lang
from sania.voice.interfaces import Audio

SPEAKERS = {Lang.HINDI: "Divya", Lang.ENGLISH: "Mary"}
DESCRIPTION = "{speaker} speaks with a moderate pitch at a normal pace, calm and clear, very clear recording, close sound."


class IndicParlerTTS:
    def __init__(self, model_id: str = "ai4bharat/indic-parler-tts", device: str | None = None,
                 speakers: dict[Lang, str] = SPEAKERS):
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.speakers = speakers
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(model_id).to(self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.description_tokenizer = AutoTokenizer.from_pretrained(self.model.config.text_encoder._name_or_path)

    def synthesize(self, text: str, lang: Lang) -> Audio:
        description = DESCRIPTION.format(speaker=self.speakers[lang])
        desc = self.description_tokenizer(description, return_tensors="pt").to(self.device)
        prompt = self.tokenizer(text, return_tensors="pt").to(self.device)
        generation = self.model.generate(
            input_ids=desc.input_ids,
            attention_mask=desc.attention_mask,
            prompt_input_ids=prompt.input_ids,
            prompt_attention_mask=prompt.attention_mask,
        )
        samples = generation.cpu().numpy().squeeze().astype("float32")
        return Audio(samples, self.model.config.sampling_rate)
