# -*- coding: utf-8 -*-
"""Task session persistence (resume support)."""
import json
from pathlib import Path

from . import config as cfgmod


def save_task(work_dir, params):
    (Path(work_dir) / 'task.json').write_text(
        json.dumps(params, ensure_ascii=False, indent=2), encoding='utf-8')


def load_task(work_dir):
    p = Path(work_dir) / 'task.json'
    if not p.exists():
        raise RuntimeError(f'工作目录缺少 task.json，无法恢复: {work_dir}')
    return json.loads(p.read_text(encoding='utf-8'))


def count_state(work_dir):
    raw = Path(work_dir) / 'raw'
    final = Path(work_dir) / 'final'
    raw_count = len(list(raw.glob('*.jpg'))) if raw.is_dir() else 0
    final_count = len(list(final.glob('*.jpg'))) if final.is_dir() else 0
    return raw_count, final_count


def latest_work_dir(cfg):
    """Most recently created task directory with a task.json, if any."""
    datasets_dir = Path(cfgmod.ensure_work_dirs(cfg)['datasets_dir'])
    candidates = sorted(
        (p for p in datasets_dir.iterdir() if p.is_dir() and (p / 'task.json').exists()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None
