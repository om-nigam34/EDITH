"""
Speech-to-text.

Two backends behind one interface, picked by config.STT_BACKEND:

- "local" (default): faster-whisper running entirely on your machine (CPU
  is fine), so there's no per-request internet round-trip and no free-tier
  accuracy ceiling. The first run downloads the model from Hugging Face and
  caches it locally; every run after that is fully offline.
- "groq": Groq's hosted whisper-large-v3-turbo, using the same account/key
  as LLM_PROVIDER=groq. Trades "needs internet + a Groq key" for noticeably
  faster and more accurate transcription (the full large-v3 model instead
  of whatever fits on your CPU), which matters most for Hindi and accented
  speech. Falls back to local automatically if the request fails.

SpeechRecognition's Microphone is still used purely for audio *capture* in
both cases — it already handles ambient-noise calibration and "stop
automatically when you go quiet" well, so there's no reason to replace
that part.

IMPORTANT (this was the actual bug behind "Hindi recognition doesn't
work"): STT_MODEL_SIZE must be a multilingual model name (tiny, base,
small, medium, large-v3) — never a "*.en" variant. The ".en" models are
English-only at the weights level; no amount of clear speech makes them
transcribe Hindi. See config.py for the corrected default.

Tuning accuracy vs. speed: set STT_MODEL_SIZE in .env. 'tiny' is
fastest/least accurate, 'small' (default) is a good balance on a normal
laptop CPU, 'medium'/'large-v3' are noticeably more accurate but slower to
load and transcribe — or skip that tradeoff entirely with STT_BACKEND=groq.
"""

import io

import speech_recognition as sr
from faster_whisper import WhisperModel

from config import config

_recognizer = sr.Recognizer()
_recognizer.energy_threshold = config.STT_ENERGY_THRESHOLD
_recognizer.pause_threshold = config.STT_PAUSE_THRESHOLD

_whisper_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        print(f"[EDITH] Loading speech recognition model '{config.STT_MODEL_SIZE}' "
              f"(first run downloads it — this can take a minute)...")
        _whisper_model = WhisperModel(config.STT_MODEL_SIZE, device="cpu", compute_type="int8")
        print("[EDITH] Speech recognition model ready.")
    return _whisper_model


def _record_audio(timeout: float, phrase_time_limit: float) -> bytes:
    """Blocking mic capture — always runs off the event loop via to_thread
    in listen_once(), regardless of which transcription backend is used."""
    try:
        with sr.Microphone() as source:
            _recognizer.adjust_for_ambient_noise(source, duration=0.4)
            try:
                audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                return b""
    except OSError as exc:
        print(f"[EDITH] Microphone unavailable: {exc}")
        return b""
    return audio.get_wav_data()


def _transcribe_local(wav_bytes: bytes) -> str:
    try:
        wav_stream = io.BytesIO(wav_bytes)
        segments, info = _get_model().transcribe(
            wav_stream,
            beam_size=5,
            language=config.STT_LANGUAGE or None,
            vad_filter=config.STT_VAD_FILTER,
            initial_prompt=config.STT_INITIAL_PROMPT or None,
            # A temperature fallback ladder (Whisper's own recommended
            # pattern) instead of a single temperature=0 — if the greedy
            # decode looks unreliable (high compression ratio / low avg
            # logprob), it retries at a slightly higher temperature instead
            # of committing to a bad first guess.
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
            # Prevents one segment's hallucination from being fed back in
            # as "context" for the next segment within the same utterance —
            # a well-documented source of Whisper repetition loops.
            condition_on_previous_text=False,
        )
        if info.language_probability < 0.5:
            print(f"[EDITH] Low-confidence language guess: {info.language} "
                  f"({info.language_probability:.2f}) — consider setting STT_LANGUAGE explicitly.")
        # Whisper models are prone to hallucinating plausible-sounding filler
        # ("Okay.", "Thank you.") when fed silence or background noise rather
        # than returning nothing — a well-documented Whisper quirk, not
        # unique to this setup. no_speech_prob is Whisper's own estimate of
        # "this segment probably isn't speech at all"; dropping high-scoring
        # segments filters most of these out before they ever reach the LLM.
        kept = [seg for seg in segments if seg.no_speech_prob < 0.6]
        return " ".join(seg.text for seg in kept).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[EDITH] Local transcription failed: {exc}")
        return ""


async def _transcribe_via_groq(wav_bytes: bytes) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    response = await client.audio.transcriptions.create(
        model=config.GROQ_STT_MODEL,
        file=("audio.wav", wav_bytes, "audio/wav"),
        language=config.STT_LANGUAGE or None,
        prompt=config.STT_INITIAL_PROMPT or None,
    )
    return (response.text or "").strip()


async def listen_once(timeout: float = 6.0, phrase_time_limit: float = 12.0) -> str:
    """Records one utterance from the default microphone and returns the
    transcribed text, or "" if nothing was captured/understood."""
    import asyncio

    wav_bytes = await asyncio.to_thread(_record_audio, timeout, phrase_time_limit)
    if not wav_bytes:
        return ""

    if config.STT_BACKEND == "groq":
        try:
            return await _transcribe_via_groq(wav_bytes)
        except Exception as exc:  # noqa: BLE001
            print(f"[EDITH] Groq transcription failed ({exc}) — falling back to local.")

    return await asyncio.to_thread(_transcribe_local, wav_bytes)