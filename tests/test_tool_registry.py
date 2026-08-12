# -*- coding: utf-8 -*-
"""Registry: schema visibility, validation, risk gate, dispatch."""

import json

import pytest

from celebrity.security import RISK_DESTRUCTIVE, RISK_WRITE
from celebrity.tools.base import ToolContext, ToolResult, ToolSpec
from celebrity.tools.registry import ToolRegistry


def make_registry():
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name='echo',
        description='echo a message',
        parameters={'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text']},
        handler=lambda ctx, text: {'echo': text},
        risk='read',
    ))
    reg.register(ToolSpec(
        name='boom',
        description='always fails',
        parameters={'type': 'object', 'properties': {}},
        handler=lambda ctx: (_ for _ in ()).throw(RuntimeError('bad input')),
        risk='read',
    ))
    reg.register(ToolSpec(
        name='wipe',
        description='destructive op',
        parameters={'type': 'object', 'properties': {}},
        handler=lambda ctx: 'wiped',
        risk=RISK_DESTRUCTIVE,
    ))
    return reg


def ctx(risks=('read',), confirm=None):
    return ToolContext(cfg={}, work_dirs={}, allowed_risks=risks, confirm=confirm)


def test_definitions_contain_schema():
    reg = make_registry()
    names = [d['function']['name'] for d in reg.definitions()]
    assert 'echo' in names
    echo = next(d for d in reg.definitions() if d['function']['name'] == 'echo')
    assert echo['function']['parameters']['required'] == ['text']


def test_dispatch_ok():
    reg = make_registry()
    out = json.loads(reg.dispatch('echo', {'text': 'hi'}, ctx()))
    assert out['ok'] is True
    assert out['data']['echo'] == 'hi'


def test_missing_required_arg_fails():
    reg = make_registry()
    out = json.loads(reg.dispatch('echo', {}, ctx()))
    assert out['ok'] is False
    assert '缺少必要参数' in out['content']


def test_risk_gate_denies():
    reg = make_registry()
    out = json.loads(reg.dispatch('wipe', {}, ctx(risks=('read',))))
    assert out['ok'] is False
    assert '未授权' in out['content']


def test_destructive_requires_confirmation():
    reg = make_registry()
    denied = json.loads(reg.dispatch('wipe', {}, ctx(risks=('read', RISK_DESTRUCTIVE), confirm=lambda q: False)))
    assert denied['ok'] is False
    allowed = json.loads(reg.dispatch('wipe', {}, ctx(risks=('read', RISK_DESTRUCTIVE), confirm=lambda q: True)))
    assert allowed['ok'] is True


def test_handler_exception_returns_structured_error():
    reg = make_registry()
    out = json.loads(reg.dispatch('boom', {}, ctx()))
    assert out['ok'] is False
    assert 'bad input' in out['content']


def test_unknown_tool():
    reg = make_registry()
    out = json.loads(reg.dispatch('nope', {}, ctx()))
    assert out['ok'] is False


def test_tool_result_json_roundtrip():
    r = ToolResult.success('ok', {'n': 1})
    parsed = json.loads(r.to_json())
    assert parsed['ok'] is True and parsed['data']['n'] == 1
