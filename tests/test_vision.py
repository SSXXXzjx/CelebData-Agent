# -*- coding: utf-8 -*-
"""Vision helpers: JSON parsing, YuNet failure path, size bound."""

import pytest

from celebrity.vision.base import parse_json_answer


def test_parse_json_answer_strips_fences():
    answer = '```json\n{"is_target": true, "angle": "正面"}\n```'
    parsed = parse_json_answer(answer)
    assert parsed['is_target'] is True
    assert parsed['angle'] == '正面'


def test_parse_json_answer_empty():
    assert parse_json_answer('没有 json') == {}


def test_yunet_rejects_blank_image(tmp_path, cfg):
    cv2 = pytest.importorskip('cv2')
    from PIL import Image
    from celebrity.vision.yunet import YunetVision

    path = tmp_path / 'blank.jpg'
    Image.new('RGB', (800, 600), (200, 200, 200)).save(path, 'JPEG')
    vision = YunetVision(cfg)
    ok, _ = vision.check()
    if not ok:
        pytest.skip('YuNet 模型文件缺失')
    verdict = vision.judge(str(path))
    assert verdict.ok is False
    assert '人脸' in verdict.reason


def test_yunet_reads_unicode_path(tmp_path, cfg):
    """cv2.imread cannot open Windows Unicode paths; PIL-first must work."""
    pytest.importorskip('cv2')
    from PIL import Image
    from celebrity.vision.yunet import YunetVision

    raw = tmp_path / '宋雨琦_测试' / 'raw'
    raw.mkdir(parents=True)
    path = raw / 'cand_00001.jpg'
    Image.new('RGB', (800, 800), (120, 80, 40)).save(path, 'JPEG')

    vision = YunetVision(cfg)
    vision._detect = lambda img: None  # bypass model file for this test
    verdict = vision.judge(str(path))
    assert verdict.reason != '图片无法读取'
    assert '人脸' in verdict.reason


def test_openai_vision_rejects_oversized_image(tmp_path, cfg):
    from PIL import Image
    from celebrity.vision.openai_vision import OpenAICompatVision

    path = tmp_path / 'big.jpg'
    Image.new('RGB', (2000, 2000), (10, 20, 30)).save(path, 'JPEG', quality=95)
    vision_cfg = dict(cfg)
    vision_cfg['vision'] = {'provider': 'openai', 'openai': {
        'base_url': 'http://x/v1', 'model': 'qwen-vl-plus',
        'api_key_env': 'DASHSCOPE_API_KEY', 'max_image_mb': 0,
    }}
    vision = OpenAICompatVision(vision_cfg)
    with pytest.raises(ValueError):
        vision._data_url(str(path))
