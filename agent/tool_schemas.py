"""
Tool schemas for the Claude API's tool-use (function calling).

This is the contract between the LLM brain and the real-world actions in
tools.py. To give EDITH a new power later:
  1. Write the Python function in tools.py
  2. Add its schema here
  3. Add one line to the dispatch table in agent/core.py
That's the whole extension path — this is what "grows higher" means in
practice, not a vague promise.
"""

TOOLS = [
    {
        "name": "open_application",
        "description": (
            "Open a desktop application on the user's Windows machine, e.g. "
            "notepad, calculator, chrome, spotify, vs code, file explorer, "
            "task manager, settings, word, excel, powerpoint, paint, cmd, "
            "powershell. Use this whenever the user asks to open, launch, "
            "start, or run a program."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the application, e.g. 'notepad', 'chrome', 'spotify'.",
                }
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "close_application",
        "description": "Close/terminate a running application by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the application to close, e.g. 'notepad', 'chrome'.",
                }
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "open_website",
        "description": (
            "Open a website in the default browser. Accepts a full URL or a "
            "common site name (youtube, google, github, gmail, netflix, "
            "amazon, reddit, wikipedia, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "site": {
                    "type": "string",
                    "description": "URL or common site name, e.g. 'youtube.com' or 'youtube'.",
                }
            },
            "required": ["site"],
        },
    },
    {
        "name": "web_search",
        "description": "Open a Google search in the browser for the given query.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to search for."}},
            "required": ["query"],
        },
    },
    {
        "name": "play_on_youtube",
        "description": "Open YouTube search results for a song, artist, or video the user wants to play.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Song, artist, or video to search for."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "set_volume",
        "description": "Set the system master volume to an exact level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level from 0 (silent) to 100 (max).",
                }
            },
            "required": ["level"],
        },
    },
    {
        "name": "get_volume",
        "description": "Get the current system master volume level (0-100).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "mute_volume",
        "description": "Mute or unmute the system audio.",
        "input_schema": {
            "type": "object",
            "properties": {"mute": {"type": "boolean", "description": "True to mute, false to unmute."}},
            "required": ["mute"],
        },
    },
    {
        "name": "set_brightness",
        "description": "Set the primary display brightness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Brightness from 0 to 100."}
            },
            "required": ["level"],
        },
    },
    {
        "name": "get_system_status",
        "description": (
            "Get live system vitals: battery percentage and charging state, "
            "CPU usage percent, RAM usage percent, and free disk space. Use "
            "this whenever the user asks how the system/PC/battery is doing."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "take_screenshot",
        "description": "Capture the current screen and save it to disk. Returns the saved file path.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "lock_pc",
        "description": "Lock the workstation immediately (Win+L equivalent).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "power_action",
        "description": (
            "Shut down, restart, or sleep the machine. This is destructive — "
            "only call this after the user has clearly confirmed in the "
            "conversation that they want to proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["shutdown", "restart", "sleep"],
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true. Only set true if the user explicitly confirmed.",
                },
            },
            "required": ["action", "confirmed"],
        },
    },
    {
        "name": "get_datetime",
        "description": "Get the current date and time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "open_path",
        "description": "Open a file or folder on disk in its default application / File Explorer.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute or relative file/folder path."}},
            "required": ["path"],
        },
    },
    {
        "name": "save_note",
        "description": (
            "Save a short piece of text to EDITH's persistent notes file so it "
            "can be recalled later — reminders, ideas, to-dos the user dictates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The note content."}},
            "required": ["text"],
        },
    },
    {
        "name": "read_notes",
        "description": "Read back all saved notes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_navigate",
        "description": (
            "Open a URL in an automated, controllable browser window — separate "
            "from the user's regular browser — that EDITH can subsequently read "
            "and interact with (click, type). Use this instead of open_website "
            "whenever the task requires doing something ON the page afterward, "
            "not just viewing it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to open."}},
            "required": ["url"],
        },
    },
    {
        "name": "browser_read_page",
        "description": (
            "List the clickable/typeable elements currently visible on the "
            "automated browser's page, each with an index number. Call this "
            "after navigating, and again after any action that might have "
            "changed the page, before clicking or typing."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_click",
        "description": "Click the element at the given index (from the most recent browser_read_page call).",
        "input_schema": {
            "type": "object",
            "properties": {"index": {"type": "integer", "description": "Element index to click."}},
            "required": ["index"],
        },
    },
    {
        "name": "browser_type",
        "description": (
            "Click the element at the given index and type the given text into "
            "it. Works for normal inputs and for rich editors that capture real "
            "keystrokes (e.g. code editors like Monaco/CodeMirror on coding "
            "sites), since this types via simulated keyboard input rather than "
            "setting a value directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "Element index to click before typing."},
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["index", "text"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "Take a screenshot of the automated browser's current page and save it to disk.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_close",
        "description": "Close the automated browser window when done with it.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """
    Converts the Anthropic-shaped schemas above (which use 'input_schema')
    into OpenAI Responses API tool schemas (flat, using 'parameters'). One
    tool list, two providers — no duplicated definitions to keep in sync.
    """
    converted = []
    for t in anthropic_tools:
        converted.append(
            {
                "type": "function",
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            }
        )
    return converted


OPENAI_TOOLS = to_openai_tools(TOOLS)


def to_chat_completions_tools(anthropic_tools: list[dict]) -> list[dict]:
    """
    Converts to the older (but universally supported) OpenAI Chat
    Completions tool format — nested under 'function'. Used for any
    OpenAI-compatible endpoint that doesn't support the newer Responses
    API, e.g. Groq.
    """
    converted = []
    for t in anthropic_tools:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
        )
    return converted


CHAT_COMPLETIONS_TOOLS = to_chat_completions_tools(TOOLS)