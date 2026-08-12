# -*- coding: utf-8 -*-
"""Pipeline tool helpers: target check, model download confirmation."""

import pytest

from celebrity.tools.builtin import pipeline_tools as pt
from celebrity.vision.registry import resolve_vision
from celebrity.vision.yunet import ensure_yunet


def test_check_target_under():
    assert pt._check_target(30, 50) == {'needs_more': True, 'target': 50, 'missing': 20}


def test_check_target_met():
    assert pt._check_target(50, 50) == {'needs_more': False, 'target': 50}
    assert pt._check_target(60, 50)['needs_more'] is False


def test_check_target_zero_disabled():
    assert pt._check_target(0, 0)['needs_more'] is False


def test_ensure_yunet_decline_does_not_download(tmp_path, cfg):
    cfg['work']['models_dir'] = str(tmp_path / 'models')
    cfg['vision'] = {'provider': '', 'yunet': {'url': 'https://example.com/yunet.onnx'}}
    with pytest.raises(RuntimeError, match='取消'):
        ensure_yunet(cfg, confirm=lambda question: False)
    assert not (tmp_path / 'models' / 'face_detection_yunet_2023mar.onnx').exists()


def test_ensure_yunet_skips_when_present(tmp_path, cfg):
    models_dir = tmp_path / 'models'
    models_dir.mkdir()
    model_file = models_dir / 'face_detection_yunet_2023mar.onnx'
    model_file.write_bytes(b'fake')
    cfg['work']['models_dir'] = str(models_dir)
    assert ensure_yunet(cfg, confirm=lambda q: False) == model_file


def _fake_model_dir(tmp_path):
    model_dir = tmp_path / 'Qwen3-VL'
    model_dir.mkdir()
    (model_dir / 'config.json').write_text('{}', encoding='utf-8')
    (model_dir / 'model.safetensors').write_bytes(b'x')
    return model_dir


def test_resolve_vision_non_interactive_raises(cfg):
    with pytest.raises(RuntimeError, match='视觉模型'):
        resolve_vision(cfg)


def test_resolve_vision_local_path(tmp_path, cfg):
    model_dir = _fake_model_dir(tmp_path)
    cfg_path = tmp_path / 'cfg.yaml'
    ask_choice = lambda prompt, choices, default=1, overlay=False: (2, choices[1])
    ask_text = lambda prompt, default=None, password=False, overlay=False: str(model_dir)
    vision = resolve_vision(cfg, ask_choice=ask_choice, ask_text=ask_text, cfg_path=cfg_path)
    assert vision.name == 'local_vlm'
    assert cfg['vision']['provider'] == 'local_vlm'
    assert str(model_dir) in cfg_path.read_text(encoding='utf-8')


def test_resolve_vision_local_path_invalid(tmp_path, cfg):
    ask_choice = lambda prompt, choices, default=1, overlay=False: (2, choices[1])
    ask_text = lambda prompt, default=None, password=False, overlay=False: str(tmp_path / 'missing')
    with pytest.raises(RuntimeError, match='本地模型不可用'):
        resolve_vision(cfg, ask_choice=ask_choice, ask_text=ask_text, cfg_path=tmp_path / 'c.yaml')


def test_resolve_vision_yunet_fallback(tmp_path, cfg):
    models_dir = tmp_path / 'models'
    models_dir.mkdir()
    (models_dir / 'face_detection_yunet_2023mar.onnx').write_bytes(b'fake')
    cfg['work']['models_dir'] = str(models_dir)
    ask_choice = lambda prompt, choices, default=1, overlay=False: (3, choices[2])
    vision = resolve_vision(cfg, ask_choice=ask_choice, cfg_path=tmp_path / 'c.yaml')
    assert vision.name == 'yunet'


def test_resolve_vision_cancel(tmp_path, cfg):
    def ask_choice(prompt, choices, default=1, overlay=False):
        raise KeyboardInterrupt
    with pytest.raises(RuntimeError, match='取消'):
        resolve_vision(cfg, ask_choice=ask_choice, cfg_path=tmp_path / 'c.yaml')
