# -*- coding: utf-8 -*-
"""Slash-command helpers: .env writing, provider profile discovery."""

from types import SimpleNamespace

from celebrity.commands import (
    detect_credential,
    extract_cookie,
    provider_profiles,
    try_store_credential,
    write_env_value,
)
from celebrity.security import Redactor


def test_write_env_creates(tmp_path):
    env = tmp_path / '.env'
    write_env_value(env, 'DEEPSEEK_API_KEY', 'sk-abc')
    assert env.exists()
    assert 'DEEPSEEK_API_KEY="sk-abc"' in env.read_text(encoding='utf-8')


def test_write_env_preserves_other_lines(tmp_path):
    env = tmp_path / '.env'
    env.write_text('# comment\nXHS_COOKIE="a=b;c"\n', encoding='utf-8')
    write_env_value(env, 'DEEPSEEK_API_KEY', 'sk-abc')
    text = env.read_text(encoding='utf-8')
    assert '# comment' in text
    assert 'XHS_COOKIE="a=b;c"' in text
    assert 'DEEPSEEK_API_KEY="sk-abc"' in text


def test_write_env_replaces_existing(tmp_path):
    env = tmp_path / '.env'
    env.write_text('DEEPSEEK_API_KEY="old"\n', encoding='utf-8')
    write_env_value(env, 'DEEPSEEK_API_KEY', 'new')
    text = env.read_text(encoding='utf-8')
    assert text.count('DEEPSEEK_API_KEY') == 1
    assert 'DEEPSEEK_API_KEY="new"' in text


def test_write_env_quotes_special_chars(tmp_path):
    env = tmp_path / '.env'
    write_env_value(env, 'XHS_COOKIE', 'a=b;c d="x"')
    assert 'XHS_COOKIE="a=b;c d=\\"x\\""' in env.read_text(encoding='utf-8')


def test_provider_profiles_include_deepseek(cfg):
    names = provider_profiles(cfg)
    assert 'deepseek' in names


def test_detect_explicit_env_pairs():
    kind, payload = detect_credential('DEEPSEEK_API_KEY=sk-abc123\nXHS_COOKIE=a1=x')
    assert kind == 'env'
    assert payload['DEEPSEEK_API_KEY'] == 'sk-abc123'


def test_detect_cookie_like_text():
    kind, _ = detect_credential('a1=abc; web_session=xyz; xsecappid=1')
    assert kind == 'cookie'


def test_detect_bare_api_key():
    kind, payload = detect_credential('sk-abc123')
    assert kind == 'api_key'
    assert payload == 'sk-abc123'


def test_detect_ordinary_message():
    assert detect_credential('帮我构建宋雨琦的数据集') == (None, None)


def test_store_credential_writes_env_not_echoed(tmp_path, cfg):
    env = tmp_path / '.env'
    ctx = SimpleNamespace(redactor=Redactor())
    handled, message = try_store_credential(
        'DEEPSEEK_API_KEY=sk-abc123', cfg, ctx, env_path=env)
    assert handled
    assert 'DEEPSEEK_API_KEY' in message
    assert 'sk-abc123' not in message  # secret never echoed raw
    assert 'sk-abc123' in env.read_text(encoding='utf-8')  # stored locally


def test_store_cookie(tmp_path, cfg):
    env = tmp_path / '.env'
    handled, _ = try_store_credential(
        'a1=abc; web_session=xyz; xsecappid=1', cfg, SimpleNamespace(redactor=Redactor()),
        env_path=env)
    assert handled
    assert 'XHS_COOKIE' in env.read_text(encoding='utf-8')


def test_extract_cookie_strips_quotes_and_explanation():
    text = '“abRequestId=abc; a1=123” 双引号里面就是cookie，直接配置进去'
    assert extract_cookie(text) == 'abRequestId=abc; a1=123'


def test_extract_cookie_with_chinese_appended():
    text = 'abRequestId=abc; a1=123，这个是cookie帮我加进去'
    assert extract_cookie(text) == 'abRequestId=abc; a1=123'


def test_extract_cookie_keeps_ascii_special_values():
    text = 'unread={%22ub%22:1}; id_token=VjEAA+Ooa8i/i8g0z; loadts=1786525178482，中文'
    assert extract_cookie(text) == 'unread={%22ub%22:1}; id_token=VjEAA+Ooa8i/i8g0z; loadts=1786525178482'


def test_extract_cookie_drops_invalid_segments():
    assert extract_cookie('garbage text; a1=123; 中文说明') == 'a1=123'


def test_extract_cookie_stops_at_question_marks():
    assert extract_cookie('loadts=1786525178482????cookie???????') == 'loadts=1786525178482'


def test_store_wrapped_cookie_with_explanation(tmp_path, cfg):
    env = tmp_path / '.env'
    handled, message = try_store_credential(
        '“abRequestId=abc; a1=123” 双引号里面就是cookie',
        cfg, SimpleNamespace(redactor=Redactor()), env_path=env)
    assert handled
    stored = env.read_text(encoding='utf-8')
    assert 'abRequestId=abc; a1=123' in stored
    assert '双引号' not in stored
    assert '非 ASCII' not in message


def test_store_cookie_with_chinese_appended(tmp_path, cfg):
    env = tmp_path / '.env'
    handled, message = try_store_credential(
        'abRequestId=abc; a1=123，这个是cookie帮我加进去',
        cfg, SimpleNamespace(redactor=Redactor()), env_path=env)
    assert handled
    stored = env.read_text(encoding='utf-8')
    assert 'abRequestId=abc; a1=123' in stored
    assert '这个是cookie' not in stored


def test_store_cookie_strips_chinese_keeps_ascii_pairs(tmp_path, cfg):
    env = tmp_path / '.env'
    handled, _message = try_store_credential(
        '“abc=1; def=2中文” 解释', cfg, SimpleNamespace(redactor=Redactor()), env_path=env)
    assert handled
    stored = env.read_text(encoding='utf-8')
    assert 'abc=1; def=2' in stored
    assert '中文' not in stored
