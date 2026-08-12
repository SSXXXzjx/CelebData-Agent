# -*- coding: utf-8 -*-
"""Caption generation via the vision provider (batch-capable)."""
from pathlib import Path

from .. import ui


DEFAULT_CAPTION_PROMPT = """You are an AI assistant that generates detailed, structured, and accurate image captions for training AI image generation models.
Your task is to describe the given image, which features a single Asian female as the main subject.
The caption should be optimized for text-to-image model training (like Stable Diffusion).

**Critical Rules:**
- **DO NOT** use any personal names, titles, or any information that could identify a specific individual.
- Refer to the person generally as "a woman", "the female subject", or "the main subject".
- **DO** provide a thorough and objective description of her visual appearance, especially facial features.

Your description must be a cohesive paragraph (using comma-separated phrases) covering:
1. Subject & demographics (never a proper name).
2. Shooting angle & perspective (front-facing, three-quarter profile, high-angle, low-angle...).
3. Composition & framing (extreme close-up, close-up, medium shot, full-length...).
4. Facial features & expression (essential, objective detail).
5. Hair & makeup.
6. Pose & body language.
7. Attire & style.
8. Scene & environment.
9. Overall lighting & atmosphere.

Aim for a descriptive, specific, objective caption without revealing identity."""


def generate_captions(vision, raw_dir, accepted, prompt, caption_enabled=True):
    """Generate captions for accepted images; batch when the provider supports it."""
    if vision is None:
        ui.info('未配置视觉模型，跳过 caption 生成')
        return {}
    try:
        ok, reason = vision.check()
    except Exception:
        ok, reason = False, 'check 异常'
    if not ok:
        ui.warn(f'视觉模型不可用，跳过 caption 生成：{reason}')
        return {}
    if not caption_enabled:
        ui.info('caption 生成已关闭（label.caption_enabled=false）')
        return {}

    batch_size = int(getattr(vision, 'caption_batch_size', 1) or 1)
    use_batch = batch_size > 1 and hasattr(vision, 'caption_batch')
    ui.info(f'正在用视觉模型生成逐图描述（batch_size={batch_size}）...' if use_batch
            else '正在用视觉模型生成逐图描述...')

    captions = {}
    total = len(accepted)
    progress = ui.make_progress()
    task = progress.add_task('生成逐图描述', total=total)
    try:
        progress.start()
        if use_batch:
            for start in range(0, total, batch_size):
                chunk = accepted[start:start + batch_size]
                paths = [str(Path(raw_dir) / item['file']) for item in chunk]
                try:
                    batch_result = vision.caption_batch(paths, prompt, batch_size=batch_size)
                except Exception as exc:
                    ui.warn(f'批量 caption 失败（{exc}），该批改为逐张生成')
                    batch_result = {}
                for item in chunk:
                    cap = batch_result.get(str(Path(raw_dir) / item['file']), '')
                    if not cap:
                        try:
                            cap = vision.caption(str(Path(raw_dir) / item['file']), prompt)
                        except Exception as exc:
                            ui.warn(f'  caption 失败 {item["file"]}: {exc}')
                    captions[item['file']] = cap
                progress.update(task, completed=min(start + len(chunk), total))
        else:
            for idx, item in enumerate(accepted, 1):
                try:
                    captions[item['file']] = vision.caption(
                        str(Path(raw_dir) / item['file']), prompt)
                except Exception as exc:
                    ui.warn(f'  caption 失败 {item["file"]}: {exc}')
                    captions[item['file']] = ''
                progress.update(task, completed=idx)
    finally:
        progress.stop()
    return captions
