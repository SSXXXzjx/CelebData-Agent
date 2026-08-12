# -*- coding: utf-8 -*-
"""OpenAI-compatible provider over httpx MockTransport."""

import json

import httpx
import pytest

from celebrity.providers.base import ProviderError
from celebrity.providers.openai_compat import OpenAICompatProvider


def make_provider(cfg, handler, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-test')
    provider = OpenAICompatProvider(cfg, profile='deepseek')
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    return provider


def test_chat_parses_tool_calls(cfg, monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert body['model'] == 'deepseek-v4-flash'
        assert body['tools'][0]['function']['name'] == 'add'
        return httpx.Response(200, json={
            'choices': [{
                'message': {
                    'content': None,
                    'tool_calls': [{
                        'id': 'call_1',
                        'type': 'function',
                        'function': {'name': 'add', 'arguments': '{"a":1,"b":2}'},
                    }],
                },
                'finish_reason': 'tool_calls',
            }],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        })

    provider = make_provider(cfg, handler, monkeypatch)
    result = provider.chat(
        [{'role': 'user', 'content': 'hi'}],
        tools=[{'type': 'function', 'function': {'name': 'add', 'parameters': {}}}],
    )
    assert result.tool_calls[0].name == 'add'
    assert result.tool_calls[0].arguments == {'a': 1, 'b': 2}
    assert result.finish_reason == 'tool_calls'
    assert result.usage == {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}


def test_retry_then_success(cfg, monkeypatch):
    calls = {'n': 0}

    def handler(request):
        calls['n'] += 1
        if calls['n'] == 1:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={
            'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]
        })

    provider = make_provider(cfg, handler, monkeypatch)
    result = provider.chat([{'role': 'user', 'content': 'x'}])
    assert result.content == 'ok'
    assert calls['n'] == 2


def test_unauthorized_fails_fast(cfg, monkeypatch):
    def handler(request):
        return httpx.Response(401, json={})

    provider = make_provider(cfg, handler, monkeypatch)
    with pytest.raises(ProviderError) as exc:
        provider.chat([{'role': 'user', 'content': 'x'}])
    assert 'API Key' in str(exc.value)


def test_missing_key_fails_actionably(cfg, monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    provider = OpenAICompatProvider(cfg, profile='deepseek')
    with pytest.raises(ProviderError) as exc:
        provider.chat([{'role': 'user', 'content': 'x'}])
    assert 'DEEPSEEK_API_KEY' in str(exc.value)


def test_chat_stream_parses_sse(cfg, monkeypatch):
    events = [
        {'choices': [{'delta': {'content': '你'}, 'finish_reason': None}]},
        {'choices': [{'delta': {'content': '好'}, 'finish_reason': 'stop'}]},
        {'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
    ]
    body = ''.join(f'data: {json.dumps(e)}\n\n' for e in events) + 'data: [DONE]\n\n'

    def handler(request):
        return httpx.Response(
            200, content=body.encode(), headers={'content-type': 'text/event-stream'})

    provider = make_provider(cfg, handler, monkeypatch)
    got = list(provider.chat_stream([{'role': 'user', 'content': 'hi'}]))
    texts = [e['delta'] for e in got if e['type'] == 'text']
    assert texts == ['你', '好']
    done = got[-1]
    assert done['type'] == 'done'
    assert done['result'].content == '你好'
    assert done['result'].usage['total_tokens'] == 15


def test_chat_stream_aggregates_tool_call_arguments(cfg, monkeypatch):
    events = [
        {'choices': [{'delta': {'tool_calls': [
            {'index': 0, 'id': 'call_1', 'function': {'name': 'add', 'arguments': '{"a":'}}]}}]},
        {'choices': [{'delta': {'tool_calls': [
            {'index': 0, 'function': {'arguments': '1,"b":2}'}}]}}]},
        {'choices': [{'delta': {}, 'finish_reason': 'tool_calls'}]},
    ]
    body = ''.join(f'data: {json.dumps(e)}\n\n' for e in events) + 'data: [DONE]\n\n'

    def handler(request):
        return httpx.Response(
            200, content=body.encode(), headers={'content-type': 'text/event-stream'})

    provider = make_provider(cfg, handler, monkeypatch)
    got = list(provider.chat_stream([{'role': 'user', 'content': 'x'}]))
    done = got[-1]
    call = done['result'].tool_calls[0]
    assert call.id == 'call_1'
    assert call.name == 'add'
    assert call.arguments == {'a': 1, 'b': 2}
