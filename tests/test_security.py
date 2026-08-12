# -*- coding: utf-8 -*-
"""Secret redaction and path containment."""

import pytest

from celebrity.security import Redactor, ensure_within, mask_cookie


def test_redactor_masks_secrets():
    r = Redactor(['sk-secret-123', 'cookie-value-abc'])
    text = r.redact('token=sk-secret-123 and cookie=cookie-value-abc')
    assert 'sk-secret-123' not in text
    assert 'cookie-value-abc' not in text
    assert text.count('***') == 2


def test_redactor_ignores_short_secrets():
    r = Redactor(['ab'])
    assert r.redact('value ab here') == 'value ab here'


def test_ensure_within_allows_inside(tmp_path):
    target = tmp_path / 'sub' / 'file.jpg'
    target.parent.mkdir()
    target.write_bytes(b'x')
    resolved = ensure_within(tmp_path, 'sub/file.jpg')
    assert resolved == target.resolve()


def test_ensure_within_rejects_escape(tmp_path):
    outside = tmp_path.parent / 'secret.txt'
    with pytest.raises(PermissionError):
        ensure_within(tmp_path, outside)
    with pytest.raises(PermissionError):
        ensure_within(tmp_path, '../outside')


def test_mask_cookie_hides_value():
    assert 'visible' not in mask_cookie('visible-secret-value')
