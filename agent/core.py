"""
The reasoning core.

Delegates the actual API mechanics to a provider (Anthropic or OpenAI, see
agent/providers.py) so the brain can be swapped via one config value.
Persona, memory, and tool dispatch are identical no matter which provider
is running underneath.
"""

from __future__ import annotations

from typing import Callable, Optional

from agent import tools
from agent.persona import SYSTEM_PROMPT
from agent.providers import build_provider
from memory.store import MemoryStore

StateCallback = Optional[Callable[[str, str], None]]


class EdithAgent:
    def __init__(self):
        self.provider = build_provider()
        self.memory = MemoryStore()
        self._seeded_recap = False

    def _system_prompt(self) -> str:
        """Base persona, plus a one-time recap of recent past sessions."""
        if self._seeded_recap:
            return SYSTEM_PROMPT
        self._seeded_recap = True
        recap = self.memory.recent_summary()
        if not recap:
            return SYSTEM_PROMPT
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"For continuity, here is a short excerpt of the end of your last "
            f"session with this user. Use it only if relevant \u2014 don't bring "
            f"it up unprompted:\n{recap}"
        )

    async def respond(self, user_text: str, on_state: StateCallback = None) -> str:
        def emit(state: str, detail: str = "") -> None:
            if on_state:
                on_state(state, detail)

        history = self.memory.get_history()
        final_text, new_history = await self.provider.run_turn(
            history=history,
            user_text=user_text,
            system_prompt=self._system_prompt(),
            on_tool_call=lambda name, tool_input: tools.run_tool(name, tool_input),
            on_state=emit,
        )

        self.memory.set_history(new_history)
        self.memory.log_turn("user", user_text)
        self.memory.log_turn("assistant", final_text)
        emit("speaking", final_text)
        return final_text or "Done."
