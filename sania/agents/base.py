"""Base class for the conversational agents.

An agent is a role prompt (prompts/<version>/<name>.md) + a signals schema. Each
turn the Orchestrator passes it a JSON context and gets back an AgentResult.
Agents never touch state.
"""

import json
from dataclasses import dataclass, field

from sania import config, prompts
from sania.llm import BOOL, LLM, STRING, enum, nullable, obj
from sania.state import CallState, Lang


@dataclass
class AgentResult:
    speech: str = ""
    signals: dict = field(default_factory=dict)
    handoff: str | None = None
    end_call: bool = False
    failed: bool = False


class Agent:
    name: str = ""                         # also the prompt file name: prompts/<version>/<name>.md
    handoffs: tuple[str, ...] = ()         # agents it may hand over to
    signals_schema: dict = obj()
    fallback_lines: dict[Lang, str] = {}   # safe line if the model fails twice

    @property
    def instructions(self) -> str:
        return prompts.load(self.name)

    def system_prompt(self) -> str:
        return f"AGENT: {self.name}\n\n{prompts.load('shared')}\n\n{self.instructions}"

    def schema(self) -> dict:
        handoff = nullable(enum(*self.handoffs)) if self.handoffs else {"type": "null"}
        return obj(speech=STRING, signals=self.signals_schema, handoff=handoff, end_call=BOOL)

    def extra(self, state: CallState) -> dict:
        """Agent-specific facts added to the context."""
        return {}

    def validate(self, speech: str, state: CallState) -> list[str]:
        """Agent-specific checks on top of the shared guard."""
        return []

    def fallback(self, state: CallState) -> str:
        return self.fallback_lines[state.language].format(name=state.profile.name_dev)

    def run(self, context: dict, llm: LLM, feedback: list[str] | None = None) -> AgentResult:
        user = json.dumps(context, ensure_ascii=False)
        if feedback:
            user += "\n\nYour previous reply broke these rules. Write it again without breaking them:\n- "
            user += "\n- ".join(feedback)

        data = llm(
            system=self.system_prompt(),
            user=user,
            schema=self.schema(),
            effort=config.EFFORT[self.name],
            model=config.model_for(self.name),
        )
        if not data:
            return AgentResult(failed=True)
        return AgentResult(
            speech=data.get("speech", ""),
            signals=data.get("signals", {}),
            handoff=data.get("handoff"),
            end_call=data.get("end_call", False),
        )
