# -*- coding: utf-8 -*-
"""Crawl query composition (no network)."""

from celebrity.crawler import _next_cand_no, build_queries, normalize_image


def test_build_queries_composition():
    queries = build_queries('宋雨琦', ['YUQI'], keywords=['写真', '自拍'], sort_types=[0, 2])
    names = [q for q, _ in queries]
    assert ('宋雨琦 写真', 0) in queries
    assert ('宋雨琦 自拍', 2) in queries
    assert ('YUQI 写真', 0) in queries
    assert not any(q == '宋雨琦' for q, _ in queries)


def test_next_cand_no_skips_existing(tmp_path):
    raw = tmp_path / 'raw'
    raw.mkdir()
    for name in ('cand_00003.jpg', 'cand_00007.jpg', 'junk.txt'):
        (raw / name).write_bytes(b'x')
    assert _next_cand_no(raw) == 7
    assert _next_cand_no(tmp_path / 'empty') == 0


def test_normalize_image_rejects_non_image(tmp_path):
    p = tmp_path / 'bad.jpg'
    p.write_bytes(b'<html>error page</html>')
    assert normalize_image(p) is False


def test_normalize_image_converts_webp_to_jpeg(tmp_path):
    from PIL import Image
    p = tmp_path / 'pic.jpg'
    Image.new('RGB', (32, 32), (1, 2, 3)).save(p, 'WEBP')
    assert normalize_image(p) is True
    with Image.open(p) as im:
        assert im.format == 'JPEG'
