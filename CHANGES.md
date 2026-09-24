# EDITH update — voice accuracy, wake word, gesture-reactive orb

Reference points for this pass: the open-sourced part of
`ultron-by-sagar-builds` (Three.js orb + MediaPipe gesture control) and
`ultronmain` (a fuller Python voice assistant with a wake-word process,
PyQt6 desktop wrapper, and Gemini Live API for streaming voice). Nothing
below is copied from either — each idea was re-implemented from scratch
against EDITH's own architecture, since a lot of what makes those repos
work depends on choices (PyQt6 shell, Gemini-only brain, single-file
main.py) that trade against things EDITH is already doing on purpose.

## Files changed

- `config.py` — new STT/TTS/wake-word settings (see below)
- `voice/stt.py` — multilingual model default, VAD, initial_prompt,
  temperature fallback, optional Groq-hosted backend
- `voice/tts.py` — per-script-run synthesis for mixed Hindi/English replies
- `main.py` — async `listen_once()` call site, direct `set_volume` path
- `frontend/app.js` — orb tracks hand position, pinch-to-volume gesture
- `frontend/style.css` — one line (`transition` on `.core`) for the above
- `requirements.txt` — `websockets`, `playsound==1.2.2` (both optional,
  only used by the new wake-word script)

## New files

- `voice/wake_word.py` — standalone always-on wake-word listener
- `start_wake_word.bat` — double-click launcher for it

## The bug that was actually behind "Hindi recognition doesn't work"

`STT_MODEL_SIZE` defaulted to `base.en`. The `.en` Whisper variants are
English-only at the weights level — not "worse at Hindi," genuinely
incapable of it. Every other symptom (garbled Hindi, English words coming
out fine) is consistent with that. Fixed by defaulting to `small`
(multilingual) instead, plus:

- `STT_VAD_FILTER=true` — trims silence/noise before decoding
- `STT_INITIAL_PROMPT` — primes the decoder with EDITH's own vocabulary,
  in both scripts
- `STT_LANGUAGE` — leave empty for auto-detect (recommended for a
  Hinglish speaker), or force `hi`/`en` if auto-detect guesses wrong on
  short utterances
- `temperature` fallback ladder + `condition_on_previous_text=False` —
  standard fixes for Whisper's repetition/hallucination tendencies
- `STT_BACKEND=groq` (opt-in) — routes audio to Groq's hosted
  `whisper-large-v3-turbo` instead of local decoding. Same account/key as
  `LLM_PROVIDER=groq`. Full large-v3 accuracy without your CPU doing the
  work; falls back to local automatically on any error.

**Tradeoff to know about:** `small` is a bigger, slower download than
`base.en` was. If transcription latency matters more than Hindi accuracy
on your machine, `STT_BACKEND=groq` sidesteps that entirely; if you'd
rather stay fully local and offline, `base` (no `.en`) is a smaller
multilingual step up from the old default.

## The other half of the Hindi complaint — TTS clarity

The old code picked ONE voice for an entire reply based on whether >15%
of its characters were Devanagari. A normal Hinglish reply like "मैं
Chrome खोल रहा हूँ" would get read entirely by whichever voice won that
character count — meaning either the English word got read in a Hindi
accent, or the Hindi sentence got read in an English voice, depending on
which side of 15% it landed. `voice/tts.py` now splits the reply into
runs by script and synthesizes each with its own voice and rate, then
stitches the audio together. `HINDI_TTS_RATE` (separate from `TTS_RATE`)
also lets you slow the Hindi voice down independently if `-5%` isn't
right for your ear.

Still true and not fixed by this: **romanized Hinglish** ("aap kaise ho"
typed in Latin letters) has no script signal to key off of, so it's read
by the English voice — that would need a language-ID model in the loop,
which is a bigger addition than this pass makes.

## Wake word

New `voice/wake_word.py`, run as its own process
(`python voice/wake_word.py` or `start_wake_word.bat`). Same general
shape as `ultronmain`'s approach — a lightweight always-on listener doing
short listen→transcribe→match cycles, checking whether the main app is
already running before launching it — reimplemented for what EDITH
actually is:

