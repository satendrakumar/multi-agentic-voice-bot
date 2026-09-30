"""Runtime settings. Override with environment variables or a .env file in the repo root."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # real environment variables win over .env values

# Prompts: prompts/<version>/*.md at the repo root (see prompts/README.md).
PROMPT_VERSION = os.getenv("SANIA_PROMPT_VERSION", "v1")
PROMPTS_DIR = Path(os.getenv("SANIA_PROMPTS_DIR", Path(__file__).resolve().parent.parent / "prompts"))

# LLM backend: "openai" (any OpenAI-compatible server, e.g. local vLLM) or "claude" (Anthropic API).
LLM_BACKEND = os.getenv("SANIA_LLM", "openai")
LLM_BASE_URL = os.getenv("SANIA_LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY = os.getenv("SANIA_LLM_API_KEY", "EMPTY")  # vLLM ignores it unless started with --api-key
LLM_MAX_TOKENS = int(os.getenv("SANIA_LLM_MAX_TOKENS", "400"))  # replies are short JSON; low cap stops runaway loops
LLM_TOP_P = float(os.getenv("SANIA_LLM_TOP_P", "0.8"))            # Qwen's recommended non-thinking sampling
LLM_PRESENCE_PENALTY = float(os.getenv("SANIA_LLM_PRESENCE_PENALTY", "1.0"))  # discourages repeating words
# Qwen thinking mode on vLLM: "1" on, "0" off, unset = don't send the switch (for other servers).
_thinking = os.getenv("SANIA_LLM_THINKING")
LLM_THINKING = None if _thinking is None else _thinking == "1"

# One model for every agent by default; lower effort keeps the fast agents quick (Claude only).
DEFAULT_MODELS = {"openai": "Qwen/Qwen3.5-4B", "claude": "claude-opus-5-5"}
MODEL = os.getenv("SANIA_MODEL", DEFAULT_MODELS.get(LLM_BACKEND, ""))

# Optional faster model for the simple agents (e.g. SANIA_FAST_MODEL=claude-haiku-4-5 to cut latency).
FAST_MODEL = os.getenv("SANIA_FAST_MODEL", MODEL)
FAST_AGENTS = {"identity", "disclosure", "closing", "classifier"}


def model_for(agent: str) -> str:
    return FAST_MODEL if agent in FAST_AGENTS else MODEL

# Effort per agent (low | medium | high). Negotiation gets the most thinking.
EFFORT = {
    "identity": "low",
    "disclosure": "low",
    "reason": "low",
    "negotiation": "medium",
    "dispute": "low",
    "servicing": "low",
    "safety": "low",
    "closing": "low",
    "classifier": "low",
}

# Voice models, by name from sania/voice/registry.py.
STT = os.getenv("SANIA_STT", "whisper")                      # whisper | indic_conformer
TTS = os.getenv("SANIA_TTS", "kokoro")                       # kokoro | indic_parler
DENOISER = os.getenv("SANIA_DENOISER", "rnnoise")            # rnnoise | noisereduce | none
VAD = os.getenv("SANIA_VAD", "silero")                       # silero | energy
MAX_CHUNK_S = float(os.getenv("SANIA_MAX_CHUNK_S", "15"))    # longest audio chunk sent to STT

MAX_TOKENS = 4000              # Claude backend (includes thinking tokens)
RECENT_TURNS = 8               # transcript lines sent to each agent
MAX_NEGOTIATION_TURNS = 10     # safety valve before forcing the close
MAX_IDENTITY_REASKS = 4
LOW_CONFIDENCE = 0.55          # STT confidence below this = "didn't hear you"
