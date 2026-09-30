"""Prompt loader. All prompt text lives in versioned folders, not in the code:

    prompts/<version>/shared.md               rules added to every agent
    prompts/<version>/<agent name>.md          one role prompt per agent
    prompts/<version>/classifier.md            hard-stop classifier
    prompts/<version>/transliterate.md         name -> Devanagari
    prompts/<version>/negotiation_moves.toml   instruction for each negotiation move

The version is chosen with SANIA_PROMPT_VERSION (see prompts/README.md).
"""

import tomllib
from functools import lru_cache
from pathlib import Path

from sania import config


def prompt_dir() -> Path:
    return config.PROMPTS_DIR / config.PROMPT_VERSION


@lru_cache
def load(name: str) -> str:
    """Text of prompts/<version>/<name>.md."""
    path = prompt_dir() / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt {path} (SANIA_PROMPT_VERSION={config.PROMPT_VERSION})")
    return path.read_text(encoding="utf-8").strip()


@lru_cache
def load_toml(name: str) -> dict:
    """Parsed prompts/<version>/<name>.toml."""
    path = prompt_dir() / f"{name}.toml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt {path} (SANIA_PROMPT_VERSION={config.PROMPT_VERSION})")
    return tomllib.loads(path.read_text(encoding="utf-8"))


# Fixed support contacts (data, not prompt text): always spoken exactly like this.
SUPPORT = {
    "phone": "one eight zero zero two six zero zero, or one eight zero zero one six zero zero",
    "email": "customer services dot cards at H D F C bank dot in",
    "whatsapp": "seven zero seven zero zero two two two two two",
}
