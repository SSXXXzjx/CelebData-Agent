# -*- coding: utf-8 -*-
"""OpenAI-compatible chat provider (DeepSeek is the default profile).

Any provider profile with base_url / model / api_key_env in config.yaml can
be served by this class, so new OpenAI-compatible vendors need no code.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from .. import config as cfgmod
from .base import ChatResult, Provider, ProviderError, ToolCall

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip('/')
    return base if base.endswith('/chat/completions') else base + '/chat/completions'


class OpenAICompatProvider(Provider):
    name = 'openai_compat'

    def __init__(self, cfg: dict, profile: str = 'deepseek'):
        self.cfg = cfg
        self.profile = profile
        settings = cfgmod.get(cfg, f'provider.{profile}', {}) or {}
        self.base_url = settings.get('base_url') or 'https://api.deepseek.com'
        self.model = settings.get('model') or 'deepseek-chat'
        self.api_key_env = settings.get('api_key_env') or f'{profile.upper()}_API_KEY'
        self.api_key = os.environ.get(self.api_key_env, '')
        self.timeout = float(cfgmod.get(cfg, 'agent.timeout_seconds', 120) or 120)
        self.retries = max(1, int(cfgmod.get(cfg, 'agent.retries', 3) or 3))
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def check(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, f'缺少 API Key：请在 .env 中设置 {self.api_key_env}'
        return True, f'{self.profile}（{self.model}）'

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResult:
        if not self.api_key:
            raise ProviderError(f'缺少 API Key：请在 .env 中设置 {self.api_key_env}')
        payload = self._payload(messages, tools, temperature, max_tokens, stream=False)

        last_exc: Optional[ProviderError] = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.client.post(
                    _endpoint(self.base_url),
                    json=payload,
                    headers={'Authorization': f'Bearer {self.api_key}'},
                )
                if resp.status_code == 401:
                    raise ProviderError(f'API Key 无效或未配置（{self.api_key_env}）')
                if resp.status_code in _RETRYABLE_STATUS:
                    last_exc = ProviderError(
                        f'服务端错误 HTTP {resp.status_code}（第 {attempt}/{self.retries} 次）',
                        retriable=True)
                    time.sleep(min(2 ** attempt, 8))
                    continue
                resp.raise_for_status()
                return self._parse(resp.json())
            except ProviderError as exc:
                if not exc.retriable:
                    raise
                last_exc = exc
            except httpx.HTTPStatusError as exc:
                last_exc = ProviderError(f'HTTP {exc.response.status_code}', retriable=True)
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8))
            except httpx.HTTPError as exc:
                last_exc = ProviderError(f'网络错误: {exc}', retriable=True)
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8))
        raise ProviderError(str(last_exc or '请求失败'), retriable=True)

    def _payload(self, messages, tools, temperature, max_tokens, stream=False):
        payload: Dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature if temperature is not None else 0.3,
        }
        if max_tokens:
            payload['max_tokens'] = max_tokens
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'
        if stream:
            payload['stream'] = True
        return payload

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Stream an OpenAI-compatible completion (SSE).

        Yields {'type': 'text', 'delta': str} events and finally
        {'type': 'done', 'result': ChatResult} (tool calls are aggregated).
        """
        if not self.api_key:
            raise ProviderError(f'缺少 API Key：请在 .env 中设置 {self.api_key_env}')
        payload = self._payload(messages, tools, temperature, max_tokens, stream=True)
        payload['stream_options'] = {'include_usage': True}
        last_exc: Optional[ProviderError] = None
        for attempt in range(1, self.retries + 1):
            started = False
            try:
                with self.client.stream(
                    'POST', _endpoint(self.base_url), json=payload,
                    headers={'Authorization': f'Bearer {self.api_key}'},
                ) as resp:
                    if resp.status_code == 401:
                        raise ProviderError(f'API Key 无效或未配置（{self.api_key_env}）')
                    if resp.status_code in (400, 422) and payload.get('stream_options'):
                        payload.pop('stream_options', None)  # provider may reject include_usage
                        continue
                    if resp.status_code in _RETRYABLE_STATUS:
                        last_exc = ProviderError(
                            f'服务端错误 HTTP {resp.status_code}（第 {attempt}/{self.retries} 次）',
                            retriable=True)
                        time.sleep(min(2 ** attempt, 8))
                        continue
                    resp.raise_for_status()
                    content_parts: List[str] = []
                    tool_slots: Dict[int, Dict[str, str]] = {}
                    finish_reason = None
                    usage = None
                    for line in resp.iter_lines():
                        line = (line or '').strip()
                        if not line or line.startswith(':'):
                            continue
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choice = (chunk.get('choices') or [{}])[0]
                        delta = choice.get('delta') or {}
                        finish_reason = choice.get('finish_reason') or finish_reason
                        if chunk.get('usage'):
                            usage = chunk['usage']
                        text = delta.get('content')
                        if text:
                            started = True
                            content_parts.append(text)
                            yield {'type': 'text', 'delta': text}
                        for tc in delta.get('tool_calls') or []:
                            started = True
                            index = tc.get('index', 0)
                            slot = tool_slots.setdefault(index, {'id': '', 'name': '', 'arguments': ''})
                            if tc.get('id'):
                                slot['id'] = tc['id']
                            fn = tc.get('function') or {}
                            if fn.get('name'):
                                slot['name'] = fn['name']
                            if fn.get('arguments'):
                                slot['arguments'] += fn['arguments']
                    calls = []
                    for index in sorted(tool_slots):
                        slot = tool_slots[index]
                        try:
                            arguments = json.loads(slot['arguments'] or '{}')
                        except json.JSONDecodeError:
                            arguments = {}
                        calls.append(ToolCall(id=slot['id'], name=slot['name'], arguments=arguments))
                    result = ChatResult(
                        content=''.join(content_parts) or None,
                        tool_calls=calls,
                        finish_reason=finish_reason,
                        usage=usage,
                    )
                    yield {'type': 'done', 'result': result}
                    return
            except ProviderError as exc:
                if not exc.retriable:
                    raise
                last_exc = exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 422) and payload.get('stream_options'):
                    payload.pop('stream_options', None)
                    continue
                retriable = exc.response.status_code in _RETRYABLE_STATUS
                last_exc = ProviderError(f'HTTP {exc.response.status_code}', retriable=retriable)
                if not retriable:
                    raise
            except httpx.HTTPError as exc:
                last_exc = ProviderError(f'网络错误: {exc}', retriable=True)
            if started:
                raise ProviderError(f'流式输出中断: {last_exc}', retriable=False)
            if attempt < self.retries:
                time.sleep(min(2 ** attempt, 8))
        raise ProviderError(str(last_exc or '请求失败'), retriable=True)

    @staticmethod
    def _parse(data: Dict[str, Any]) -> ChatResult:
        choices = data.get('choices') or []
        if not choices:
            raise ProviderError('响应缺少 choices')
        message = choices[0].get('message') or {}
        content = message.get('content')
        calls = []
        for item in message.get('tool_calls') or []:
            fn = item.get('function') or {}
            try:
                arguments = json.loads(fn.get('arguments') or '{}')
            except json.JSONDecodeError:
                arguments = {}
            calls.append(ToolCall(id=item.get('id', ''), name=fn.get('name', ''), arguments=arguments))
        return ChatResult(
            content=content,
            tool_calls=calls,
            finish_reason=choices[0].get('finish_reason'),
            usage=data.get('usage'),
        )
