# -*- coding: utf-8 -*-
"""Config precedence and work-dir creation."""

from pathlib import Path

from celebrity import config as cfgmod


def test_defaults_merged(tmp_path):
    cfg = cfgmod.load_config(tmp_path / 'missing.yaml')
    assert cfg['provider']['deepseek']['model'] == 'deepseek-v4-flash'
    assert cfg['agent']['max_turns'] == 12


def test_yaml_override_merges(tmp_path):
    path = tmp_path / 'custom.yaml'
    path.write_text("agent:\n  max_turns: 3\n", encoding='utf-8')
    cfg = cfgmod.load_config(path)
    assert cfg['agent']['max_turns'] == 3
    assert cfg['provider']['deepseek']['model'] == 'deepseek-v4-flash'


def test_api_key_reads_env(cfg, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-test-123')
    assert cfgmod.api_key(cfg, 'deepseek') == 'sk-test-123'


def test_ensure_work_dirs_creates(tmp_path):
    cfg = {
        'work': {
            'datasets_dir': str(tmp_path / 'a'),
            'models_dir': str(tmp_path / 'b'),
            'outputs_dir': str(tmp_path / 'c'),
        }
    }
    dirs = cfgmod.ensure_work_dirs(cfg)
    for key, path in dirs.items():
        assert Path(path).is_dir()


def test_get_dotted(cfg):
    assert cfgmod.get(cfg, 'provider.deepseek.model') == 'deepseek-v4-flash'
    assert cfgmod.get(cfg, 'missing.key', 'fallback') == 'fallback'
