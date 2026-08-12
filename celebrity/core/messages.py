# -*- coding: utf-8 -*-
"""Conversation message builders and role-grammar validation.

OpenAI-compatible message shape is used as the canonical transcript so the
provider boundary stays minimal. Tool calls and results must stay paired.
"""
import json
from typing import Any, Dict, List

from ..providers.base import ToolCall

ROLE_SYSTEM = 'system'
ROLE_USER = 'user'
ROLE_ASSISTANT = 'assistant'
ROLE_TOOL = 'tool'


def system(content: str) -> Dict[str, Any]:
    return {'role': ROLE_SYSTEM, 'content': content}


def user(content: str) -> Dict[str, Any]:
    return {'role': ROLE_USER, 'content': content}


def assistant_text(content: str) -> Dict[str, Any]:
    return {'role': ROLE_ASSISTANT, 'content': content}


def assistant_tool_calls(calls: List[ToolCall]) -> Dict[str, Any]:
    return {
        'role': ROLE_ASSISTANT,
        'content': None,
        'tool_calls': [
            {
                'id': c.id,
                'type': 'function',
                'function': {
                    'name': c.name,
                    'arguments': json.dumps(c.arguments, ensure_ascii=False),
                },
            }
            for c in calls
        ],
    }


def tool_result(tool_call_id: str, content: str) -> Dict[str, Any]:
    return {'role': ROLE_TOOL, 'tool_call_id': tool_call_id, 'content': content}


def validate_sequence(messages: List[Dict[str, Any]]) -> bool:
    """Fail closed on malformed alternation (unpaired tool calls, dup users)."""
    open_calls: set = set()
    prev_role = None
    for msg in messages:
        role = msg.get('role')
        if role == ROLE_TOOL:
            call_id = msg.get('tool_call_id')
            if not call_id or call_id not in open_calls:
                raise ValueError('tool 结果缺少对应的 assistant tool call')
            open_calls.discard(call_id)
        elif role == ROLE_ASSISTANT and msg.get('tool_calls'):
            for call in msg['tool_calls']:
                open_calls.add(call.get('id'))
        elif role == ROLE_USER and prev_role == ROLE_USER:
            raise ValueError('不允许连续的 user 消息')
        prev_role = role
    return True
