"""
Tool implementations.

Every function here returns a short string — that string is what gets fed
back to the Claude API as the tool_result, so keep them factual and terse;
the model turns them into natural speech on its own.

Design rule: never let a missing optional dependency crash the whole
assistant. Each Windows-specific integration is imported lazily inside its
function and fails soft with an actionable message.
"""

from __future__ import annotations

import inspect
import os
import platform
import subprocess
import urllib.parse
import webbrowser
from datetime import datetime

from agent import browser
from config import config

IS_WINDOWS = platform.system() == "Windows"

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

APP_MAP = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "spotify": "spotify:",
    "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:",
    "calendar": "outlookcal:",
    "mail": "outlookmail:",
}


def open_application(app_name: str) -> str:
    if not IS_WINDOWS:
        return "open_application only supports Windows in this build."
    key = app_name.strip().lower()
    target = APP_MAP.get(key, app_name)
    try:
        os.startfile(target)  # type: ignore[attr-defined]
        return f"Opened {app_name}."
    except OSError:
        try:
            subprocess.Popen(f'start "" "{target}"', shell=True)
            return f"Opened {app_name}."
        except Exception as exc:  # noqa: BLE001
            return f"Couldn't open {app_name}: {exc}"


def close_application(app_name: str) -> str:
    try:
        import psutil
    except ImportError:
        return "psutil isn't installed. Run: pip install psutil"

    target = app_name.strip().lower()
    closed = []
    for proc in psutil.process_iter(["pid", "name"]):
        name = (proc.info.get("name") or "").lower()
        if target in name:
            try:
                proc.terminate()
                closed.append(proc.info["name"])
            except Exception:  # noqa: BLE001
                pass
    if closed:
        return f"Closed: {', '.join(sorted(set(closed)))}."
    return f"No running process matching '{app_name}' was found."


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------

SITE_MAP = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://www.github.com",
    "gmail": "https://mail.google.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "twitter": "https://www.x.com",
    "x": "https://www.x.com",
    "linkedin": "https://www.linkedin.com",
    "spotify web": "https://open.spotify.com",
    "maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
}


def open_website(site: str) -> str:
    key = site.strip().lower()
    if key in SITE_MAP:
        url = SITE_MAP[key]
    elif site.startswith("http://") or site.startswith("https://"):
        url = site
    elif "." in site and " " not in site:
        url = f"https://{site}"
    else:
        # Not a recognizable URL/site name — fall back to a search.
        return web_search(site)
    webbrowser.open(url)
    return f"Opened {url}"


def web_search(query: str) -> str:
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return f"Searched the web for '{query}'."


def play_on_youtube(query: str) -> str:
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return f"Opened YouTube results for '{query}'."


# ---------------------------------------------------------------------------
# Audio / display
# ---------------------------------------------------------------------------

def _volume_interface():
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def set_volume(level: int) -> str:
    try:
        vol = _volume_interface()
        level = max(0, min(100, int(level)))
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level}%."
    except ImportError:
        return "Volume control needs: pip install pycaw comtypes"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't set volume: {exc}"


def get_volume() -> str:
    try:
        vol = _volume_interface()
        current = round(vol.GetMasterVolumeLevelScalar() * 100)
        return f"Current volume is {current}%."
    except ImportError:
        return "Volume control needs: pip install pycaw comtypes"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't read volume: {exc}"


def mute_volume(mute: bool) -> str:
    try:
        vol = _volume_interface()
        vol.SetMute(1 if mute else 0, None)
        return "Muted." if mute else "Unmuted."
    except ImportError:
        return "Volume control needs: pip install pycaw comtypes"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't change mute state: {exc}"


def set_brightness(level: int) -> str:
    try:
        import screen_brightness_control as sbc

        level = max(0, min(100, int(level)))
        sbc.set_brightness(level)
        return f"Brightness set to {level}%."
    except ImportError:
        return "Brightness control needs: pip install screen-brightness-control"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't set brightness: {exc}"


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

