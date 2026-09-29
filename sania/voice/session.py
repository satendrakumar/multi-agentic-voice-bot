"""Voice call loop: audio in -> STT -> Orchestrator -> TTS -> audio out.

Depends only on the interfaces, so any STT / TTS / audio device can be swapped in.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sania.orchestrator import Orchestrator
from sania.state import Lang
from sania.voice.interfaces import AudioIO, SpeechToText, TextToSpeech

log = logging.getLogger(__name__)

REPLY = re.compile(r"^<\|(HINDI|ENGLISH)\|>\s*(.*?)\s*(?:ENDCALL)?\s*$", re.S)


def split_reply(line: str) -> tuple[Lang, str]:
    """'<|HINDI|> नमस्ते. ENDCALL' -> (Lang.HINDI, 'नमस्ते.'). The tag picks the TTS voice."""
    match = REPLY.match(line)
    if not match:
        return Lang.HINDI, line.strip()
    return Lang(match.group(1)), match.group(2)


def split_for_tts(text: str, max_words: int = 12) -> list[str]:
    """Split a reply into sentences; long sentences also split at commas. Short pieces start playing sooner."""
    pieces = []
    for sentence in re.findall(r"[^.]+\.?", text):
        sentence = sentence.strip()
        if len(sentence.split()) <= max_words:
            pieces.append(sentence)
            continue
        current = ""
        for part in re.findall(r"[^,]+,?", sentence):
            current = f"{current} {part.strip()}".strip()
            if len(current.split()) >= max_words // 2:
                pieces.append(current)
                current = ""
        if current:
            pieces.append(current)
    return [p for p in pieces if p.strip(" .,")]


class VoiceSession:
    def __init__(self, bot: Orchestrator, stt: SpeechToText, tts: TextToSpeech, io: AudioIO):
        self.bot, self.stt, self.tts, self.io = bot, stt, tts, io

    def run(self) -> None:
        self._speak(self.bot.start())
        while not self.bot.ended:
            audio = self.io.record_utterance()
            transcript = self.stt.transcribe(audio, self.bot.state.language)
            log.info("caller: %s", transcript.text or "<silence>")
            self._speak(self.bot.respond(transcript.text, transcript.confidence))

    def _speak(self, line: str) -> None:
        """Stream the reply piece by piece: synthesize the next piece while the current one plays."""
        log.info("sania:  %s", line)
        lang, text = split_reply(line)
        pieces = split_for_tts(text)
        if not pieces:
            return
        with ThreadPoolExecutor(max_workers=1) as pool:
            upcoming = pool.submit(self.tts.synthesize, pieces[0], lang)
            for i in range(len(pieces)):
                audio = upcoming.result()
                if i + 1 < len(pieces):
                    upcoming = pool.submit(self.tts.synthesize, pieces[i + 1], lang)
                self.io.play(audio)
