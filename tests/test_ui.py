# -*- coding: utf-8 -*-
"""Slash-command autocomplete behavior."""

from types import SimpleNamespace

import pytest
from prompt_toolkit.document import Document

from celebrity.ui import (
    SlashCompleter,
    _chat_key_bindings,
    format_elapsed,
    format_tokens,
    plain_markdown,
)

COMMANDS = {
    'model': ['m', '模型', 'provider'],
    'apikey': ['key'],
    'cookie': ['ck'],
    'vision': ['视觉'],
    'status': ['s'],
    'help': ['h'],
    'exit': [],
}


def completions_for(text):
    return list(SlashCompleter(COMMANDS).get_completions(Document(text)))


def test_slash_prefix_matches_canonical():
    found = completions_for('/m')
    assert len(found) == 1
    assert found[0].text == 'model'


def test_chinese_alias_matches():
    found = completions_for('/模型')
    assert any(c.text == 'model' for c in found)


def test_no_completion_without_slash():
    assert completions_for('hello') == []


def test_no_completion_when_space_present():
    assert completions_for('/model xx') == []


def test_empty_prefix_lists_all():
    found = completions_for('/')
    names = {c.text for c in found}
    assert 'model' in names and 'exit' in names


def test_escape_binding_raises_keyboard_interrupt():
    kb = _chat_key_bindings()
    bindings = kb.get_bindings_for_keys(('escape',))
    assert bindings, 'escape 必须绑定'
    with pytest.raises(KeyboardInterrupt):
        bindings[0].handler(SimpleNamespace())


def test_print_agent_renders_markdown():
    from celebrity import ui

    with ui.console.capture() as cap:
        ui.print_agent('**加粗** 和 `code` 以及 - 列表')
    text = cap.get()
    assert '**' not in text
    assert '加粗' in text


def test_format_elapsed():
    assert format_elapsed(18) == '18s'
    assert format_elapsed(133) == '2m 13s'
    assert format_elapsed(3900) == '1h 05m'


def test_format_tokens():
    assert format_tokens(500) == '500'
    assert format_tokens(1234) == '1.2k'


def test_plain_markdown_strips_markers():
    assert plain_markdown('**加粗** 和 `code` 以及 # 标题') == '加粗 和 code 以及 # 标题'
    assert plain_markdown('# 标题\n**加粗**') == '标题\n加粗'


def test_stream_ui_emits_plain_text(capsys, cfg):
    import time
    from types import SimpleNamespace

    from celebrity import ui

    agent = SimpleNamespace(usage={'total_tokens': 0})
    stream = ui.StreamUI(cfg, agent, time.monotonic(), tip='T')
    stream.on_stream_start()
    stream.on_delta('**你**')
    stream.on_delta(' 好 `code`')
    stream.on_stream_end('你好')
    out = capsys.readouterr().out
    assert '**' not in out and '`' not in out
    assert '好' in out
    assert 'T' in out


def test_stream_ui_tool_lines_render_live(cfg):
    import time
    from types import SimpleNamespace

    from celebrity import ui

    agent = SimpleNamespace(usage={'total_tokens': 0})
    stream = ui.StreamUI(cfg, agent, time.monotonic())
    with ui.console.capture() as cap:
        stream.on_tool_start('crawl_images')
        ui.console.print('CRAWLED 10')  # tool progress prints live
        stream.on_tool('crawl_images', True, 'saved 10')
    text = cap.get()
    assert 'CRAWLED 10' in text
    assert '◆ crawl_images' in text
    assert 'saved 10' in text