def get_system_status() -> str:
    try:
        import psutil
    except ImportError:
        return "psutil isn't installed. Run: pip install psutil"

    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    battery = psutil.sensors_battery()
    parts = [f"CPU {cpu}%", f"RAM {mem}%", f"Disk {disk}% used"]
    if battery:
        state = "charging" if battery.power_plugged else "on battery"
        parts.append(f"Battery {battery.percent}% ({state})")
    return ", ".join(parts) + "."


def take_screenshot() -> str:
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Screenshot needs: pip install pillow"
    img = ImageGrab.grab()
    filename = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = config.SCREENSHOT_DIR / filename
    img.save(path)
    return f"Screenshot saved to {path}"


def lock_pc() -> str:
    if not IS_WINDOWS:
        return "lock_pc only supports Windows in this build."
    import ctypes

    ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
    return "Locked the workstation."


def power_action(action: str, confirmed: bool) -> str:
    if not confirmed:
        return "Not executed — this action requires explicit user confirmation first."
    if not IS_WINDOWS:
        return "power_action only supports Windows in this build."
    commands = {
        "shutdown": "shutdown /s /t 5",
        "restart": "shutdown /r /t 5",
        "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
    }
    cmd = commands.get(action)
    if not cmd:
        return f"Unknown power action '{action}'."
    os.system(cmd)
    return f"{action.capitalize()} initiated."


def get_datetime() -> str:
    return datetime.now().strftime("%A, %d %B %Y, %H:%M")


def open_path(path: str) -> str:
    if not os.path.exists(path):
        return f"Path not found: {path}"
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return f"Opened {path}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't open {path}: {exc}"


# ---------------------------------------------------------------------------
# Notes / lightweight memory
# ---------------------------------------------------------------------------

def save_note(text: str) -> str:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(config.NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text}\n")
    return "Noted."


def read_notes() -> str:
    if not config.NOTES_FILE.exists():
        return "No notes saved yet."
    content = config.NOTES_FILE.read_text(encoding="utf-8").strip()
    return content if content else "No notes saved yet."


# ---------------------------------------------------------------------------
# Dispatch table — name in tool_schemas.py -> callable here
# ---------------------------------------------------------------------------

DISPATCH = {
    "open_application": lambda i: open_application(i["app_name"]),
    "close_application": lambda i: close_application(i["app_name"]),
    "open_website": lambda i: open_website(i["site"]),
    "web_search": lambda i: web_search(i["query"]),
    "play_on_youtube": lambda i: play_on_youtube(i["query"]),
    "set_volume": lambda i: set_volume(i["level"]),
    "get_volume": lambda i: get_volume(),
    "mute_volume": lambda i: mute_volume(i["mute"]),
    "set_brightness": lambda i: set_brightness(i["level"]),
    "get_system_status": lambda i: get_system_status(),
    "take_screenshot": lambda i: take_screenshot(),
    "lock_pc": lambda i: lock_pc(),
    "power_action": lambda i: power_action(i["action"], i.get("confirmed", False)),
    "get_datetime": lambda i: get_datetime(),
    "open_path": lambda i: open_path(i["path"]),
    "save_note": lambda i: save_note(i["text"]),
    "read_notes": lambda i: read_notes(),
    # Browser automation — separate, controllable browser window that EDITH
    # can read and interact with (as opposed to open_website, which just
    # fires-and-forgets a URL to your regular browser). See agent/browser.py.
    "browser_navigate": lambda i: browser.browser_navigate(i["url"]),
    "browser_read_page": lambda i: browser.browser_read_page(),
    "browser_click": lambda i: browser.browser_click(i["index"]),
    "browser_type": lambda i: browser.browser_type(i["index"], i["text"]),
    "browser_screenshot": lambda i: browser.browser_screenshot(),
    "browser_close": lambda i: browser.browser_close(),
}


async def run_tool(name: str, tool_input: dict) -> str:
    handler = DISPATCH.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    try:
        result = handler(tool_input)
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception as exc:  # noqa: BLE001
        return f"Tool '{name}' failed: {exc}"