# EDITH — Personal AI Assistant (Phase 1)

A voice- and text-commanded AI assistant for your Windows machine, with a
swappable LLM brain, real tool-calling for system control, hand-gesture
input, and an animated HUD-style UI. This is Phase 1 of a longer roadmap:
a real, working software brain, running locally, that grows from here.

## What it actually does right now

- **Runs on a free brain by default.** `LLM_PROVIDER` in `.env` picks
  between **Gemini** or **Groq** (both genuinely free, no credit card) or
  **Claude**/**OpenAI** (paid, metered) — see "Choosing a provider" below.
- **Talks and listens.** Type or click the mic and speak; EDITH replies in
  a synthesized voice (edge-tts, free, neural, no API key). Audio plays
  and is analyzed live in your browser via the Web Audio API, so the
  waveform visual reacts to the actual speech, not a canned animation.
- **Reads hand gestures.** An optional camera toggle turns on real-time
  hand tracking (MediaPipe, running entirely on-device in your browser —
  no video frame is ever sent to the server or the LLM). Open palm =
  listen, fist = interrupt/stop, thumbs up = confirm. Gestures are an
  addition, not a requirement — the buttons always work too.
- **Controls your PC.** Opens/closes apps, opens websites, runs web
  searches, plays things on YouTube, sets volume/brightness, mutes audio,
  reads CPU/RAM/battery/disk status, takes screenshots, locks the machine,
  and can shut down/restart/sleep — but only after you've explicitly said
  yes to that specific action in the conversation.
- **Remembers within a session**, and keeps a lightweight plain-text log on
  disk (`data/memory.json`) so it can recall roughly where you left off
  next time.
- **Has a real animated UI** — a pulsing HUD core that changes color and
  motion for idle / listening / thinking / acting / speaking, plus a live
  transcript. Runs in your browser at `http://127.0.0.1:8765`, served by
  EDITH's own local FastAPI server.

This is an original sci-fi HUD design in that visual genre — not a
reproduction of any copyrighted franchise's actual interface.

## Choosing a provider

| Provider | Cost | Notes |
|---|---|---|
| **Gemini** (default) | Free | Google AI Studio, no credit card. Rate-limited (roughly 10-15 requests/minute, ~250-1000/day depending on model). **Free-tier prompts may be used by Google to improve their products** — worth knowing since this app handles voice commands and notes. |
| **Groq** | Free | No credit card, gated only by rate limits (~30 requests/minute). Runs fast open-weight models (Llama 3.3 by default). |
| **Claude (Anthropic)** | Paid | ~$2 input / $10 output per million tokens for the default model. No free tier. |
| **OpenAI** | Paid | ~$4-5 input / $20-30 output per million tokens for the flagship model. No meaningful free tier. |

For a personal assistant used casually, Gemini or Groq's free tiers are
genuinely enough — you won't hit the limits unless you're firing off
commands constantly. Start with the default (Gemini) and switch only if
you want to.

## Setup — from scratch

### Step 1: Unzip the project

You should have a file called **`edith.zip`**.

- **Windows:** Right-click `edith.zip` → **Extract All...** → choose a
  location (e.g. your Desktop or Documents folder) → **Extract**. This
  creates a folder called `edith` with everything inside it.
- No extra software needed — Windows has this built in.

### Step 2: Install Python

Skip this if `python --version` in a terminal already shows 3.10 or
higher. Otherwise, download it from https://python.org — during install,
**check the box that says "Add Python to PATH"** before clicking Install.

### Step 3: Open a terminal in the project folder

Open the `edith` folder you extracted, click the address bar at the top of
File Explorer, type `cmd`, and press Enter. This opens a terminal already
pointed at the right folder.

### Step 4: Create a virtual environment

```powershell
python -m venv venv
venv\Scripts\activate
```

Your terminal prompt should now show `(venv)` at the start of the line.
You'll need to run that `venv\Scripts\activate` line again every time you
open a new terminal to work on this project.

### Step 5: Install dependencies

```powershell
pip install -r requirements.txt
```

If `PyAudio` fails to build (a common Windows issue), run this and try
again:
```powershell
pip install pipwin
pipwin install pyaudio
```

### Step 6: Get a free API key

Pick one:
- **Gemini (recommended, free):** https://aistudio.google.com/apikey —
  sign in with a Google account, click "Create API key".
- **Groq (free):** https://console.groq.com/keys — sign up, create a key.

(Or, if you'd rather pay for Claude/OpenAI: Anthropic keys are at
console.anthropic.com/settings/keys, OpenAI keys at
platform.openai.com/api-keys.)

### Step 7: Configure

```powershell
copy .env.example .env
```

Open the new `.env` file in Notepad. Set `LLM_PROVIDER` to the provider
you picked, and paste your key into the matching line (e.g.
`GEMINI_API_KEY=...`). Leave everything else as-is for now.

### Step 8: Run it

```powershell
python main.py
```

You should see `[EDITH] Online.` in the terminal, naming your provider and
model. Leave this window open — it's the server running EDITH.

### Step 9: Open the interface

Open your browser (Chrome or Edge recommended) and go to:

```
http://127.0.0.1:8765
```

Type a command, or click the mic and speak. Try: *"what's my battery
at"*, *"open notepad"*, *"search for the latest SpaceX launch"*. Click the
hand icon to enable gesture control (grant camera permission when asked).

## Project layout

```
edith/
  main.py              FastAPI server + WebSocket bridge to the UI
  config.py            All settings, loaded from .env
  agent/
    core.py            The reasoning loop — persona, memory, delegates to a provider
    providers.py       Anthropic, OpenAI, Gemini, and Groq behind one interface
    persona.py         EDITH's system prompt / personality
    tool_schemas.py    What tools the brain can see and call
    tools.py           What the tools actually do on your machine
  voice/
    stt.py             Speech-to-text (mic -> text)
    tts.py             Text-to-speech (text -> audio bytes, played in-browser)
  memory/
    store.py           Session history + persistent text log
  frontend/
    index.html / style.css / app.js    The animated HUD + gesture control
```

## How to give EDITH a new power

1. Write a plain Python function in `agent/tools.py` that does the thing
   and returns a short string describing the result.
2. Add one entry to `TOOLS` in `agent/tool_schemas.py` describing when to
   use it.
3. Add one line to the `DISPATCH` dict in `agent/tools.py` mapping the tool
   name to your function.

No changes needed to `core.py`, `providers.py`, `main.py`, or the
frontend — every provider reads from the same `TOOLS` list.

## To add a fifth LLM provider later

Write one more class in `agent/providers.py` implementing `run_turn()`
(copy the shape of an existing one), add one branch to `build_provider()`,
add the config fields to `config.py`. Nothing else changes.

## Safety and privacy notes

- `power_action` (shutdown/restart/sleep) is hard-coded to refuse unless
  explicitly confirmed, and the persona prompt tells the model to only
  confirm after you've said yes in the conversation. Watch the transcript
  before confirming anything destructive.
- Your `.env` file holds your API key(s) — already excluded via
  `.gitignore`. Never commit it or share it.
- Conversations are sent to whichever provider you selected to generate
  responses. On Gemini's free tier specifically, Google may use that data
  to improve their products (not the case on paid tiers, or on Groq per
  their current terms — check each provider's own policy page if this
  matters to you).
- Camera frames for gesture control are processed entirely in your
  browser via MediaPipe's on-device model and are never transmitted
  anywhere. Camera access only starts when you click the gesture button.
- Browsers block audio autoplay without a recent click/tap on the page.
  Since replies only arrive right after you've clicked mic/send/a gesture,
  this is normally a non-issue; if you ever see "TAP TO HEAR REPLY," one
  click anywhere resumes it.

## A note on the Gemini provider specifically

Gemini's function-calling wire format was the least consistent across
Google's own documentation while building this (Google has at least two
overlapping API styles right now). The implementation in
`agent/providers.py` follows the most-corroborated pattern, but this is
the one piece I couldn't verify against a live API call. If it errors on
your first real run, check
https://ai.google.dev/gemini-api/docs/function-calling against your
installed `google-genai` version — that's the most likely spot needing a
small adjustment.