# -*- coding: utf-8 -*-
"""Status / progress lines for the input frame."""

from types import SimpleNamespace

from celebrity import cli


def fake_agent():
    return SimpleNamespace(
        usage={'total_tokens': 1234},
        elapsed=12.5,
        turn_count=3,
        last_tool='crawl_images',
    )


def test_status_line_shows_metrics(cfg):
    line = cli._status_line(cfg, fake_agent())
    assert '模型 deepseek-v4-flash' in line
    assert 'Token 1234' in line
    assert '耗时 12.5s' in line
    assert '轮次 3' in line


def test_progress_line_shows_tool(cfg, tmp_path):
    line = cli._progress_line(cfg, fake_agent())
    assert '工具 crawl_images' in line
    assert '暂无任务' not in line


def test_progress_line_without_task(cfg):
    line = cli._progress_line(cfg, None)
    assert '暂无任务' in line
