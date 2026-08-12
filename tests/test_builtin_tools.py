# -*- coding: utf-8 -*-
"""Built-in tool registration and meta tools."""

import json

from celebrity.tools.base import ToolContext
from celebrity.tools.builtin import register_builtins
from celebrity.tools.registry import ToolRegistry


def test_builtin_tools_registered(cfg, tmp_path):
    reg = ToolRegistry()
    register_builtins(reg)
    names = reg.names()
    for expected in ('about', 'list_tools', 'crawl_images', 'run_pipeline',
                     'package_dataset', 'dataset_status', 'list_work_files'):
        assert expected in names


def test_about_tool_works(cfg, tmp_path):
    reg = ToolRegistry()
    register_builtins(reg)
    ctx = ToolContext(
        cfg=cfg,
        work_dirs={'datasets_dir': str(tmp_path / 'datasets'),
                   'models_dir': str(tmp_path / 'models'),
                   'outputs_dir': str(tmp_path / 'outputs')},
        allowed_risks=('read',),
        tool_names=reg.names,
    )
    out = json.loads(reg.dispatch('about', {}, ctx))
    assert out['ok'] is True
    assert out['data']['version']


def test_pipeline_tool_risk_gate(cfg, tmp_path):
    reg = ToolRegistry()
    register_builtins(reg)
    ctx = ToolContext(cfg=cfg, work_dirs={}, allowed_risks=('read',))
    out = json.loads(reg.dispatch('crawl_images', {'celebrity': '宋雨琦'}, ctx))
    assert out['ok'] is False
    # fail-closed: availability gate (missing cookie) or risk gate denies
    assert ('未授权' in out['content']) or ('不可用' in out['content'])
