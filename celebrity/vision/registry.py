# -*- coding: utf-8 -*-
"""Vision provider selection from config."""
from pathlib import Path
from typing import Optional

from .. import config as cfgmod
from .base import VisionProvider


class VisionError(Exception):
    pass


def create_vision(cfg: dict) -> Optional[VisionProvider]:
    """Build the configured vision provider (construction is lazy/cheap)."""
    name = (cfg.get('vision') or {}).get('provider') or ''
    name = name.strip().lower()
    if not name:
        return None
    if name == 'yunet':
        from .yunet import YunetVision
        return YunetVision(cfg)
    if name == 'openai':
        from .openai_vision import OpenAICompatVision
        return OpenAICompatVision(cfg)
    if name == 'local_vlm':
        from .local_vlm import LocalVLMVision
        return LocalVLMVision(cfg)
    raise VisionError(f'未知视觉 provider: {name}（可选 yunet / openai / local_vlm）')


def describe(provider: Optional[VisionProvider]) -> str:
    if provider is None:
        return '未配置（vision.provider 为空）'
    ok, reason = provider.check()
    return reason if ok else f'不可用: {reason}'


def resolve_vision(cfg, confirm=None, ask_choice=None, ask_text=None, cfg_path=None):
    """Resolve a usable vision provider at judging time.

    When Qwen-VL is configured but incomplete (or nothing is configured), the
    user is asked to download Qwen3-VL, provide a local model path, fall back
    to YuNet, or cancel. `ask_choice` / `ask_text` are UI callbacks; when they
    are None (non-interactive), a structured error is raised instead.
    """
    from .. import config as cfgmod
    from .local_vlm import LocalVLMVision, ensure_vlm, _vlm_ready
    from .yunet import YunetVision, ensure_yunet

    vision = create_vision(cfg)
    if vision is not None and vision.check()[0]:
        return vision
    if vision is not None and getattr(vision, 'name', '') == 'yunet':
        ensure_yunet(cfg, confirm=confirm)
        return vision

    name = getattr(vision, 'name', '') if vision is not None else ''
    if ask_choice is None:
        if name == 'local_vlm':
            raise RuntimeError(
                '模型判断需要 Qwen3-VL，但模型不完整。请在交互对话中运行，'
                '选择下载模型或提供本地模型路径；或在 config.yaml 配置 vision.local_vlm.model_dir。')
        raise RuntimeError(
            '模型判断需要视觉模型（默认 Qwen3-VL）。请在交互对话中运行以选择下载/本地路径，'
            '或配置 vision.provider（local_vlm / yunet / openai）。')

    choices = [
        '下载 Qwen3-VL-8B（约 16GB，来自 ModelScope）',
        '提供本地已下载的模型路径',
        '使用轻量 YuNet（无需下载）',
        '取消',
    ]
    try:
        idx, _ = ask_choice('模型逐图判断需要视觉模型，请选择', choices, default=1, overlay=True)
    except KeyboardInterrupt:
        raise RuntimeError('用户取消模型选择') from None

    if idx == 1:
        cfg.setdefault('vision', {})['provider'] = 'local_vlm'
        ensure_vlm(cfg, confirm=None)  # user already confirmed by choosing download
        cfgmod.save_config(cfg, cfg_path or cfgmod.CONFIG_PATH)
        return LocalVLMVision(cfg)

    if idx == 2:
        raw = ask_text('本地 Qwen3-VL 模型目录路径', overlay=True)
        model_dir = Path(raw.strip())
        if not model_dir.is_absolute():
            model_dir = cfgmod.ROOT / model_dir
        if not _vlm_ready(model_dir):
            raise RuntimeError(
                f'本地模型不可用：{model_dir}（需要 config.json 与 .safetensors 权重文件）')
        vision_cfg = cfg.setdefault('vision', {})
        vision_cfg['provider'] = 'local_vlm'
        vision_cfg.setdefault('local_vlm', {})['model_dir'] = str(model_dir)
        cfgmod.save_config(cfg, cfg_path or cfgmod.CONFIG_PATH)
        return LocalVLMVision(cfg)

    if idx == 3:
        ensure_yunet(cfg, confirm=confirm)
        return YunetVision(cfg)

    raise RuntimeError('已取消模型判断')
