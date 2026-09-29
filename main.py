"""Run the Sania bot.

    uv run python main.py            # text simulator: type as the caller, an empty line is silence
    uv run python main.py --voice    # microphone + speaker, using SANIA_STT / SANIA_TTS models
"""

import argparse
import logging
import warnings
from datetime import date

from sania import Orchestrator, Profile, config


def demo_profile() -> Profile:
    return Profile(
        name="Rahul",
        card_name="Millennia",
        card_last4="1234",
        out=70000,
        mad=3500,
        due_date=date(2026, 9, 15),
        today=date.today(),
    )


def run_text(bot: Orchestrator) -> None:
    print(f"sania  > {bot.start()}")
    while not bot.ended:
        try:
            text = input("caller > ")
        except (EOFError, KeyboardInterrupt):
            break
        print(f"sania  > {bot.respond(text)}   [{bot.state.stage.value}]")


def run_voice(bot: Orchestrator) -> None:
    from sania.voice import VoiceSession
    from sania.voice.audio_io import MicSpeakerIO
    from sania.voice.registry import build_stt, build_tts

    # Model libraries print deprecation notices on load that don't affect us.
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=UserWarning, module="torch")
    logging.getLogger("sania.voice").setLevel(logging.INFO)
    print(f"Loading STT={config.STT} (denoiser={config.DENOISER}, VAD={config.VAD}), TTS={config.TTS} ...")
    stt = build_stt(config.STT, denoiser=config.DENOISER, vad=config.VAD, max_chunk_s=config.MAX_CHUNK_S)
    session = VoiceSession(bot, stt=stt, tts=build_tts(config.TTS), io=MicSpeakerIO())
    print("Ready. Speak after Sania finishes.")
    try:
        session.run()
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(description="Sania collections voice bot")
    parser.add_argument("--voice", action="store_true", help="use microphone and speaker")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    bot = Orchestrator(demo_profile())
    if args.voice:
        run_voice(bot)
    else:
        run_text(bot)


if __name__ == "__main__":
    main()
