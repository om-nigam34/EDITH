import re
import tempfile
import uuid
from pathlib import Path

import edge_tts

from config import config

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
# Below this many non-whitespace characters, a run doesn't get its own TTS
# call — it's merged into the previous run instead, so a single stray
# character doesn't cause a tiny, choppy, separately-synthesized clip.
# Deliberately NOT using str.isalnum() to count this: Devanagari dependent
# vowel signs and nasalization marks (े, ा, ँ, etc.) are Unicode
# "combining mark" characters, which isalnum() does not count — so common
# short Hindi words like है, हाँ, को, ना would be undercounted as length 1
# and wrongly swallowed into the neighboring English run, which is exactly
# the "short Hindi words sound wrong" bug this whole file exists to fix.
_MIN_RUN_CHARS = 2


def _split_by_script(text: str) -> list[tuple[str, str]]:
    """Splits text into (voice_key, chunk) runs, voice_key one of 'hi'/'en'.
    Punctuation and whitespace stay attached to whichever run they're
    already inside rather than forcing a language switch on their own."""
    if not text:
        return []

    segments: list[list[str]] = []  # each item: [key, accumulated_text]
    for ch in text:
        if ch.isspace() or not ch.isalnum():
            if segments:
                segments[-1][1] += ch
            else:
                segments.append(["en", ch])
            continue
        key = "hi" if _DEVANAGARI_RE.match(ch) else "en"
        if segments and segments[-1][0] == key:
            segments[-1][1] += ch
        else:
            segments.append([key, ch])

    merged: list[list[str]] = []
    for key, chunk in segments:
        meaningful_len = len(chunk.strip())
        if merged and meaningful_len < _MIN_RUN_CHARS:
            merged[-1][1] += chunk
        else:
            merged.append([key, chunk])
    return [(key, chunk) for key, chunk in merged]


def _voice_and_rate(key: str) -> tuple[str, str]:
    if key == "hi":
        return config.HINDI_TTS_VOICE, config.HINDI_TTS_RATE
    return config.TTS_VOICE, config.TTS_RATE


async def _synthesize_segment(text: str, voice: str, rate: str) -> bytes:
    if not text.strip():
        return b""
    tmp_path = Path(tempfile.gettempdir()) / f"edith_tts_{uuid.uuid4().hex}.mp3"
    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
        await communicate.save(str(tmp_path))
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


async def synthesize(text: str) -> bytes:
    """Returns MP3 bytes for the given text, or b"" on failure."""
    if not text:
        return b""

    segments = _split_by_script(text)
    if not segments:
        return b""

    if len(segments) == 1:
        # The common case (a reply entirely in one script) — one call,
        # same behavior and same cost as before.
        key, chunk = segments[0]
        voice, rate = _voice_and_rate(key)
        try:
            return await _synthesize_segment(chunk, voice, rate)
        except Exception as exc:  # noqa: BLE001
            print(f"[EDITH] TTS synthesis failed: {exc}")
            return b""

    audio_parts = []
    for key, chunk in segments:
        voice, rate = _voice_and_rate(key)
        try:
            part = await _synthesize_segment(chunk, voice, rate)
        except Exception as exc:  # noqa: BLE001
            print(f"[EDITH] TTS segment synthesis failed ({key}): {exc}")
            part = b""
        if part:
            audio_parts.append(part)

    return b"".join(audio_parts)