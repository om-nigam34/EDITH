"""
Text-to-speech.

Synthesizes audio with edge-tts (Microsoft's neural voices, free, no API
key) and returns raw bytes. Playback happens in the browser, not on the
server — this means EDITH's audio comes out of whatever device you're
viewing the UI on, which matters once you're not always sitting at the
same machine the server runs on. It also lets the UI drive real
audio-reactive visuals via the Web Audio API, instead of a canned
animation standing in for speech.

Language handling: edge-tts needs one voice per request, so a single
utterance can't smoothly mix a Hindi voice and an English voice mid-word.
What this does instead: the reply text is split into runs of Devanagari
vs. non-Devanagari script, and each run is synthesized separately with the
matching voice and rate, then the resulting MP3 bytes are concatenated in
order.

This directly replaces the old approach of picking ONE voice for the
*entire* reply based on whether >15% of its characters were Devanagari —
that approach meant a reply like "मैं Chrome खोल रहा हूँ" either read the
English word in a Hindi-accented voice, or read the whole Hindi sentence in
an English voice, depending on which side of the 15% line it landed on.
Splitting by script means each word is actually spoken by the voice suited
to it, which is what "the Hindi doesn't come out clearly" usually turns out
to mean in practice — it's not that hi-IN-SwaraNeural itself is unclear,
it's that mixed-script sentences (a very normal Hinglish reply from a
model told to mirror the user's language) were being read by the wrong
voice for parts of the sentence.

Caveat that's still true, and worth knowing: this only helps text that's
actually in Devanagari script. Romanized Hinglish ("aap kaise ho" typed in
Latin letters) is indistinguishable from English to this splitter, since
there's no script signal to key off of — it'll be read by the English
voice, and Hindi-origin words spelled phonetically won't sound as natural
as proper Devanagari would. There's no clean fix for that without a
language-identification model in the loop, which is a bigger addition than
this pass makes.

Concatenating independently-generated MP3 clips back-to-back is a
pragmatic approach, not a seamless one — most players (including browser
<audio> elements) handle sequential MP3 frames fine, but there can be a
very slight click at each seam since there's no crossfade. If that
becomes noticeable, the fix is decoding each clip to PCM and
re-encoding as one file (e.g. via pydub + ffmpeg) instead of raw byte
concatenation — a reasonable next step, left out here to avoid adding a
new dependency for something that mostly works today.
"""

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