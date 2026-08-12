# -*- coding: utf-8 -*-
"""Deterministic pipeline runner (steps 5-8) and work-directory helpers."""
import time
from pathlib import Path

from .. import config as cfgmod
from .. import ui
from . import steps


def run_pipeline(work_dir, cfg, vision, celebrity='celebrity', caption_prompt=''):
    """Run steps 5-8 over an existing work directory with raw/ images."""
    quality = cfg.get('quality', {}) or {}
    min_side = int(quality.get('min_short_side', 720))
    prefix = cfg.get('label', {}).get('filename_prefix', 'dataset')
    fields = cfg.get('label', {}).get('fields')
    caption_enabled = bool(cfg.get('label', {}).get('caption_enabled', True))
    prompt = caption_prompt or steps_default_caption_prompt()

    work_dir = Path(work_dir)
    raw_dir = work_dir / 'raw'
    if not raw_dir.is_dir():
        raise RuntimeError(f'缺少爬取目录: {raw_dir}')

    report = steps.initial_check(raw_dir, min_side)
    if not report['valid']:
        ui.error('没有合格图片，流水线终止')
        return None, None, []
    kept = steps.dedup(raw_dir, report['valid'])
    accepted, rejected = steps.judge_images(raw_dir, vision, kept)
    if not accepted:
        ui.error('模型判断后没有通过图片，流水线终止')
        return None, None, []
    accepted = steps.similarity_dedup_step(work_dir, accepted, cfg)
    if not accepted:
        ui.error('相似去重后没有图片，流水线终止')
        return None, None, []
    final_dir, labels = steps.build_dataset(
        work_dir, accepted, prefix, fields, vision,
        caption_prompt=prompt, caption_enabled=caption_enabled)
    outputs_dir = cfgmod.ensure_work_dirs(cfg)['outputs_dir']
    zip_path, entry_count = steps.package_zip(final_dir, outputs_dir, celebrity)
    steps.notify(celebrity, len(labels), zip_path)
    return final_dir, zip_path, labels


def steps_default_caption_prompt():
    from .captions import DEFAULT_CAPTION_PROMPT
    return DEFAULT_CAPTION_PROMPT


def create_work_dir(cfg, celebrity):
    """Create a timestamped task directory and persist task.json params."""
    from .. import sessions
    datasets_dir = Path(cfgmod.ensure_work_dirs(cfg)['datasets_dir'])
    safe_name = ''.join(c for c in celebrity if c.isalnum() or c in '_-') or 'celebrity'
    work_dir = datasets_dir / f'{safe_name}_{time.strftime("%Y%m%d_%H%M%S")}'
    work_dir.mkdir(parents=True, exist_ok=True)
    params = {
        'celebrity': celebrity,
        'work_dir': str(work_dir),
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    sessions.save_task(work_dir, params)
    return work_dir, params
