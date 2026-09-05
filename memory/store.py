"""
Two layers of memory, kept deliberately separate:

1. Live session history — the exact list of API message blocks (including
   tool_use/tool_result) needed for the current conversation's tool loop.
   Lives in memory only; resets when EDITH restarts, same as a fresh
   conversation with any assistant. Raw tool-call blocks aren't JSON-clean,
   so this layer is intentionally not persisted.

2. Persistent text log — a plain-text record of what was actually said (no
   tool internals), written to disk so EDITH can recall the gist of past
   sessions on startup. This is the seed of the "memory and personality"
   phase on the roadmap — a fuller long-term memory (facts, preferences,
   embeddings/search) can be layered on top of this log later without
   changing the interface other callers use.
"""

import json
from datetime import datetime
from typing import Any

from config import config

MAX_TEXT_LOG_ENTRIES = 500


class MemoryStore:
    def __init__(self):
        self._live_history: list[dict[str, Any]] = []
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not config.MEMORY_FILE.exists():
            config.MEMORY_FILE.write_text("[]", encoding="utf-8")

    # --- live, in-process history (used directly in the API loop) ---

    def get_history(self) -> list[dict[str, Any]]:
        return self._live_history

    def set_history(self, history: list[dict[str, Any]]) -> None:
        self._live_history = history

    # --- durable plain-text log (used for continuity across restarts) ---

    def log_turn(self, role: str, text: str) -> None:
        if not text:
            return
        entries = self._read_log()
        entries.append(
            {"role": role, "text": text, "ts": datetime.now().isoformat(timespec="seconds")}
        )
        entries = entries[-MAX_TEXT_LOG_ENTRIES:]
        config.MEMORY_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def recent_summary(self, n: int = 6) -> str:
        entries = self._read_log()[-n:]
        if not entries:
            return ""
        return "\n".join(f"{e['role']}: {e['text']}" for e in entries)

    def _read_log(self) -> list[dict[str, Any]]:
        try:
            return json.loads(config.MEMORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []
