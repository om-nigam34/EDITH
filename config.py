"""
EDITH — configuration.

Everything that might change between machines or over time lives here,
loaded from environment variables (via a local .env file). Nothing is
hardcoded so this can move from your laptop to a server later without
code changes — same principle as the rest of the roadmap.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of current working directory
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


class Config:
    # --- Brain ---
    # "anthropic", "openai", "gemini", or "groq" — swap providers without
    # touching any code. Gemini and Groq both have genuinely free tiers
    # (rate-limited, no credit card) — see README for the tradeoffs.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.6")

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # Gemini's model lineup moves fast — if this 404s with "no longer
    # available," the error message itself names the current replacement
    # model. Update this default (and your own .env) to match.
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # Groq's lineup also shifts — llama-3.3-70b-versatile was retired
    # June 2026. gpt-oss-120b is Groq's own recommended replacement.
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "1024"))
    # How many prior turns to keep in the live context window before
    # summarizing/trimming. Kept small at first on purpose — see memory/store.py.
    MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "20"))

    # --- Voice ---
    TTS_VOICE: str = os.getenv("TTS_VOICE", "en-GB-SoniaNeural")  # calm, precise, British — EDITH-coded
    HINDI_TTS_VOICE: str = os.getenv("HINDI_TTS_VOICE", "hi-IN-SwaraNeural")  # used automatically for Devanagari replies
    TTS_RATE: str = os.getenv("TTS_RATE", "+4%")
    STT_ENERGY_THRESHOLD: int = int(os.getenv("STT_ENERGY_THRESHOLD", "300"))
    STT_PAUSE_THRESHOLD: float = float(os.getenv("STT_PAUSE_THRESHOLD", "0.8"))
    # tiny.en (fastest) / base.en (default, balanced) / small.en (most accurate, slower)
    STT_MODEL_SIZE: str = os.getenv("STT_MODEL_SIZE", "base.en")
    WAKE_WORD: str = os.getenv("WAKE_WORD", "edith").lower()

    # --- Browser automation ---
    # Visible by default so you can watch EDITH work — set true to hide the window.
    BROWSER_HEADLESS: bool = os.getenv("BROWSER_HEADLESS", "false").strip().lower() == "true"

    # --- Server ---
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8765"))

    # --- Storage paths ---
    DATA_DIR: Path = ROOT_DIR / "data"
    MEMORY_FILE: Path = DATA_DIR / "memory.json"
    NOTES_FILE: Path = DATA_DIR / "notes.txt"
    SCREENSHOT_DIR: Path = ROOT_DIR / "screenshots"
    LOG_FILE: Path = ROOT_DIR / "logs" / "edith.log"

    @classmethod
    def validate(cls) -> list[str]:
        """Returns a list of human-readable problems. Empty list = good to go."""
        problems = []
        required_key = {
            "anthropic": cls.ANTHROPIC_API_KEY,
            "openai": cls.OPENAI_API_KEY,
            "gemini": cls.GEMINI_API_KEY,
            "groq": cls.GROQ_API_KEY,
        }
        if cls.LLM_PROVIDER not in required_key:
            problems.append(
                f"LLM_PROVIDER='{cls.LLM_PROVIDER}' is invalid — use one of: "
                f"{', '.join(required_key)}."
            )
        elif not required_key[cls.LLM_PROVIDER]:
            problems.append(
                f"{cls.LLM_PROVIDER.upper()}_API_KEY is not set. Copy .env.example to "
                f".env and add your key."
            )
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        return problems

    @classmethod
    def active_model(cls) -> str:
        return {
            "anthropic": cls.ANTHROPIC_MODEL,
            "openai": cls.OPENAI_MODEL,
            "gemini": cls.GEMINI_MODEL,
            "groq": cls.GROQ_MODEL,
        }.get(cls.LLM_PROVIDER, "unknown")


config = Config()