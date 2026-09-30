"""Agent 0 — Orchestrator / Call Controller (docs/agents/00-orchestrator.md).

Plain code, no LLM. Owns the call state, picks which agent speaks, enforces the
identity lock and usage counters, runs the compliance guard and emits ENDCALL.

Per caller turn:
  input quality -> language -> [hard-stop classifier || active agent] -> apply signals
  -> (at most one chained handoff) -> guard (regenerate once, else fallback) -> tag + ENDCALL
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sania import config, guard, input_quality, language
from sania.agents import (
    ClosingAgent, DisclosureAgent, DisputeAgent, HardStopClassifier, IdentityAgent,
    NegotiationAgent, ReasonAgent, SafetyAgent, ServicingAgent,
)
from sania.agents.base import Agent, AgentResult
from sania.agents.identity import T1, looks_like_self_id
from sania.llm import LLM, get_llm
from sania.state import CallState, Lang, Profile, Stage

log = logging.getLogger(__name__)

# The closing "any other help" question, however the model words it.
HELP_QUESTION = re.compile(r"(और|other|else).{0,20}(help|हेल्प|assist|सहायता)|help चाहिए|हेल्प चाहिए", re.I)

VOICEMAIL_LINE ="Sorry for the inconvenience. Thank you."

# Agents whose safe fallback line is a goodbye.
ENDS_ON_FALLBACK = {Stage.SAFETY, Stage.CLOSING, Stage.SERVICING}


class Orchestrator:
    def __init__(self, profile: Profile, llm: LLM | None = None):
        self.llm = llm or get_llm()  # backend from SANIA_LLM
        self.state = CallState(profile)
        self.classifier = HardStopClassifier()
        self.agents: dict[Stage, Agent] = {
            Stage.IDENTITY: IdentityAgent(),
            Stage.DISCLOSURE: DisclosureAgent(),
            Stage.REASON: ReasonAgent(),
            Stage.NEGOTIATION: NegotiationAgent(),
            Stage.DISPUTE: DisputeAgent(),
            Stage.SERVICING: ServicingAgent(),
            Stage.SAFETY: SafetyAgent(),
            Stage.CLOSING: ClosingAgent(),
        }
        self._pool = ThreadPoolExecutor(max_workers=1)

    @property
    def ended(self) -> bool:
        return self.state.ended

    # --- public API ------------------------------------------------------------------

    def start(self) -> str:
        """First bot turn: the fixed identity greeting."""
        profile = self.state.profile
        if not profile.name_dev:
            profile.name_dev = language.transliterate_name(profile.name, self.llm) or profile.name
        return self._say(T1.format(name=profile.name_dev))

    def respond(self, text: str, confidence: float = 1.0) -> str:
        """Handle one caller utterance and return Sania's reply (tagged, maybe ending in ENDCALL)."""
        s = self.state
        if s.ended:
            return ""
        s.transcript.append({"role": "caller", "text": text})

        quick = input_quality.handle(s, text, confidence)
        if quick:
            return self._say(quick.speech, quick.end_call)

        language.observe(s, text)
        if s.stage == Stage.NEGOTIATION:
            s.topic = None  # a side topic is finished once we are back in negotiation

        # The hard-stop check runs in parallel with the active agent, to save latency.
        agent = self.agents[s.stage]
        hardstop_future = self._pool.submit(self.classifier.classify, text, self.llm)
        result = agent.run(self._context(agent, text), self.llm)
        hardstop = hardstop_future.result()

        if hardstop:
            if hardstop == "voicemail":
                return self._say(VOICEMAIL_LINE, end=True, lang=Lang.ENGLISH)
            s.hardstop = hardstop
            self._go(Stage.SAFETY)
            agent = self.agents[Stage.SAFETY]
            result = agent.run(self._context(agent, text), self.llm)

        agent, result = self._apply(agent, result, text)
        speech = self._final_speech(agent, result, text)
        return self._say(speech, result.end_call)

    # --- routing -----------------------------------------------------------------------

    def _go(self, stage: Stage) -> None:
        if stage != self.state.stage:
            self.state.prev_stage, self.state.stage = self.state.stage, stage

    def _apply(self, agent: Agent, result: AgentResult, text: str) -> tuple[Agent, AgentResult]:
        """Apply signals, then follow a handoff. An empty speech means the next agent speaks now."""
        self._update_state(agent, result, text)
        if result.end_call or not result.handoff:
            return agent, result

        self._go(Stage(result.handoff))
        if result.speech.strip() or result.failed:
            return agent, result  # this agent speaks (or its fallback does); the new agent takes the next turn

        # Chained hop: at most one per turn.
        nxt = self.agents[self.state.stage]
        nxt_result = nxt.run(self._context(nxt, text), self.llm)
        self._update_state(nxt, nxt_result, text)
        if nxt_result.handoff and not nxt_result.end_call and (nxt_result.speech.strip() or nxt_result.failed):
            self._go(Stage(nxt_result.handoff))
        return nxt, nxt_result

    def _update_state(self, agent: Agent, r: AgentResult, text: str) -> None:
        """Turn an agent's signals into state changes. Code, not the model, has the final say."""
        s, sig = self.state, r.signals
        if agent.name == "disclosure":
            r.handoff = "reason"  # disclosure is always exactly one turn, even when its fallback is used
            r.failed = r.failed or not r.speech.strip()  # it must speak; empty -> the fallback line
        if r.failed:
            r.end_call = self.state.stage in ENDS_ON_FALLBACK
            return
        if sig.get("question_intent"):
            s.questions_asked.append(sig["question_intent"])
        if sig.get("topic"):
            s.topic = sig["topic"]

        if agent.name == "identity":
            identity = sig.get("identity")
            if identity == "VERIFIED" and looks_like_self_id(text, s.profile):
                s.verified = True
                r.speech, r.handoff = "", "disclosure"
            elif identity in ("VERIFIED", "UNCLEAR"):
                # Unclear, or the model said yes but the rule disagrees: stay locked and re-ask.
                s.identity_reasks += 1
                r.handoff = None
                if identity == "VERIFIED":
                    r.speech = ""  # falls back to the fixed re-ask line
                if s.identity_reasks > config.MAX_IDENTITY_REASKS:
                    r.speech = input_quality.LINES["bye"][s.language]
                    r.end_call = True
            else:
                r.end_call = True  # denied / wrong number / third party
                r.speech = r.speech or input_quality.LINES["bye"][s.language]

        elif agent.name == "reason":
            if s.reason_asked and sig.get("reason_class", "unknown") == "unknown" and not r.handoff:
                r.speech, r.handoff = "", "negotiation"  # the reason is asked only once
            s.reason_asked = s.reason_asked or bool(r.speech.strip())
            if sig.get("reason_class", "unknown") != "unknown":
                s.reason_class = sig["reason_class"]
                s.reason_text = sig.get("reason_text")
            if s.reason_class == "firm_today":
                s.commitment.firm_today = True
                r.speech, r.handoff = "", "closing"

        elif agent.name == "negotiation":
            self._update_negotiation(r)

        elif agent.name in ("dispute", "servicing"):
            s.support_shared = s.support_shared or sig.get("support_shared", False)

        elif agent.name == "safety":
            self._update_safety(r)

        elif agent.name == "closing":
            s.closing_turns += 1
            asks_help = bool(HELP_QUESTION.search(r.speech)) or sig.get("asked_help", False)
            if asks_help and s.help_asked:
                r.speech, r.end_call = "", True        # asked once already: just the goodbye (fallback line)
            elif asks_help:
                s.help_asked, r.end_call = True, False  # a question never ends the call
            if s.irritated or s.closing_turns >= 3:
                r.end_call = True

    def _update_negotiation(self, r: AgentResult) -> None:
        s, sig = self.state, r.signals
        s.negotiation_turns += 1

        # The move was chosen by negotiation.next_move(); record it so it is not repeated.
        move = sig.get("move_done") or ""
        kind, _, name = move.partition(":")
        if kind == "angle" and name not in s.angles_used:
            s.angles_used.append(name)
        elif kind == "funds" and name not in s.funds_ideas_used:
            s.funds_ideas_used.append(name)
        elif kind == "callout":
            s.callouts += 1
        elif kind == "pivot_minimum":
            s.ask_level = "MAD"
        if move:
            s.questions_asked.append(move)

        c, new = s.commitment, sig.get("commitment") or {}
        c.amount = new.get("amount") or c.amount
        c.mode = new.get("mode") or c.mode
        c.firm_today = c.firm_today or new.get("firm_today", False)
        if new.get("ptp_date") and new["ptp_date"] != c.ptp_date:
            c.ptp_date = new["ptp_date"]
            s.ptp_history.append(c.ptp_date)

        if sig.get("irritated"):
            s.irritated = True
        if s.irritated or c.complete() or s.negotiation_turns >= config.MAX_NEGOTIATION_TURNS:
            if r.handoff not in ("dispute", "servicing"):
                r.speech, r.handoff = "", "closing"

    def _update_safety(self, r: AgentResult) -> None:
        s = self.state
        if s.hardstop == "abuse":
            s.abuse_warnings += 1
            r.end_call = s.abuse_warnings >= 2
        elif s.hardstop == "injection":
            s.injection_warnings += 1
            r.end_call = s.injection_warnings >= 2
        elif s.hardstop == "deceased":
            r.end_call = s.deceased_asked
            s.deceased_asked = True
        else:
            r.end_call = True  # distress, self harm, opt-out
        if not r.end_call and s.hardstop in ("abuse", "injection"):
            s.hardstop = None
            self._go(s.prev_stage or Stage.IDENTITY)  # back to where we were

    # --- context & output --------------------------------------------------------------

    def _name_allowed(self) -> bool:
        s = self.state
        if s.stage in (Stage.IDENTITY, Stage.SAFETY):
            return True  # the identity question needs the name; so do final goodbyes
        return s.turn_no < 2 or (s.stage == Stage.CLOSING and s.help_asked)

    def _context(self, agent: Agent, text: str) -> dict:
        s = self.state
        context = {
            "language": s.language.value,
            "name_allowed": self._name_allowed(),
            "customer_name": s.profile.name_dev,
            # The identity lock: no account data exists in the context until verified.
            "account": s.profile.spoken() if s.verified else "NOT VERIFIED. You know nothing about the account.",
            "questions_asked": s.questions_asked[-8:],
            "recent_turns": s.transcript[-config.RECENT_TURNS - 1:-1],
            "caller_just_said": text,
        }
        context.update(agent.extra(s))
        return context

    def _final_speech(self, agent: Agent, result: AgentResult, text: str) -> str:
        """Guard the speech: auto-fix, regenerate once on a violation, else the safe fallback line."""
        s = self.state
        name_ok = self._name_allowed()
        speech = guard.autofix(result.speech, s, name_ok)
        problems = guard.check(speech, s, text) + agent.validate(speech, s)

        if speech and problems:
            log.info("%s regenerating: %s", agent.name, problems)
            retry = agent.run(self._context(agent, text), self.llm, feedback=problems)
            speech = guard.autofix(retry.speech, s, name_ok)
            problems = guard.check(speech, s, text) + agent.validate(speech, s)

        if not speech or problems:
            log.warning("%s using fallback line: %s", agent.name, problems)
            speech = guard.autofix(agent.fallback(s), s, name_ok)

        spoken = s.profile.spoken()
        s.out_spoken = s.out_spoken or spoken["out_words"] in speech.lower()
        s.mad_spoken = s.mad_spoken or spoken["mad_words"] in speech.lower()
        return speech

    def _say(self, speech: str, end: bool = False, lang: Lang | None = None) -> str:
        s = self.state
        s.turn_no += 1
        s.transcript.append({"role": "sania", "text": speech})
        line = f"{language.tag(lang or s.language)} {speech}"
        if end:
            s.stage = Stage.END
            line += " ENDCALL"
        return line
