"""
LLM providers.

Each provider owns its own tool-calling loop end-to-end, in its native
message format — Anthropic and OpenAI don't represent conversation history
the same way, and normalizing that away would just add a translation layer
that could silently drop information. Instead, core.py depends only on the
run_turn() contract below; it never sees provider-specific message shapes.

To add a third provider (Gemini, a local model, etc.), write one more class
implementing run_turn() and add one line to build_provider(). Nothing else
in the codebase changes.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol

from config import config

MAX_TOOL_ITERATIONS = 6
STEP_LIMIT_MESSAGE = "That took more steps than expected — try breaking the request down."

OnToolCall = Callable[[str, dict], Any]  # returns str or an awaitable resolving to str
OnState = Callable[[str, str], None]


class LLMProvider(Protocol):
    name: str

    async def run_turn(
        self,
        history: list[Any],
        user_text: str,
        system_prompt: str,
        on_tool_call: OnToolCall,
        on_state: OnState,
    ) -> tuple[str, list[Any]]:
        """Runs one full user turn, including any tool calls, and returns
        (final_text, updated_history)."""
        ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        from anthropic import AsyncAnthropic
        from agent.tool_schemas import TOOLS

        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.tools = TOOLS

    async def run_turn(self, history, user_text, system_prompt, on_tool_call, on_state):
        history = list(history)
        history.append({"role": "user", "content": user_text})

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            on_state("thinking", "")
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                tools=self.tools,
                messages=history,
            )
            history.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                final_text = "".join(
                    block.text for block in response.content if block.type == "text"
                ).strip()
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                on_state("acting", block.name)
                result = await on_tool_call(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
            history.append({"role": "user", "content": tool_results})
        else:
            final_text = STEP_LIMIT_MESSAGE

        return final_text, history


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        from openai import AsyncOpenAI
        from agent.tool_schemas import OPENAI_TOOLS

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.tools = OPENAI_TOOLS

    async def run_turn(self, history, user_text, system_prompt, on_tool_call, on_state):
        input_list = list(history)
        input_list.append({"role": "user", "content": user_text})

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            on_state("thinking", "")
            response = await self.client.responses.create(
                model=self.model,
                instructions=system_prompt,
                tools=self.tools,
                input=input_list,
                max_output_tokens=self.max_tokens,
            )
            input_list += response.output

            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                final_text = (response.output_text or "").strip()
                break

            for call in calls:
                on_state("acting", call.name)
                args = json.loads(call.arguments) if call.arguments else {}
                result = await on_tool_call(call.name, args)
                input_list.append(
                    {"type": "function_call_output", "call_id": call.call_id, "output": result}
                )
        else:
            final_text = STEP_LIMIT_MESSAGE

        return final_text, input_list


class GeminiProvider:
    """
    Google AI Studio / Gemini API. Genuinely free for Flash-class models,
    no credit card — see README for the current rate limits and the one
    real tradeoff (free-tier prompts may be used to improve Google's
    products; paid tier does not have this clause).

    Note: this is the one provider I couldn't fully verify against a live
    API call from the build environment — Gemini's function-calling wire
    format was the least consistent across Google's own documentation
    while building this. The logic below follows the most-corroborated
    pattern (manual function-calling via google.genai.types), but if you
    hit an error here, check https://ai.google.dev/gemini-api/docs/function-calling
    against the exact version of `google-genai` you have installed —
    this is the most likely spot needing a small adjustment.
    """

    name = "gemini"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        from google import genai
        from google.genai import types
        from agent.tool_schemas import TOOLS

        self.client = genai.Client(api_key=api_key)
        self.types = types
        self.model = model
        self.max_tokens = max_tokens
        self.tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t["description"],
                        parameters=t["input_schema"],
                    )
                    for t in TOOLS
                ]
            )
        ]

    async def run_turn(self, history, user_text, system_prompt, on_tool_call, on_state):
        types = self.types
        contents = list(history)
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            on_state("thinking", "")
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=self.tools,
                    max_output_tokens=self.max_tokens,
                ),
            )
            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [
                part.function_call for part in candidate.content.parts if part.function_call
            ]
            if not function_calls:
                final_text = (response.text or "").strip()
                break

            response_parts = []
            for fc in function_calls:
                on_state("acting", fc.name)
                args = dict(fc.args) if fc.args else {}
                result = await on_tool_call(fc.name, args)
                response_parts.append(
                    types.Part.from_function_response(name=fc.name, response={"result": result})
                )
            contents.append(types.Content(role="user", parts=response_parts))
        else:
            final_text = STEP_LIMIT_MESSAGE

        return final_text, contents


class GroqProvider:
    """
    Groq's free tier: no credit card, gated only by rate limits (fast
    inference on open-weight models like Llama 3.3). Groq exposes an
    OpenAI-compatible Chat Completions endpoint, so this reuses the
    `openai` SDK pointed at Groq's base URL instead of a separate
    dependency.
    """

    name = "groq"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        from openai import AsyncOpenAI
        from agent.tool_schemas import CHAT_COMPLETIONS_TOOLS

        self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.model = model
        self.max_tokens = max_tokens
        self.tools = CHAT_COMPLETIONS_TOOLS

    async def run_turn(self, history, user_text, system_prompt, on_tool_call, on_state):
        messages = list(history)
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = system_prompt
        else:
            messages.insert(0, {"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_text})

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            on_state("thinking", "")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                max_tokens=self.max_tokens,
            )
            choice = response.choices[0]
            messages.append(choice.message.model_dump(exclude_none=True))

            tool_calls = choice.message.tool_calls
            if not tool_calls:
                final_text = (choice.message.content or "").strip()
                break

            for call in tool_calls:
                on_state("acting", call.function.name)
                args = json.loads(call.function.arguments) if call.function.arguments else {}
                result = await on_tool_call(call.function.name, args)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )
        else:
            final_text = STEP_LIMIT_MESSAGE

        return final_text, messages


def build_provider() -> LLMProvider:
    if config.LLM_PROVIDER == "openai":
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env.")
        return OpenAIProvider(config.OPENAI_API_KEY, config.OPENAI_MODEL, config.MAX_TOKENS)

    if config.LLM_PROVIDER == "gemini":
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to .env.")
        return GeminiProvider(config.GEMINI_API_KEY, config.GEMINI_MODEL, config.MAX_TOKENS)

    if config.LLM_PROVIDER == "groq":
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing. Add it to .env.")
        return GroqProvider(config.GROQ_API_KEY, config.GROQ_MODEL, config.MAX_TOKENS)

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is missing. Add it to .env.")
    return AnthropicProvider(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL, config.MAX_TOKENS)