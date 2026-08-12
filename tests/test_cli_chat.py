# -*- coding: utf-8 -*-
"""Chat session lifecycle: reuse across main-page round trips, wizard cancel."""

from types import SimpleNamespace

from celebrity import cli


class _FakeStdin:
    def __init__(self, text):
        self._lines = iter(text.splitlines(keepends=True))

    def isatty(self):
        return False

    def readline(self):
        return next(self._lines, '')


def _make_state(cfg):
    ctx = cli.build_ctx(cfg, confirm=lambda q: True, interactive=True)
    agent, _provider, _tools = cli.build_agent(cfg, ctx)
    return {'agent': agent}


def test_chat_reuses_existing_agent(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(cli.cfgmod, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.stdin', _FakeStdin('/exit\n'))
    state = _make_state(cfg)
    agent = state['agent']
    cli.cmd_chat(cfg, SimpleNamespace(config=None), state=state)
    assert state['agent'] is agent


def test_chat_wizard_cancel_keeps_conversation(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(cli.cfgmod, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.stdin', _FakeStdin('/model\n/exit\n'))
    state = _make_state(cfg)
    agent = state['agent']
    agent.messages.append({'role': 'user', 'content': '你好'})
    before = len(agent.messages)

    def _cancel(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.slash, 'run_slash', _cancel)
    cli.cmd_chat(cfg, SimpleNamespace(config=None), state=state)
    assert state['agent'] is agent
    assert len(agent.messages) == before
