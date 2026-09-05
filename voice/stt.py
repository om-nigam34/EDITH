"""
Speech-to-text.

Uses faster-whisper for transcription — it runs entirely on your machine
(CPU is fine), so there's no per-request internet round-trip and no free-
tier accuracy ceiling. The first run downloads the model (~75MB for the
default 'base.en') from Hugging Face and caches it locally; every run
after that is fully offline.

SpeechRecognition's Microphone is still used purely for audio *capture* —
it already handles ambient-noise calibration and "stop automatically when
you go quiet" well, so there's no reason to replace that part.

Tuning accuracy vs. speed: set STT_MODEL_SIZE in .env. 'tiny.en' is
fastest/least accurate, 'base.en' (default) is a good balance on a normal
laptop CPU, 'small.en' is noticeably more accurate but slower to load and
transcribe.
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


def listen_once(timeout: float = 6.0, phrase_time_limit: float = 12.0) -> str:
    """Records one utterance from the default microphone and returns the
    transcribed text, or "" if nothing was captured/understood."""
    try:
        with sr.Microphone() as source:
            _recognizer.adjust_for_ambient_noise(source, duration=0.4)
            try:
                audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                return ""
    except OSError as exc:
        print(f"[EDITH] Microphone unavailable: {exc}")
        return ""

    try:
        wav_stream = io.BytesIO(audio.get_wav_data())
        segments, _info = _get_model().transcribe(wav_stream, beam_size=5)
        # Whisper models are prone to hallucinating plausible-sounding filler
        # ("Okay.", "Thank you.") when fed silence or background noise rather
        # than returning nothing — a well-documented Whisper quirk, not
        # unique to this setup. no_speech_prob is Whisper's own estimate of
        # "this segment probably isn't speech at all"; dropping high-scoring
        # segments filters most of these out before they ever reach the LLM.
        kept = [seg for seg in segments if seg.no_speech_prob < 0.6]
        return " ".join(seg.text for seg in kept).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[EDITH] Transcription failed: {exc}")
        return ""