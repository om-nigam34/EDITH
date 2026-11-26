import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent import live, tools
from agent.core import EdithAgent
from config import config
from voice import stt, tts

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

app = FastAPI(title="EDITH")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

agent: EdithAgent | None = None

VITALS_INTERVAL_SECONDS = 3


def _friendly_error(exc: Exception) -> str:
    # Turns a raw provider exception into something worth reading aloud,
    # instead of dumping a stack trace's worth of JSON into the transcript.
    text = str(exc)
    lowered = text.lower()
    if "429" in text or "resource_exhausted" in lowered or "rate limit" in lowered or "quota" in lowered:
        return (
            "I've hit the AI provider's rate limit or free-tier quota. "
            "Wait a bit and try again, or switch LLM_PROVIDER in your .env "
            "to a different provider. Local commands, weather, news and "
            "currency still work."
        )
    return f"I hit an error reaching the AI provider: {text[:200]}"


@app.on_event("startup")
async def startup() -> None:
    global agent
    problems = config.validate()
    for problem in problems:
        print(f"[EDITH] WARNING: {problem}")
    # Always start the agent. Without a working LLM it runs in local-only
    # mode: the brain still handles commands, live data and small talk.
    agent = EdithAgent()
    if agent.provider is None:
        print(
            "[EDITH] AI model not connected - running in local-only mode "
            f"({agent.provider_error or 'no provider configured'}). Commands, weather, "
            "news and currency still work."
        )
    brain_mode = "on" if agent.brain else "off"
    print(
        f"[EDITH] Online. Provider: {config.LLM_PROVIDER} | Model: {config.active_model()} "
        f"| Brain: {brain_mode} | STT: {config.STT_BACKEND} | http://{config.HOST}:{config.PORT}"
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


async def _vitals_loop(send_json) -> None:
    """Pushes CPU/RAM/disk/battery to the HUD's side panel. Only started for
    clients that announce themselves as the HUD (see "hud_ready" below)."""
    try:
        import psutil
    except ImportError:
        return
    try:
        psutil.cpu_percent(None)  # first reading is always 0.0 - prime it
        await asyncio.sleep(0.5)
        while True:
            battery = psutil.sensors_battery()
            await send_json({
                "type": "vitals",
                "cpu": psutil.cpu_percent(None),
                "ram": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage("/").percent,
                "battery": battery.percent if battery else None,
                "charging": battery.power_plugged if battery else None,
            })
            await asyncio.sleep(VITALS_INTERVAL_SECONDS)
    except Exception:  # noqa: BLE001  (socket closed, psutil quirk) - the panel just stops updating
        return


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    async def send_json(payload: dict) -> None:
        await websocket.send_text(json.dumps(payload))

    async def send_state(state: str, detail: str = "") -> None:
        await send_json({"type": "state", "state": state, "detail": detail})

    async def send_stats() -> None:
        brain = agent.brain if agent else None
        stats = brain.stats() if brain else {"local": 0, "live": 0, "ai": 0, "total": 0, "saved": 0, "pct": 0}
        await send_json({"type": "stats", "enabled": brain is not None, **stats})

    async def send_weather() -> None:
        city = agent.brain.default_city if agent and agent.brain else config.DEFAULT_CITY
        text = await live.weather(city)
        await send_json({"type": "weather", "text": text or "Weather is unavailable right now."})

    async def notify(message: str) -> None:
        # A timer or reminder fired: show it, and say it out loud.
        await send_json({"type": "notice", "text": message})
        audio_bytes = await tts.synthesize(message)
        if audio_bytes:
            await send_state("speaking")
            await websocket.send_bytes(audio_bytes)

    background: list[asyncio.Task] = []
    hud_ready = False

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            if agent is None:
                await send_json({"type": "error", "text": "EDITH is still starting up - try again in a moment."})
                continue

            if msg_type == "hud_ready":
                # Sent only by the browser HUD, never by the wake-word client,
                # so only the HUD gets live panels and timer/reminder notices.
                if not hud_ready:
                    hud_ready = True
                    if agent.brain:
                        agent.brain.notifiers.add(notify)
                    background.append(asyncio.create_task(_vitals_loop(send_json)))
                    background.append(asyncio.create_task(send_weather()))
                await send_stats()
                continue

            if msg_type == "get_weather":
                background.append(asyncio.create_task(send_weather()))
                continue

            if msg_type == "get_stats":
                await send_stats()
                continue

            if msg_type == "set_volume":
                # A continuous gesture control (pinch-to-adjust, see
                # frontend/app.js) firing many times a second has no
                # business round-tripping through an LLM call - this goes
                # straight to the tool, same as any other deterministic,
                # unambiguous action would.
                level = int(message.get("level", 50))
                result = await tools.run_tool("set_volume", {"level": level})
                await send_json({"type": "volume_ack", "level": level, "text": result})
                continue

            if msg_type == "listen":
                await send_state("listening")
                user_text = await stt.listen_once()
                await send_json({"type": "heard", "text": user_text})
                if not user_text:
                    await send_state("idle")
                    continue
            elif msg_type == "text":
                user_text = message.get("text", "").strip()
                if not user_text:
                    continue
            elif msg_type == "playback_done":
                # Client finished playing the audio it received - now we're
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
            state_tasks: list[asyncio.Task] = []

            def on_state(state: str, detail: str) -> None:
                state_tasks.append(loop.create_task(send_state(state, detail)))

            async def flush_states() -> None:
                # Every state update of this turn must reach the client BEFORE
                # anything sent after it. As bare fire-and-forget tasks, a late
                # "speaking" could land after the final "idle" (uvicorn's
                # sends often don't yield) and leave the HUD stuck on
                # "Speaking" whenever there was no audio to play.
                await asyncio.gather(*state_tasks, return_exceptions=True)

            try:
                turn = await agent.respond(user_text, on_state=on_state)
            except Exception as exc:  # noqa: BLE001
                # Provider errors (rate limits, quota, network blips) should
                # never take the whole connection down with them.
                await flush_states()
                await send_json({"type": "error", "text": _friendly_error(exc)})
                await send_stats()
                await send_state("idle")
                continue

            await flush_states()
            await send_json({"type": "response", "text": turn.text, "route": turn.route})
            await send_stats()

            audio_bytes = await tts.synthesize(turn.speech)
            if audio_bytes:
                await send_state("speaking")
                await websocket.send_bytes(audio_bytes)
                # The client tells us when playback actually finishes (see
                # app.js) so the HUD doesn't drop back to idle mid-sentence.
            else:
                await send_state("idle")

    except WebSocketDisconnect:
        pass
    finally:
        if agent and agent.brain:
            agent.brain.notifiers.discard(notify)
        for task in background:
            task.cancel()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)