# -*- coding: utf-8 -*-
"""Narrow-waist agent: conversation loop plus tool dispatch.

Entrypoints (CLI, future gateway/batch) configure this Agent; they never own
a second conversation engine.
"""
import time
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .. import config as cfgmod
from ..providers.base import Provider, ProviderError
from ..tools.base import ToolContext
from ..tools.registry import ToolRegistry
from . import messages as msg


@dataclass
class RunResult:
    content: str
    turns: int
    tool_calls: int
    messages: List[Dict[str, Any]]


class UIHooks:
    """Optional UI callbacks. All are no-ops by default, so core behavior is
    unchanged when the UI layer does not pass hooks."""

    def on_stream_start(self):
        pass

    def on_delta(self, delta: str):
        pass

    def on_stream_end(self, content: str):
        pass

    def on_tool_start(self, name: str):
        pass

    def on_tool(self, name: str, ok: bool, summary: str):
        pass


class Agent:
    def __init__(
        self,
        cfg: dict,
        provider: Provider,
        tools: ToolRegistry,
        ctx: ToolContext,
        system_prompt: Optional[str] = None,
    ):
        self.cfg = cfg
        self.provider = provider
        self.tools = tools
        self.ctx = ctx
        self.system_prompt = system_prompt or ''
        self.messages: List[Dict[str, Any]] = [msg.system(self.system_prompt)]
        self.temperature = float(cfgmod.get(cfg, 'agent.temperature', 0.3) or 0.3)
        self.max_turns = int(cfgmod.get(cfg, 'agent.max_turns', 12) or 12)
        # Cumulative session metrics for the status bar / main page.
        self.usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        self.elapsed = 0.0
        self.turn_count = 0
        self.last_tool: Optional[str] = None

    def reset(self):
        self.messages = [msg.system(self.system_prompt)]

    def run(self, user_input: str, reset: bool = False, hooks: Optional[UIHooks] = None) -> RunResult:
        """One user turn: model request/tool-call loop until final content."""
        hooks = hooks or UIHooks()
        if reset:
            self.reset()
        self.messages.append(msg.user(user_input))
        msg.validate_sequence(self.messages)

        tool_calls = 0
        for turn in range(1, self.max_turns + 1):
            started = time.monotonic()
            try:
                result = self._chat(hooks)
            except ProviderError as exc:
                raise AgentError(self.ctx.redact(str(exc))) from exc
            self.elapsed += time.monotonic() - started
            self.turn_count += 1
            for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                self.usage[key] += int((result.usage or {}).get(key, 0) or 0)

            if result.tool_calls:
                self.messages.append(msg.assistant_tool_calls(result.tool_calls))
                for call in result.tool_calls:
                    self.last_tool = call.name
                    hooks.on_tool_start(call.name)
                    output = self.tools.dispatch(call.name, call.arguments, self.ctx)
                    self.messages.append(msg.tool_result(call.id, output))
                    try:
                        parsed = json.loads(output)
                        ok = bool(parsed.get('ok', False))
                        summary = str(parsed.get('content', ''))[:160]
                    except Exception:
                        ok, summary = True, output[:160]
                    hooks.on_tool(call.name, ok, summary)
                    tool_calls += 1
                msg.validate_sequence(self.messages)
                continue

            content = (result.content or '').strip()
            self.messages.append(msg.assistant_text(content))
            return RunResult(content=content, turns=turn, tool_calls=tool_calls, messages=self.messages)

        return RunResult(
            content='已达到最大工具轮次，未得到最终回答。请简化任务或分步执行。',
            turns=self.max_turns,
            tool_calls=tool_calls,
            messages=self.messages,
        )

    def _chat(self, hooks: UIHooks) -> Any:
        """Call the provider; streams through hooks when the provider supports it."""
        streamer = getattr(self.provider, 'chat_stream', None)
        if streamer is None:
            hooks.on_stream_start()
            result = self.provider.chat(
                self.messages,
                tools=self.tools.definitions(),
                temperature=self.temperature,
            )
            hooks.on_stream_end(result.content or '')
            return result
        hooks.on_stream_start()
        result = None
        for event in streamer(
            self.messages,
            tools=self.tools.definitions(),
            temperature=self.temperature,
        ):
            if event['type'] == 'text':
                hooks.on_delta(event['delta'])
            elif event['type'] == 'done':
                result = event['result']
        hooks.on_stream_end(result.content or '' if result is not None else '')
        return result


class AgentError(Exception):
    """Structured, redacted agent failure."""
