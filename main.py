"""
EDITH — local entry point.

    python main.py

then open http://127.0.0.1:8765 in a browser (Chrome/Edge recommended).
"""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent.core import EdithAgent
from config import config
from voice import stt, tts

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

app = FastAPI(title="EDITH")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

agent: EdithAgent | None = None


def _friendly_error(exc: Exception) -> str:
    """Turns a raw provider exception into something worth reading aloud,
    instead of dumping a stack trace's worth of JSON into the transcript."""
    text = str(exc)
    lowered = text.lower()
    if "429" in text or "resource_exhausted" in lowered or "rate limit" in lowered or "quota" in lowered:
        return (
            "I've hit the AI provider's rate limit or free-tier quota. "
            "Wait a bit and try again, or switch LLM_PROVIDER in your .env "
            "to a different provider."
        )
    return f"I hit an error reaching the AI provider: {text[:200]}"


@app.on_event("startup")
async def startup() -> None:
    global agent
    problems = config.validate()
    if problems:
        for problem in problems:
            print(f"[EDITH] WARNING: {problem}")
        print("[EDITH] Starting anyway — the UI will report the error until this is fixed.")
        return
    agent = EdithAgent()
    print(
        f"[EDITH] Online. Provider: {config.LLM_PROVIDER} | Model: {config.active_model()} "
        f"| http://{config.HOST}:{config.PORT}"
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    async def send_state(state: str, detail: str = "") -> None:
        await websocket.send_text(json.dumps({"type": "state", "state": state, "detail": detail}))

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            if agent is None:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "text": "EDITH isn't configured yet — add ANTHROPIC_API_KEY to .env and restart.",
                }))
                continue

            if msg_type == "listen":
                await send_state("listening")
                user_text = await asyncio.to_thread(stt.listen_once)
                await websocket.send_text(json.dumps({"type": "heard", "text": user_text}))
                if not user_text:
                    await send_state("idle")
                    continue
            elif msg_type == "text":
                user_text = message.get("text", "").strip()
                if not user_text:
                    continue
            elif msg_type == "playback_done":
                # Client finished playing the audio it received — now we're
                # truly idle. Playback lives entirely in the browser, so the
                # server has no other way to know when speech ends.
                await send_state("idle")
                continue
            elif msg_type == "stop":
                # Gesture/button interrupt. Playback stops client-side
                # immediately; this just re-syncs the HUD state.
                await send_state("idle")
                continue
            else:
                continue

            loop = asyncio.get_running_loop()

            def on_state(state: str, detail: str) -> None:
                loop.create_task(send_state(state, detail))

            try:
                reply = await agent.respond(user_text, on_state=on_state)
            except Exception as exc:  # noqa: BLE001
                # Provider errors (rate limits, quota, network blips) should
                # never take the whole connection down with them.
                await websocket.send_text(
                    json.dumps({"type": "error", "text": _friendly_error(exc)})
                )
                await send_state("idle")
                continue

            await websocket.send_text(json.dumps({"type": "response", "text": reply}))

            audio_bytes = await tts.synthesize(reply)
            if audio_bytes:
                await send_state("speaking")
                await websocket.send_bytes(audio_bytes)
                # The client tells us when playback actually finishes (see
                # app.js) so the HUD doesn't drop back to idle mid-sentence.
            else:
                await send_state("idle")

    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)