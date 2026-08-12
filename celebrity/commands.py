# -*- coding: utf-8 -*-
"""交互式斜杠命令：运行时修改模型厂商 / API Key / Cookie / 视觉模型。

行为配置写入 config.yaml，密钥只写入 .env（绝不进 YAML 或日志）。
"""
import re
import os
from pathlib import Path

from . import config as cfgmod
from . import ui
from .security import mask_cookie, mask_secret

PRESET_PROVIDERS = ('deepseek', 'openai')
PROVIDER_LABELS = {
    'deepseek': 'DeepSeek（默认）',
    'openai': 'OpenAI 兼容（OpenAI / 通义等）',
}
ENV_KEY_ALIASES = {
    'DEEPSEEK_API_KEY': 'deepseek',
    'OPENAI_API_KEY': 'openai',
    'DASHSCOPE_API_KEY': 'vision-openai',
}
VISION_CHOICES = [
    '不配置（纯文本 Agent）',
    'YuNet 单人检测（本地轻量）',
    'OpenAI 兼容视觉（如 Qwen-VL）',
    '本地 Qwen3-VL（需 torch/transformers）',
]

ALIASES = {
    'm': 'model', '模型': 'model', '模型设置': 'model', 'provider': 'model',
    'key': 'apikey', 'api': 'apikey', 'apikey': 'apikey', '密钥': 'apikey',
    'ck': 'cookie', '登录': 'cookie', 'cookies': 'cookie',
    'vision': 'vision', '视觉': 'vision',
    's': 'status', '状态': 'status', '配置': 'status',
    'h': 'help', '?': 'help', '帮助': 'help', '命令': 'help',
}


