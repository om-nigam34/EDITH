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

    # --- Voice: text-to-speech ---
    TTS_VOICE: str = os.getenv("TTS_VOICE", "en-GB-SoniaNeural")  # calm, precise, British — EDITH-coded
    HINDI_TTS_VOICE: str = os.getenv("HINDI_TTS_VOICE", "hi-IN-SwaraNeural")  # used automatically for Devanagari replies
    TTS_RATE: str = os.getenv("TTS_RATE", "+4%")
    # Hindi neural voices read noticeably less clearly at the same +4% pace
    # tuned for the English voice — a slower, separate rate for Hindi runs
    # is one half of fixing "I can't hear the Hindi clearly." The other half
    # is voice/tts.py now synthesizing mixed Hindi/English replies as
    # separate per-language segments instead of picking one voice for the
    # whole sentence — see voice/tts.py for why that matters.
    HINDI_TTS_RATE: str = os.getenv("HINDI_TTS_RATE", "-5%")

    # --- Voice: speech-to-text ---
    STT_ENERGY_THRESHOLD: int = int(os.getenv("STT_ENERGY_THRESHOLD", "300"))
    STT_PAUSE_THRESHOLD: float = float(os.getenv("STT_PAUSE_THRESHOLD", "0.8"))
    # IMPORTANT: this must be a multilingual model (tiny/base/small/medium/
    # large-v3), never the "*.en" variants (tiny.en, base.en, small.en...).
    # The ".en" models are English-only at the weights level — they cannot
    # transcribe Hindi at all, no matter how clearly it's spoken. That was
    # the actual root cause of Hindi recognition "not working" before.
    # "small" is the default balance of accuracy vs. CPU speed; bump to
    # "medium" if you have the CPU headroom and want noticeably better
    # Hindi accuracy, or see STT_BACKEND below for an alternative.
    STT_MODEL_SIZE: str = os.getenv("STT_MODEL_SIZE", "small")
    # "" = auto-detect the spoken language per utterance (recommended for a
    # bilingual/Hinglish speaker). Set to "hi" or "en" to force one language
    # if auto-detect guesses wrong on short utterances.
    STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "").strip().lower()
    # Trims leading/trailing silence and noise-only stretches before
    # decoding (faster-whisper's built-in Silero VAD). Cuts down further on
    # the hallucinated-filler-phrase problem, on top of no_speech_prob
    # filtering in voice/stt.py.
    STT_VAD_FILTER: bool = os.getenv("STT_VAD_FILTER", "true").strip().lower() == "true"
    # Primes the decoder toward EDITH's own vocabulary (names, tools,
    # commands) instead of the nearest generic-sounding word or phrase —
    # the single cheapest accuracy win for domain-specific speech. Includes
    # a few Hindi terms too so the model has Devanagari tokens to lean on.
    STT_INITIAL_PROMPT: str = os.getenv(
        "STT_INITIAL_PROMPT",
        "EDITH, Playwright, notepad, YouTube, brightness, volume, screenshot. "
        "एडिथ, वॉल्यूम, नोटपैड, स्क्रीनशॉट।",
    )
    # "local" = faster-whisper on this machine (default; no extra API key,
    # works offline). "groq" = Groq's hosted whisper-large-v3-turbo — same
    # account/key as LLM_PROVIDER=groq, much faster, and generally more
    # accurate (especially on Hindi) since it's the full large-v3 model, at
    # the cost of needing internet + a Groq key even if your LLM brain is
    # Gemini/Claude/OpenAI. Automatically falls back to local on any error.
    STT_BACKEND: str = os.getenv("STT_BACKEND", "local").strip().lower()
    GROQ_STT_MODEL: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

    # --- Voice: wake word ---
    WAKE_WORD: str = os.getenv("WAKE_WORD", "edith").lower()
    # Plain substring phrases the standalone wake-word listener checks for
    # (see voice/wake_word.py) — deliberately simple string matching rather
    # than a trained wake-word model, so it stays cheap enough to run
    # continuously in the background.
    WAKE_PHRASES: list[str] = [
        WAKE_WORD,
        f"hey {WAKE_WORD}",
        f"wake up {WAKE_WORD}",
        f"ok {WAKE_WORD}",
    ]
    # Kept small on purpose — the wake-word listener only needs to catch a
    # few short phrases, not transcribe full commands, so it can stay fast
    # and run continuously without competing for CPU with the main brain.
    WAKE_MODEL_SIZE: str = os.getenv("WAKE_MODEL_SIZE", "tiny")

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
        if cls.STT_BACKEND not in ("local", "groq"):
            problems.append(f"STT_BACKEND='{cls.STT_BACKEND}' is invalid — use 'local' or 'groq'.")
        elif cls.STT_BACKEND == "groq" and not cls.GROQ_API_KEY:
            problems.append(
                "STT_BACKEND='groq' but GROQ_API_KEY is not set. Get a free key from "
                "console.groq.com, or set STT_BACKEND back to 'local'."
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