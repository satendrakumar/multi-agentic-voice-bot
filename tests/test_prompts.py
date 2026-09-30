import pytest

from sania import config, prompts
from sania.agents import (
    ClosingAgent, DisclosureAgent, DisputeAgent, IdentityAgent, NegotiationAgent,
    ReasonAgent, SafetyAgent, ServicingAgent,
)

AGENTS = [IdentityAgent, DisclosureAgent, ReasonAgent, NegotiationAgent, DisputeAgent,
          ServicingAgent, SafetyAgent, ClosingAgent]
REQUIRED = [a.name for a in AGENTS] + ["shared", "classifier", "transliterate"]
VERSIONS = sorted(p.name for p in config.PROMPTS_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("version", VERSIONS)
def test_every_version_is_complete(version):
    folder = config.PROMPTS_DIR / version
    missing = [n for n in REQUIRED if not (folder / f"{n}.md").is_file()]
    assert not missing, f"{version} is missing prompts: {missing}"
    assert (folder / "negotiation_moves.toml").is_file()


@pytest.mark.parametrize("version", VERSIONS)
def test_negotiation_moves_cover_every_move(version, monkeypatch):
    monkeypatch.setattr(config, "PROMPT_VERSION", version)
    prompts.load_toml.cache_clear()
    moves = prompts.load_toml("negotiation_moves")
    assert {"confirm_payment", "pivot_minimum", "callout", "angle", "ask_date"} <= set(moves)
    from sania.state import FUNDS_IDEAS, IMPACT_ANGLES
    assert set(moves["angles"]) == set(IMPACT_ANGLES)
    assert set(moves["funds"]) == set(FUNDS_IDEAS)
    prompts.load_toml.cache_clear()


def test_agents_build_system_prompt_from_files():
    system = NegotiationAgent().system_prompt()
    assert system.startswith("AGENT: negotiation")
    assert prompts.load("shared") in system and prompts.load("negotiation") in system


def test_missing_version_fails_clearly(monkeypatch):
    monkeypatch.setattr(config, "PROMPT_VERSION", "v999")
    prompts.load.cache_clear()
    with pytest.raises(FileNotFoundError, match="v999"):
        prompts.load("shared")
    prompts.load.cache_clear()