def _quote_env(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def write_env_value(env_path, key: str, value: str):
    """Create/update a key in .env, preserving every other line."""
    env_path = Path(env_path)
    lines = env_path.read_text(encoding='utf-8').splitlines() if env_path.exists() else []
    new_lines = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and stripped.split('=', 1)[0].strip() == key:
            new_lines.append(f'{key}={_quote_env(value)}')
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        if new_lines and new_lines[-1].strip():
            new_lines.append('')
        new_lines.append(f'{key}={_quote_env(value)}')
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')


def set_api_key(cfg, profile: str, key: str):
    env_name = cfgmod.get(cfg, f'provider.{profile}.api_key_env') or f'{profile.upper()}_API_KEY'
    write_env_value(cfgmod.env_path(), env_name, key)
    os.environ[env_name] = key
    return env_name


def provider_profiles(cfg) -> list:
    names = list(PRESET_PROVIDERS)
    block = cfg.get('provider', {}) or {}
    for name in block:
        if name == 'default' or name in names or name == 'openai_compat':
            continue
        if isinstance(block[name], dict):
            names.append(name)
    return names


def _parse_pairs(text):
    """Parse KEY=VALUE pairs from pasted text (one per line)."""
    pairs = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, _, value = line.partition('=')
            pairs[key.strip().upper()] = value.strip().strip('"\'“‘”’')
    return pairs


def extract_cookie(text):
    """Extract the real cookie from pasted text.

    Handles wrapping quotes (English/Chinese), paste-wrap newlines, and mixed
    Chinese explanations: only ASCII `key=value` pairs are kept, so a paste
    like `a1=x; webId=y，这是cookie帮我加进去` still yields the real cookie.
    Returns '' when nothing usable is found.
    """
    value = (text or '').strip()
    for open_q, close_q in (('“', '”'), ('"', '"'), ("'", "'"), ('‘', '’')):
        if value.startswith(open_q) and close_q in value:
            value = value[1:value.find(close_q, 1)]
            break
    value = re.sub(r'[\r\n\u3000]+', '', value)
    pairs = []
    for segment in value.split(';'):
        segment = segment.strip()
        key, sep, val = segment.partition('=')
        if not sep:
            continue
        key = key.strip()
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', key):
            continue
        ascii_val = []
        for ch in val:
            # '?' 既不是小红书 cookie 值的合法字符，也可能是粘贴/传输时
            # 中文被替换成的占位符，一律在此截断。
            if ord(ch) > 127 or ch == '?':
                break
            ascii_val.append(ch)
        ascii_val = ''.join(ascii_val).strip()
        if not ascii_val:
            continue
        pairs.append(f'{key}={ascii_val}')
    return '; '.join(pairs)


def detect_credential(text):
    """Classify pasted text as a credential.

    Returns (kind, payload): 'env' (explicit KEY= pairs), 'cookie',
    'api_key' (bare sk-...), or (None, None) for ordinary messages.
    """
    text = (text or '').strip()
    if not text:
        return None, None
    pairs = _parse_pairs(text)
    if pairs:
        known = {
            k: v for k, v in pairs.items()
            if k in ENV_KEY_ALIASES or k.endswith('_API_KEY') or k.endswith('_COOKIE')
        }
        if known:
            return 'env', known
        if len(pairs) >= 2:
            return 'cookie', text
    if text.lower().startswith(('sk-', 'sk_')):
        return 'api_key', text
    if ';' in text and '=' in text:
        return 'cookie', text
    return None, None


def try_store_credential(text, cfg, ctx=None, env_path=None):
    """If pasted text is a credential, store it in .env locally.

    Returns (handled, message). Credentials never go to the model.
    """
    kind, payload = detect_credential(text)
    if kind is None:
        return False, ''
    env_path = env_path or cfgmod.env_path()

    if kind == 'env':
        names = []
        for key, value in payload.items():
            if key.endswith('_COOKIE'):
                value = extract_cookie(value)
                if not value or not value.isascii():
                    return True, f'{key} 包含非 ASCII 字符，无法使用；请只粘贴 cookie 本体'
            write_env_value(env_path, key, value)
            os.environ[key] = value
            if ctx is not None and ctx.redactor is not None:
                ctx.redactor.add(value)
            names.append(f'{key}（{mask_secret(value)}）')
        return True, '已保存到 .env：' + '，'.join(names)

    if kind == 'cookie':
        cookie = extract_cookie(payload)
        if not cookie:
            return True, '未提取到有效 Cookie（仅保留 ASCII 的 key=value 对）；请只粘贴 cookie 本体'
        write_env_value(env_path, 'XHS_COOKIE', cookie)
        os.environ['XHS_COOKIE'] = cookie
        if ctx is not None and ctx.redactor is not None:
            ctx.redactor.add(cookie)
        return True, f'已识别为小红书 Cookie 并保存（{mask_secret(cookie)}）'

    # bare api key: ask where to store it (never send to the model)
    current = cfgmod.get(cfg, 'provider.default', 'deepseek')
    env_name = cfgmod.get(cfg, f'provider.{current}.api_key_env') or f'{current.upper()}_API_KEY'
    choices = [
        f'保存为当前模型（{current}）的 API Key',
        '保存为其他名称',
        '忽略（不保存也不发送）',
    ]
    try:
        idx, _ = ui.ask_choice('识别到 API Key，保存到哪里？', choices, default=1, overlay=True)
    except KeyboardInterrupt:
        return True, '已取消，未保存'
    if idx == 1:
        write_env_value(env_path, env_name, payload)
        os.environ[env_name] = payload
        if ctx is not None and ctx.redactor is not None:
            ctx.redactor.add(payload)
        return True, f'已保存到 .env：{env_name}（{mask_secret(payload)}）'
    if idx == 2:
        try:
            other = ui.ask_text('其他密钥名称（如 MYVENDOR_API_KEY / XHS_COOKIE）', overlay=True)
        except KeyboardInterrupt:
            return True, '已取消，未保存'
        other = other.strip().upper().replace(' ', '_')
        if not other:
            return True, '名称为空，未保存'
        write_env_value(env_path, other, payload)
        os.environ[other] = payload
        if ctx is not None and ctx.redactor is not None:
            ctx.redactor.add(payload)
        return True, f'已保存到 .env：{other}（{mask_secret(payload)}）'
    return True, '已忽略'


def _default_index(cfg):
    current = cfgmod.get(cfg, 'provider.default', 'deepseek')
    names = provider_profiles(cfg)
    return names.index(current) + 1 if current in names else 1


def model_wizard(cfg, cfg_path):
    """切换模型厂商；返回更新后的 cfg（已保存）。"""
    names = provider_profiles(cfg)
    labels = [PROVIDER_LABELS.get(n, n) for n in names] + ['自定义新厂商']
    idx, _ = ui.ask_choice('模型厂商设置', labels, default=_default_index(cfg), overlay=True)
    if idx == len(labels):
        name = ui.ask_text('新厂商名称（英文小写，如 myvendor）', overlay=True)
        base_url = ui.ask_text('Base URL（OpenAI 兼容，如 https://api.example.com/v1）', overlay=True)
        model = ui.ask_text('模型名（如 example-chat）', overlay=True)
        key = ui.ask_text('API Key（可留空稍后设置）', default='', password=True, overlay=True)
        env_name = f'{name.upper()}_API_KEY'
        cfg['provider'][name] = {'base_url': base_url, 'model': model, 'api_key_env': env_name}
        cfg['provider']['default'] = name
        if key:
            set_api_key(cfg, name, key)
    else:
        name = names[idx - 1]
        cfg['provider']['default'] = name
        env_name = cfgmod.get(cfg, f'provider.{name}.api_key_env') or f'{name.upper()}_API_KEY'
        key = ui.ask_text(f'设置 {name} 的 API Key（直接回车保持现状）', default='', password=True, overlay=True)
        if key:
            set_api_key(cfg, name, key)
    cfgmod.save_config(cfg, cfg_path)
    ui.success(f'模型已切换为 {cfg["provider"]["default"]}，配置已保存')
    return cfg


def apikey_wizard(cfg, cfg_path):
    name = cfgmod.get(cfg, 'provider.default', 'deepseek')
    key = ui.ask_text(f'输入 {name} 的 API Key', default='', password=True, overlay=True)
    if not key:
        ui.warn('未输入，保持现状')
        return cfg
    env_name = set_api_key(cfg, name, key)
    ui.success(f'已写入 .env（{env_name}）')
    return cfg


def cookie_wizard(cfg, cfg_path):
    value = ui.ask_text('小红书 Cookie（document.cookie 的值，可留空跳过）', default='', password=True, overlay=True)
    if not value:
        ui.warn('未输入，保持现状')
        return cfg
    write_env_value(cfgmod.env_path(), 'XHS_COOKIE', value)
    os.environ['XHS_COOKIE'] = value
    ui.success('Cookie 已写入 .env（XHS_COOKIE）')
    return cfg


def vision_wizard(cfg, cfg_path):
    idx, _ = ui.ask_choice('视觉模型设置', VISION_CHOICES, default=1, overlay=True)
    vision_cfg = cfg.setdefault('vision', {})
    if idx == 1:
        vision_cfg['provider'] = ''
    elif idx == 2:
        vision_cfg['provider'] = 'yunet'
    elif idx == 3:
        vision_cfg['provider'] = 'openai'
        opts = vision_cfg.setdefault('openai', {})
        opts['base_url'] = ui.ask_text(
            '视觉 Base URL',
            default=opts.get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
            overlay=True)
        opts['model'] = ui.ask_text('视觉模型名', default=opts.get('model', 'qwen-vl-plus'), overlay=True)
        env_name = opts.get('api_key_env') or 'DASHSCOPE_API_KEY'
        opts['api_key_env'] = env_name
        key = ui.ask_text('视觉 API Key（留空保持现状）', default='', password=True, overlay=True)
        if key:
            write_env_value(cfgmod.env_path(), env_name, key)
            os.environ[env_name] = key
    else:
        vision_cfg['provider'] = 'local_vlm'
        opts = vision_cfg.setdefault('local_vlm', {})
        opts['model_dir'] = ui.ask_text(
            '模型目录', default=opts.get('model_dir', 'models/Qwen3-VL-8B-Instruct'), overlay=True)
    cfgmod.save_config(cfg, cfg_path)
    ui.success('视觉模型配置已保存')
    return cfg


def status(cfg, cfg_path):
    provider = cfgmod.get(cfg, 'provider.default', 'deepseek')
    model = cfgmod.get(cfg, f'provider.{provider}.model', '')
    env_name = cfgmod.get(cfg, f'provider.{provider}.api_key_env', '') or ''
    key_ok = bool(os.environ.get(env_name)) if env_name else False
    vision = (cfg.get('vision', {}) or {}).get('provider', '') or '未配置'
    rows = [
        ('模型厂商', provider),
        ('模型', model),
        ('API Key', '已设置' if key_ok else '未设置'),
        ('视觉模型', vision),
        ('小红书 Cookie', mask_cookie(os.environ.get('XHS_COOKIE', ''))),
        ('数据目录', cfgmod.ensure_work_dirs(cfg)['datasets_dir']),
    ]
    ui.table('当前配置', rows, headers=('项目', '值'))
    return cfg


def help_table(cfg, cfg_path):
    rows = [
        ('/model', '切换模型厂商 / 自定义厂商、设置 API Key'),
        ('/apikey', '为当前厂商设置 API Key（写 .env）'),
        ('/cookie', '设置小红书 Cookie（写 .env）'),
        ('/vision', '切换视觉模型（无 / YuNet / OpenAI 视觉 / 本地 VLM）'),
        ('/status', '查看当前配置（密钥脱敏）'),
        ('/tools', '列出可用工具'),
        ('/reset', '开启新会话'),
        ('/exit', '返回主页面'),
        ('ESC/Ctrl+C', '返回上一级；在主页面再次按下为退出确认'),
    ]
    ui.table('斜杠命令', rows, headers=('命令', '说明'))
    return cfg


_DISPATCH = {
    'model': model_wizard,
    'apikey': apikey_wizard,
    'cookie': cookie_wizard,
    'vision': vision_wizard,
    'status': status,
    'help': help_table,
}


def run_slash(line, cfg, cfg_path):
    """Handle a slash command; returns (cfg, needs_rebuild, stop)."""
    raw = line[1:].strip().lower()
    if not raw:
        return cfg, False, False
    name = raw.split()[0]
    canonical = ALIASES.get(name, name)
    handler = _DISPATCH.get(canonical)
    if handler is None:
        ui.warn(f'未知命令: /{name}，输入 /help 查看全部命令')
        return cfg, False, False
    rebuild = canonical in ('model', 'apikey', 'cookie', 'vision')
    new_cfg = handler(cfg, cfg_path)
    return new_cfg, rebuild, False
