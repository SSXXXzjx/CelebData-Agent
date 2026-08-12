# -*- coding: utf-8 -*-
"""Pipeline steps: check, dedup, judge, similarity dedup, build, package."""
import csv
import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .. import ui


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def initial_check(raw_dir, min_short_side=720):
    ui.print_step(5, 8, '初步检查', f'验证图片有效性且最短边 >= {min_short_side}')
    from PIL import Image
    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.glob('*.jpg'))
    valid, invalid = [], []
    progress = ui.make_progress()
    task = progress.add_task('初步检查图片', total=len(files))
    try:
        progress.start()
        for p in files:
            try:
                with Image.open(p) as im:
                    w, h = im.size
                if min(w, h) < min_short_side:
                    invalid.append({'file': p.name, 'reason': f'最短边 {min(w, h)} < {min_short_side}'})
                else:
                    valid.append({'file': p.name, 'width': w, 'height': h})
            except Exception as exc:
                invalid.append({'file': p.name, 'reason': f'无法读取: {exc}'})
            progress.update(task, advance=1)
    finally:
        progress.stop()
    report = {'valid': valid, 'invalid': invalid}
    (raw_dir.parent / 'check_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    ui.success(f'初步检查完成：有效 {len(valid)}，无效/不达标 {len(invalid)}')
    for item in invalid[:10]:
        ui.warn(f'  {item["file"]}: {item["reason"]}')
    return report


def dedup(raw_dir, valid):
    ui.print_step(5, 8, '去重', '按内容 MD5 去重，保留每个哈希的第一张')
    raw_dir = Path(raw_dir)
    seen = {}
    removed = []
    kept = []
    for item in valid:
        p = raw_dir / item['file']
        digest = md5_of_file(p)
        if digest in seen:
            removed.append({'file': item['file'], 'duplicate_of': seen[digest]})
            p.unlink(missing_ok=True)
        else:
            seen[digest] = item['file']
            kept.append(item)
    ui.success(f'去重完成：保留 {len(kept)}，移除重复 {len(removed)}')
    return kept


def judge_images(raw_dir, vision, kept):
    """Judge each image with the vision provider (resumable via judgment.json)."""
    if vision is None:
        ui.info('未启用模型判断（vision=None），全部放行')
        results = [
            {'file': item['file'], 'ok': True, 'reason': '未启用模型判断', 'meta': {}}
            for item in kept
        ]
        (Path(raw_dir).parent / 'judgment.json').write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        return results, []
    ui.print_step(6, 8, '模型逐图判断', f'使用视觉模型: {getattr(vision, "name", "?")}')
    raw_dir = Path(raw_dir)
    judgment_path = raw_dir.parent / 'judgment.json'
    results = []
    judged_files = set()
    if judgment_path.exists():
        try:
            old = json.loads(judgment_path.read_text(encoding='utf-8'))
            for r in old:
                if (raw_dir / r['file']).exists():
                    results.append(r)
                    judged_files.add(r['file'])
            ui.info(f'发现已判断记录 {len(results)} 条，将从中断处继续')
        except Exception:
            pass

    pending = [item for item in kept if item['file'] not in judged_files]
    total = len(kept)
    progress = ui.make_progress()
    task = progress.add_task('模型逐图判断', total=len(pending))
    try:
        progress.start()
        done = 0
        for item in pending:
            verdict = vision.judge(str(raw_dir / item['file']))
            results.append({
                'file': item['file'],
                'ok': verdict.ok,
                'reason': verdict.reason,
                'meta': verdict.meta,
            })
            judged_files.add(item['file'])
            done += 1
            if done % 20 == 0 or done == len(pending):
                judgment_path.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            progress.update(task, completed=done)
    finally:
        progress.stop()
    judgment_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    accepted = [r for r in results if r['ok']]
    rejected = [r for r in results if not r['ok']]
    ui.success(f'模型判断完成：通过 {len(accepted)}，淘汰 {len(rejected)}')
    for item in rejected[:10]:
        ui.warn(f'  淘汰 {item["file"]}: {item["reason"]}')
    return accepted, rejected


def similarity_dedup_step(work_dir, accepted, cfg):
    """Similarity dedup before captioning: keep the first image of each group."""
    from .. import similarity
    quality = cfg.get('quality', {}) or {}
    if not quality.get('similarity_dedup', True):
        ui.info('相似去重已关闭（quality.similarity_dedup=false）')
        return accepted
    method = quality.get('similarity_method', 'phash')
    threshold = quality.get('similarity_threshold', None)
    model_path = quality.get('similarity_model') or ''
    ui.print_step(7, 8, '相似去重（打标签前）',
                  f'方法 {method}，阈值 {threshold if threshold is not None else ("0.92" if method == "onnx" else 8)}')
    raw_dir = Path(work_dir) / 'raw'
    paths = [str(raw_dir / item['file']) for item in accepted]
    progress = ui.make_progress()
    sim_task = progress.add_task('相似去重', total=len(paths))
    try:
        progress.start()

        def _cb(done, total):
            progress.update(sim_task, completed=done, total=total)

        keep_paths, remove_paths = similarity.dedup_similar(
            paths, method=method, threshold=threshold, model_path=model_path, progress_cb=_cb)
    except Exception as exc:
        ui.warn(f'相似去重执行失败（{exc}），跳过该步骤')
        return accepted
    finally:
        progress.stop()
    keep_files = {os.path.basename(p) for p in keep_paths}
    kept = [item for item in accepted if item['file'] in keep_files]
    removed = [item for item in accepted if item['file'] not in keep_files]
    (Path(work_dir) / 'similarity_report.json').write_text(
        json.dumps({
            'method': method,
            'threshold': float(threshold) if threshold is not None else None,
            'kept': len(kept),
            'removed': len(removed),
            'removed_files': [r['file'] for r in removed],
        }, ensure_ascii=False, indent=2), encoding='utf-8')
    ui.success(f'相似去重完成：保留 {len(kept)}，移除相似 {len(removed)}（每组只留首张）')
    for item in removed[:10]:
        ui.warn(f'  移除 {item["file"]}（与同组首张相似）')
    return kept


def build_dataset(work_dir, accepted, prefix='dataset', fields=None, vision=None,
                  caption_prompt='', caption_enabled=True):
    """Copy accepted images to final/ with labels.csv (+ optional captions)."""
    from .captions import generate_captions
    ui.print_step(7, 8, '打标签与建集', f'输出目录: {work_dir}')
    work_dir = Path(work_dir)
    raw_dir = work_dir / 'raw'
    final_dir = work_dir / 'final'
    if final_dir.exists():
        shutil.rmtree(final_dir)
    final_dir.mkdir(parents=True, exist_ok=True)

    captions = {}
    if vision is not None and caption_enabled:
        captions = generate_captions(vision, raw_dir, accepted, caption_prompt)

    labels = []
    for idx, item in enumerate(accepted, 1):
        fname = f'{prefix}_{idx:05d}.jpg'
        shutil.copyfile(raw_dir / item['file'], final_dir / fname)
        meta = item.get('meta') or {}
        caption = captions.get(item['file'], '')
        if caption:
            (final_dir / f'{fname}.txt').write_text(caption, encoding='utf-8')
        labels.append({
            'filename': fname,
            'source': item['file'],
            'verdict': item['reason'],
            'single_person': meta.get('single_person', 'yes'),
            'angle': meta.get('angle', '未知'),
            'composition': meta.get('composition', '未知'),
            'width': meta.get('width', ''),
            'height': meta.get('height', ''),
            'caption': caption,
        })
    csv_path = final_dir / 'labels.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(labels[0].keys()) if labels else (fields or []))
        writer.writeheader()
        writer.writerows(labels)
    ui.success(f'数据集构建完成：{len(labels)} 张，标签文件 labels.csv'
               + (f'（含 {len(captions)} 条 caption）' if captions else ''))
    return final_dir, labels


def trim_dataset(final_dir, labels, target):
    """Reduce dataset size: keep the first `target` images and sync labels.csv."""
    final_dir = Path(final_dir)
    images = sorted(final_dir.glob('*.jpg'))
    if len(images) <= target:
        ui.info(f'当前 {len(images)} 张 <= 目标 {target}，无需裁剪')
        return labels
    keep = set(p.name for p in images[:target])
    for p in images[target:]:
        p.unlink(missing_ok=True)
        txt = p.with_suffix(p.suffix + '.txt')
        if txt.exists():
            txt.unlink(missing_ok=True)
    kept_labels = [row for row in labels if row['filename'] in keep]
    csv_path = final_dir / 'labels.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(kept_labels[0].keys()) if kept_labels else [])
        writer.writeheader()
        writer.writerows(kept_labels)
    ui.success(f'裁剪完成：{len(images)} → {len(kept_labels)} 张，labels.csv 已同步')
    return kept_labels


def package_zip(final_dir, outputs_dir, celebrity):
    ui.print_step(8, 8, '检查与打包', '校验数据集后打包为 zip')
    final_dir = Path(final_dir)
    images = sorted(final_dir.glob('*.jpg'))
    if not images:
        raise RuntimeError('最终数据集中没有图片，无法打包')
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = ''.join(c for c in celebrity if c.isalnum() or c in '_-') or 'celebrity'
    zip_path = Path(outputs_dir) / f'{safe_name}_dataset_{ts}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in final_dir.rglob('*'):
            if p.is_file():
                zf.write(p, p.relative_to(final_dir))
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if n.endswith('.jpg')]
    ui.success(f'打包完成：{len(entries)} 张图片，{zip_path}（{(zip_path.stat().st_size / 1048576):.1f} MB）')
    return zip_path, len(entries)


def notify(celebrity, final_count, zip_path, extra=None):
    lines = [
        f'明星数据集构建完成：{celebrity}',
        f'最终图片数：{final_count}',
        f'压缩包：{zip_path}',
    ]
    if extra:
        lines.extend(extra)
    ui.notify_complete('Celebrity 完成', lines)
