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
reply can't smoothly mix a Hindi voice and an English voice mid-sentence.
What this does instead: if the reply is written in Devanagari script
(EDITH's persona is instructed to write Hindi that way), it's spoken with
HINDI_TTS_VOICE; otherwise it's spoken with TTS_VOICE. Romanized Hinglish
("aap kaise ho") is Latin script, so it gets read by whichever voice is
currently active — the English-origin words come out fine, but Hindi-
origin words spelled phonetically won't sound as natural as proper
Devanagari would. There's no clean fix for that with a single-voice-per-
utterance engine; it's an inherent limitation worth knowing about rather
than a bug.
"""

import re
import tempfile
import uuid
from pathlib import Path

import edge_tts

from config import config

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_DEVANAGARI_THRESHOLD = 0.15  # fraction of characters that must be Devanagari to switch voices


def _pick_voice(text: str) -> str:
    if not text:
        return config.TTS_VOICE
    devanagari_count = len(_DEVANAGARI_RE.findall(text))
    if devanagari_count / len(text) > _DEVANAGARI_THRESHOLD:
        return config.HINDI_TTS_VOICE
    return config.TTS_VOICE


async def synthesize(text: str) -> bytes:
    """Returns MP3 bytes for the given text, or b"" on failure."""
    if not text:
        return b""
    tmp_path = Path(tempfile.gettempdir()) / f"edith_tts_{uuid.uuid4().hex}.mp3"
    try:
        voice = _pick_voice(text)
        communicate = edge_tts.Communicate(text, voice=voice, rate=config.TTS_RATE)
        await communicate.save(str(tmp_path))
        return tmp_path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        print(f"[EDITH] TTS synthesis failed: {exc}")
        return b""
    finally:
        tmp_path.unlink(missing_ok=True)