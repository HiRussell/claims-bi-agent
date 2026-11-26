"""Minimal model client with tool calling (standard library only). Two wire formats:

- LLM_API_STYLE=chat       POST {base}/chat/completions. Works with any OpenAI-compatible server (hosted or local).
- LLM_API_STYLE=responses  POST {base}/responses. OpenAI's newer endpoint; needed when an OpenAI reasoning model
                           should reason AND call function tools in the same loop.

Both return the same shape to the agent: {"content": str, "tool_calls": [{"id", "function": {"name", "arguments"}}]}.
Configuration comes from environment variables (see .env.example). A .env file in the repository root is read
if present; real environment variables win over it.
"""
import json
import os
import time
import urllib.error
import urllib.request

from contract import log

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env_file(path: str = _ENV_FILE) -> None:
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LLMError(Exception):
    pass


class ChatClient:
    def __init__(self):
        load_env_file()
        self.base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "")
        self.style = os.environ.get("LLM_API_STYLE", "chat").strip().lower() or "chat"
        if self.style not in ("chat", "responses"):
            raise LLMError("LLM_API_STYLE must be 'chat' or 'responses'.")
        self.effort = os.environ.get("LLM_REASONING_EFFORT", "").strip().lower()
        temperature = os.environ.get("LLM_TEMPERATURE", "").strip()
        self.temperature = float(temperature) if temperature else None
        if not self.model:
            raise LLMError("LLM_MODEL is not set. Copy .env.example to .env and fill it in.")

    def chat(self, messages: list, tools: list, timeout: float) -> dict:
        """Return the assistant message: {"content": str, "tool_calls": [...]} (plus "_raw_output" for responses)."""
        body = self._responses_body(messages, tools) if self.style == "responses" else self._chat_body(messages, tools)
        deadline = time.monotonic() + timeout
        last_error = "no attempt made"
        for attempt in range(4):
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                break
            try:
                data = self._post(body, remaining)
                usage = data.get("usage") or {}
                log(f"[llm] usage in={usage.get('input_tokens', usage.get('prompt_tokens', 0))} "
                    f"out={usage.get('output_tokens', usage.get('completion_tokens', 0))}")
                return self._parse_responses(data) if self.style == "responses" else data["choices"][0]["message"]
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                last_error = f"HTTP {e.code}: {detail}"
                if e.code == 400 and self._drop_rejected_option(body, detail):
                    continue                           # an optional knob this model does not accept: retry without it
                if e.code not in (408, 409, 429, 500, 502, 503, 504, 529):
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_error = f"network error: {e}"
            except (KeyError, IndexError, ValueError, TypeError) as e:
                last_error = f"unexpected response shape: {e}"
            log(f"[llm] attempt {attempt + 1} failed: {last_error}")
            time.sleep(min(2 ** attempt, max(0.0, deadline - time.monotonic())))
        raise LLMError(f"model call failed: {last_error}")

    @staticmethod
    def _drop_rejected_option(body: dict, detail: str) -> bool:
        text = detail.lower()
        for key in ("temperature", "reasoning_effort", "reasoning"):
            if key in body and key.split("_")[0] in text:
                body.pop(key)
                log(f"[llm] the endpoint rejected '{key}'; retrying without it")
                return True
        return False

    # ---- chat-completions format ------------------------------------------------------------------------
    def _chat_body(self, messages: list, tools: list) -> dict:
        clean = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
        body = {"model": self.model, "messages": clean, "tools": tools, "tool_choice": "auto"}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.effort:
            body["reasoning_effort"] = self.effort
        return body

    # ---- responses format -------------------------------------------------------------------------------
    def _responses_body(self, messages: list, tools: list) -> dict:
        """Translate the agent's chat-style history. The call is stateless (store=false): every output item of
        earlier turns, including reasoning items, is replayed in order, followed by the tool results."""
        instructions, items = "", []
        for m in messages:
            role = m.get("role")
            if role == "system":
                instructions = m.get("content") or ""
            elif role == "user":
                items.append({"role": "user", "content": m.get("content") or ""})
            elif role == "assistant":
                if m.get("_raw_output") is not None:
                    items.extend(m["_raw_output"])
                elif m.get("content"):
                    items.append({"role": "assistant", "content": m["content"]})
            elif role == "tool":
                items.append({"type": "function_call_output", "call_id": m.get("tool_call_id", ""),
                              "output": m.get("content") or ""})
        body = {"model": self.model, "instructions": instructions, "input": items, "store": False,
                "tool_choice": "auto",
                "tools": [{"type": "function", "name": t["function"]["name"],
                           "description": t["function"]["description"],
                           "parameters": t["function"]["parameters"]} for t in tools]}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.effort:
            body["reasoning"] = {"effort": self.effort}
        return body

    @staticmethod
    def _parse_responses(data: dict) -> dict:
        output = data["output"]
        text, calls = [], []
        for item in output:
            if item.get("type") == "function_call":
                calls.append({"id": item["call_id"], "type": "function",
                              "function": {"name": item["name"], "arguments": item.get("arguments") or "{}"}})
            elif item.get("type") == "message":
                text += [part.get("text", "") for part in item.get("content") or [] if part.get("type") == "output_text"]
        return {"content": "".join(text), "tool_calls": calls, "_raw_output": output}

    def _post(self, body: dict, timeout: float) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        path = "/responses" if self.style == "responses" else "/chat/completions"
        req = urllib.request.Request(f"{self.base_url}{path}", data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
