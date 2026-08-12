# -*- coding: utf-8 -*-
"""Agent loop: tool-call dispatch, error recovery, turn bound."""

from celebrity.core.agent import Agent
from celebrity.providers.base import ChatResult, ToolCall
from celebrity.tools.base import ToolContext, ToolSpec
from celebrity.tools.registry import ToolRegistry


class ScriptedProvider:
    """Returns scripted results in order; used as a fake provider seam."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        result = self.results.pop(0)
        self.calls += 1
        return result


def make_agent(cfg, provider):
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name='add',
        description='add two numbers',
        parameters={
            'type': 'object',
            'properties': {'a': {'type': 'number'}, 'b': {'type': 'number'}},
            'required': ['a', 'b'],
        },
        handler=lambda ctx, a, b: {'sum': a + b},
        risk='read',
    ))
    ctx = ToolContext(cfg=cfg, work_dirs={}, allowed_risks=('read',))
    return Agent(cfg, provider, reg, ctx, system_prompt='test system')


def test_tool_call_then_final(cfg):
    provider = ScriptedProvider([
        ChatResult(
            tool_calls=[ToolCall(id='t1', name='add', arguments={'a': 1, 'b': 2})],
            usage={'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        ),
        ChatResult(
            content='结果是 3',
            usage={'prompt_tokens': 20, 'completion_tokens': 7, 'total_tokens': 27},
        ),
    ])
    agent = make_agent(cfg, provider)
    result = agent.run('计算 1+2')
    assert result.content == '结果是 3'
    assert result.tool_calls == 1
    assert result.turns == 2
    assert agent.usage['total_tokens'] == 42
    assert agent.usage['prompt_tokens'] == 30
    assert agent.turn_count == 2
    assert agent.last_tool == 'add'
    assert agent.elapsed >= 0
    roles = [m['role'] for m in agent.messages]
    assert roles == ['system', 'user', 'assistant', 'tool', 'assistant']


def test_tool_failure_continues_loop(cfg):
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name='bad',
        description='fails',
        parameters={'type': 'object', 'properties': {}},
        handler=lambda ctx: (_ for _ in ()).throw(ValueError('boom')),
        risk='read',
    ))
    provider = ScriptedProvider([
        ChatResult(tool_calls=[ToolCall(id='t1', name='bad', arguments={})]),
        ChatResult(content='已处理失败'),
    ])
    ctx = ToolContext(cfg=cfg, work_dirs={}, allowed_risks=('read',))
    agent = Agent(cfg, provider, reg, ctx, system_prompt='s')
    result = agent.run('触发失败')
    assert result.content == '已处理失败'
    tool_msgs = [m for m in agent.messages if m['role'] == 'tool']
    assert 'boom' in tool_msgs[0]['content']


def test_max_turns_bounded(cfg):
    provider = ScriptedProvider([
        ChatResult(tool_calls=[ToolCall(id=f't{i}', name='add', arguments={'a': 1, 'b': 2})])
        for i in range(20)
    ])
    agent = make_agent(cfg, provider)
    result = agent.run('一直调用工具')
    assert '最大工具轮次' in result.content
    assert result.turns == cfg['agent']['max_turns']


def test_system_prompt_stable_across_reset(cfg):
    provider = ScriptedProvider([ChatResult(content='ok')])
    agent = make_agent(cfg, provider)
    agent.run('第一次')
    agent.reset()
    provider.results.append(ChatResult(content='again'))
    agent.run('第二次')
    system_msgs = [m for m in agent.messages if m['role'] == 'system']
    assert len(system_msgs) == 1


class RecordingHooks:
    def __init__(self):
        self.starts = 0
        self.deltas = []
        self.ends = []
        self.tool_starts = []
        self.tools = []

    def on_stream_start(self):
        self.starts += 1

    def on_delta(self, delta):
        self.deltas.append(delta)

    def on_stream_end(self, content):
        self.ends.append(content)

    def on_tool_start(self, name):
        self.tool_starts.append(name)

    def on_tool(self, name, ok, summary):
        self.tools.append((name, ok, summary))


class ScriptedStreamProvider:
    def __init__(self, streams):
        self.streams = list(streams)

    def chat_stream(self, messages, tools=None, temperature=None, max_tokens=None):
        for event in self.streams.pop(0):
            yield event


def test_streaming_text_deltas(cfg):
    provider = ScriptedStreamProvider([[
        {'type': 'text', 'delta': '你'},
        {'type': 'text', 'delta': '好'},
        {'type': 'done', 'result': ChatResult(content='你好', usage={'total_tokens': 5})},
    ]])
    agent = make_agent(cfg, provider)
    hooks = RecordingHooks()
    result = agent.run('打招呼', hooks=hooks)
    assert result.content == '你好'
    assert hooks.deltas == ['你', '好']
    assert hooks.ends == ['你好']
    assert hooks.starts == 1
    assert agent.usage['total_tokens'] == 5


def test_streaming_tool_then_final(cfg):
    provider = ScriptedStreamProvider([
        [{'type': 'done', 'result': ChatResult(
            tool_calls=[ToolCall(id='t1', name='add', arguments={'a': 1, 'b': 2})])}],
        [
            {'type': 'text', 'delta': '结果'},
            {'type': 'done', 'result': ChatResult(content='结果 3')},
        ],
    ])
    agent = make_agent(cfg, provider)
    hooks = RecordingHooks()
    result = agent.run('计算', hooks=hooks)
    assert result.content == '结果 3'
    assert hooks.tool_starts == ['add']
    assert hooks.tools == [('add', True, "{\"sum\": 3}")]
    assert hooks.ends == ['', '结果 3']
