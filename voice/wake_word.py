"""
Wake-word listener — a second, lightweight, always-on process, separate
from the main EDITH server (main.py).

Why a separate process: main.py's server only opens the microphone when
someone has actively clicked/spoken/gestured. This script is meant to run
continuously in the background (e.g. from a Windows startup shortcut),
doing cheap, short listen -> transcribe -> check cycles with a tiny model,
and only wakes the real assistant when it actually hears its name.

The shape of this — a separate always-on process, plain substring
matching against a phrase list rather than a trained wake-word model, and
a liveness check before deciding whether to (re)launch the main app — is
the same general pattern used by comparable open-source assistants (it's
a common, sensible design, not unique to any one project). What's
different here, tailored to EDITH's own architecture instead of copying
anyone else's implementation:

- It stays fully offline: EDITH's main STT already runs faster-whisper
  locally, so the wake-word pass reuses that instead of depending on a
  free cloud speech API that needs internet and can rate-limit.
- Because EDITH's "brain" is a persistent WebSocket server rather than a
  program that gets launched fresh per conversation, waking it up means:
  make sure the server process is running (launching it if not), then
  connect to it *as a WebSocket client* and say "listen now" — the same
  message type the browser UI sends when you click the mic.
- It plays the reply locally (via `playsound`, optional — see
  requirements.txt) instead of requiring a browser tab to be open, so
  hands-free wake-word use doesn't depend on having the UI in focus.

Run it with:
    python voice/wake_word.py
or double-click start_wake_word.bat (see project root).

Untested against real microphone hardware from where this was written —
the logic follows faster-whisper/SpeechRecognition's documented behavior
and a straightforward socket/WebSocket handshake, but give it a real run
and watch the console output the first few times.
"""

import asyncio
import io
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# This script is meant to be run directly (python voice/wake_word.py), which
# makes Python put *this file's own folder* (voice/) at the front of
# sys.path - not the project root. That breaks `from config import ...`
# below, since config.py actually lives one level up. Inserting the parent
# directory here, before that import, fixes it regardless of how the
# script is launched (directly, via the .bat files, or with `python -m`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import speech_recognition as sr
from faster_whisper import WhisperModel

from config import ROOT_DIR, config

_recognizer = sr.Recognizer()
_recognizer.energy_threshold = config.STT_ENERGY_THRESHOLD
# Snappier than the main assistant's pause threshold — this is only ever
# listening for a short wake phrase, not a full command.
_recognizer.pause_threshold = 0.6

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"[EDITH-Wake] Loading wake-word model '{config.WAKE_MODEL_SIZE}'...")
        _model = WhisperModel(config.WAKE_MODEL_SIZE, device="cpu", compute_type="int8")
        print(f"[EDITH-Wake] Ready. Listening for: {', '.join(config.WAKE_PHRASES)}")
    return _model


def _server_is_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((config.HOST, config.PORT)) == 0


def _launch_server() -> None:
    print("[EDITH-Wake] EDITH's server isn't running — starting it in the background.")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    subprocess.Popen([sys.executable, str(ROOT_DIR / "main.py")], cwd=str(ROOT_DIR), **kwargs)
    for _ in range(20):  # wait up to ~10s for it to bind the port
        if _server_is_running():
            print("[EDITH-Wake] Server is up.")
            return
        time.sleep(0.5)
    print("[EDITH-Wake] Server still isn't responding — check the console window it opened.")


def _play_locally(audio_bytes: bytes) -> None:
    try:
        from playsound import playsound
    except ImportError:
        print("[EDITH-Wake] Reply received, but 'playsound' isn't installed, so it can't "
              "be played without a browser tab open. Run: pip install playsound==1.2.2")
        return
    tmp_path = Path(tempfile.gettempdir()) / f"edith_wake_reply_{int(time.time())}.mp3"
    tmp_path.write_bytes(audio_bytes)
    try:
        playsound(str(tmp_path))
    except Exception as exc:  # noqa: BLE001
        print(f"[EDITH-Wake] Couldn't play the reply locally: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)


async def _trigger_and_play() -> None:
    try:
        import websockets
    except ImportError:
        print("[EDITH-Wake] 'websockets' isn't installed. Run: pip install websockets")
        return

    uri = f"ws://{config.HOST}:{config.PORT}/ws"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "listen"}))
            while True:
                message = await ws.recv()
                if isinstance(message, bytes):
                    if message:
                        _play_locally(message)
                    break
                data = json.loads(message)
                msg_type = data.get("type")
                if msg_type == "heard" and data.get("text"):
                    print(f"[EDITH-Wake] Heard: {data['text']}")
                elif msg_type == "response":
                    print(f"[EDITH-Wake] EDITH: {data.get('text', '')}")
                elif msg_type == "error":
                    print(f"[EDITH-Wake] {data.get('text', '')}")
                    return
                elif msg_type == "state" and data.get("state") == "idle" and data.get("detail", "") == "":
                    # No audio came back (e.g. TTS failed) but the turn ended.
                    break
    except Exception as exc:  # noqa: BLE001
        print(f"[EDITH-Wake] Couldn't reach EDITH's server at {uri}: {exc}")


def _heard_wake_word(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in config.WAKE_PHRASES)


def listen_loop() -> None:
    model = _get_model()
    while True:
        try:
            with sr.Microphone() as source:
                audio = _recognizer.listen(source, timeout=None, phrase_time_limit=3)
        except OSError as exc:
            print(f"[EDITH-Wake] Microphone unavailable: {exc}")
            time.sleep(2)
            continue

        try:
            segments, _info = model.transcribe(io.BytesIO(audio.get_wav_data()), beam_size=1)
            text = " ".join(seg.text for seg in segments if seg.no_speech_prob < 0.6).strip()
        except Exception as exc:  # noqa: BLE001
            print(f"[EDITH-Wake] Transcription failed: {exc}")
            continue

        if not text:
            continue

        if _heard_wake_word(text):
            print(f'[EDITH-Wake] Wake word detected in: "{text}"')
            if not _server_is_running():
                _launch_server()
            asyncio.run(_trigger_and_play())


if __name__ == "__main__":
    print("[EDITH-Wake] Wake-word listener online. Say the wake word to start EDITH hands-free.")
    listen_loop()