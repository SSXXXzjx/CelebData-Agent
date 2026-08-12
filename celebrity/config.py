# -*- coding: utf-8 -*-
"""Configuration loading.

Behavior and non-secret defaults live in config.yaml; secrets (API keys,
cookies) live in .env. Load .env before reading any key.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / 'config.yaml'
EXAMPLE_PATH = ROOT / 'config.example.yaml'
ENV_PATH = ROOT / '.env'

DEFAULTS = {
    'agent': {
        'system_prompt': '',
        'max_turns': 12,
        'temperature': 0.3,
        'timeout_seconds': 120,
        'retries': 3,
        'allow_risk': ['read', 'write', 'destructive'],
    },
    'provider': {
        'default': 'deepseek',
        'deepseek': {
            'base_url': 'https://api.deepseek.com',
            'model': 'deepseek-v4-flash',
            'api_key_env': 'DEEPSEEK_API_KEY',
        },
    },
    'vision': {
        'provider': '',
        'yunet': {
            'url': 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
        },
        'openai': {
            'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'model': 'qwen-vl-plus',
            'api_key_env': 'DASHSCOPE_API_KEY',
            'max_image_mb': 20,
        },
        'local_vlm': {
            'model_dir': 'models/Qwen3-VL-8B-Instruct',
            'repo': 'Qwen/Qwen3-VL-8B-Instruct',
            'attn_implementation': '',
            'caption_batch_size': 2,
            'caption_max_new_tokens': 512,
            'judge_max_new_tokens': 160,
        },
    },
    'work': {
        'datasets_dir': 'datasets',
        'models_dir': 'models',
        'outputs_dir': 'outputs',
    },
    'spider_xhs': {
        'dir': 'third_party/Spider_XHS',
        'repo': 'https://github.com/cv-cat/Spider_XHS.git',
    },
    'crawl': {
        'keywords': ['写真', '单人照', '自拍', '生活照', '高清写真', '画报', '杂志', '日常', '随拍', '美图'],
        'sort_types': [0, 2],
        'notes_per_query': 40,
        'api_sleep': 1.2,
        'download_sleep': 0.5,
    },
    'quality': {
        'min_short_side': 720,
        'target_count': 500,
        'dedup_by_hash': True,
        'similarity_dedup': True,
        'similarity_method': 'phash',
        'similarity_threshold': 8,
        'similarity_model': '',
    },
    'label': {
        'filename_prefix': 'dataset',
        'caption_enabled': True,
    },
}


def _deep_merge(base, override):
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_env(path=None):
    """Load .env once; returns the env file path used, if any."""
    target = Path(path) if path else env_path()
    if target.is_file():
        load_dotenv(target, override=False)
        return target
    return None


def env_path():
    """Resolve the active .env path (CELEBRITY_ENV_FILE overrides default)."""
    override = os.environ.get('CELEBRITY_ENV_FILE', '')
    return Path(override) if override else ENV_PATH


def load_config(path=None):
    """Load config.yaml merged over DEFAULTS. Missing file is not an error."""
    path = Path(path) if path else CONFIG_PATH
    cfg = json_clone(DEFAULTS)
    if path.is_file():
        try:
            import yaml
            cfg = _deep_merge(cfg, yaml.safe_load(path.read_text(encoding='utf-8')) or {})
        except Exception as exc:
            raise RuntimeError(f'读取配置失败 {path}: {exc}')
    elif EXAMPLE_PATH.is_file():
        try:
            import yaml
            cfg = _deep_merge(cfg, yaml.safe_load(EXAMPLE_PATH.read_text(encoding='utf-8')) or {})
        except Exception:
            pass
    return cfg


def json_clone(obj):
    import copy
    return copy.deepcopy(obj)


def save_config(cfg, path=None):
    import yaml
    path = Path(path) if path else CONFIG_PATH
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                    encoding='utf-8')


def ensure_work_dirs(cfg):
    """Create and return absolute work directories under the project root."""
    dirs = {}
    for key in ('datasets_dir', 'models_dir', 'outputs_dir'):
        rel = cfg.get('work', {}).get(key, key)
        p = Path(rel)
        if not p.is_absolute():
            p = ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        dirs[key] = p
    return dirs


def get(cfg, dotted, default=None):
    """Dot-path lookup, e.g. get(cfg, 'provider.deepseek.model')."""
    node = cfg
    for part in dotted.split('.'):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def provider_cfg(cfg, name=None):
    name = name or get(cfg, 'provider.default', 'deepseek')
    return get(cfg, f'provider.{name}', {}) or {}


def api_key(cfg, provider_name=None, vision=False):
    """Read the provider's API key from the environment (never from YAML)."""
    section = 'vision.openai' if vision else f'provider.{provider_name or get(cfg, "provider.default", "deepseek")}'
    env_name = get(cfg, section + '.api_key_env') or ''
    return os.environ.get(env_name, '') if env_name else ''


def redaction_secrets(cfg):
    """Collect secret values (from env) for redaction in any output."""
    secrets = set()
    for section in ('provider', 'vision.openai'):
        env_name = get(cfg, section + '.api_key_env') or ''
        if env_name:
            value = os.environ.get(env_name, '')
            if value:
                secrets.add(value)
    cookie = os.environ.get('XHS_COOKIE', '')
    if cookie:
        secrets.add(cookie)
    return sorted(secrets, key=len, reverse=True)