- Fully offline: uses EDITH's own local faster-whisper (a `tiny`
  multilingual model, kept separate and small since it only needs to
  catch a few short phrases) instead of a cloud speech API.
- Because EDITH's brain is a persistent WebSocket server rather than a
  program relaunched per conversation, "waking it up" means: confirm the
  server's running (launch it if not, via a liveness check on the
  configured port), then connect to it *as its own WebSocket client* and
  send the same `{"type": "listen"}` message the browser UI sends on a
  mic click.
- Plays the reply back locally (`playsound`, optional) instead of
  requiring a browser tab to be open or focused.

Configurable via `WAKE_WORD`, `WAKE_PHRASES` (derived automatically),
and `WAKE_MODEL_SIZE` in `config.py`.

**Honest caveat:** this was written and syntax-checked but not run
against a real microphone or a live server — there's no hardware for
that here. Watch the console output the first few runs.

## Gesture-reactive orb + pinch-to-volume

`ultron-by-sagar-builds`'s open-sourced piece is a Three.js orb that
reacts to hand tracking. Porting to Three.js/WebGL would be a real
rewrite and a new dependency, working against EDITH's stated
zero-build-step, plain-JS frontend — so instead, `frontend/app.js` now
drives the *existing* SVG ring core with a CSS transform computed from
the live MediaPipe hand landmarks already being tracked for gestures:
the orb drifts toward your hand's on-screen position in real time. Less
visually dramatic than a 3D orb, same underlying feel, no new
dependencies.

Also added: a pinch gesture (thumb + index brought together) now
continuously adjusts system volume while held, sent via a new
`set_volume` WebSocket message that goes **straight to the tool call in
`main.py`, bypassing the LLM entirely** — the right call for a
high-frequency, unambiguous action, and a small concrete step toward the
"skip redundant API calls for simple tool-only turns" item already on
the roadmap.

**Bug caught and fixed during testing:** a clenched fist also brings the
thumb and index tip close together as the fingers curl in, which
would've made "fist" (stop playback) misfire as "pinch" (volume). Fixed
by also checking how far the pinch point sits from the palm center — a
real pinch is held forward, a fist's convergence point sits on the palm
— verified against synthetic landmark data for both poses before
shipping it. The exact thresholds (`PINCH_CLOSED`, `PINCH_OPEN`, the
0.5/0.55 cutoffs in `app.js`) are reasonable starting points, not
tuned against a real camera — adjust them if pinch detection feels off
for your hand/lighting.

## Deliberately not taken from either repo, and why

- **PyQt6 + PyQt6-WebEngine desktop wrapper** (`ultronmain`) — bundles a
  full Chromium runtime (~200MB+) for an app-like window. EDITH's plain
  browser tab is lighter and already works; not worth the dependency
  surface for a cosmetic upgrade.
- **Single-file `main.py`** (`ultronmain`, ~48KB) — EDITH's 17-file split
  is more maintainable as the project grows; not something to walk back.
- **Gemini-only brain** (`ultronmain`) — EDITH's multi-provider
  abstraction is strictly more flexible; no reason to narrow it.
- **Full Three.js/WebGL orb** (`ultron-by-sagar-builds`) — bigger lift
  than this pass warranted; the CSS-transform version above gets most of
  the felt effect. Worth a dedicated pass later if the 3D look matters
  more than staying build-step-free.

## The biggest lever *not* pulled this round

`ultronmain` uses Gemini's Live API (bidirectional audio streaming) and
Sagar's proprietary voice layer uses OpenAI's Realtime API — both replace
the sequential STT→LLM→TTS round-trip with one open audio connection,
which is the real fix for the ~2-3s latency already on EDITH's roadmap.
That's a different architecture, not a config change or a file-level
diff like everything above, so it's deliberately out of scope here —
worth its own dedicated pass rather than bolting it on alongside
everything else in this update.

MCP as the multi-device protocol (from the `ultron-by-sagar-builds`
writeup) is similarly still just noted, not built — still the right call
once there's more than one device type to support.