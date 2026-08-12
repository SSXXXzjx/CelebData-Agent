# -*- coding: utf-8 -*-
"""Dataset pipeline tools callable by the agent."""
import importlib.util
import shutil
from pathlib import Path

from ... import config as cfgmod
from ... import deploy, sessions
from ... import security
from ...tools.base import ToolResult, ToolSpec


def _resolve_work_dir(ctx, work_dir=''):
    datasets_dir = Path(ctx.work_dirs['datasets_dir'])
    if work_dir:
        return security.ensure_within(datasets_dir, work_dir)
    latest = sessions.latest_work_dir(ctx.cfg)
    if latest is None:
        raise RuntimeError('还没有任务目录，请先调用 crawl_images')
    return latest


def _vision_or_yunet(ctx):
    from ... import ui
    from ...vision.registry import resolve_vision

    return resolve_vision(
        ctx.cfg,
        confirm=ctx.confirm,
        ask_choice=ui.ask_choice,
        ask_text=ui.ask_text,
    )


def _check_target(final_count, target):
    """Whether the accepted image count meets the user's target."""
    target = int(target or 0)
    if target > 0 and final_count < target:
        return {'needs_more': True, 'target': target, 'missing': target - final_count}
    return {'needs_more': False, 'target': target}


def register(registry):
    registry.register(ToolSpec(
        name='crawl_images',
        description='用 Spider_XHS 爬取某明星的候选图片到任务目录（需要 .env 中 XHS_COOKIE）',
        parameters={
            'type': 'object',
            'properties': {
                'celebrity': {'type': 'string', 'description': '明星名称，如 宋雨琦'},
                'aliases': {'type': 'string', 'description': '逗号分隔的别名/搜索词（可空）'},
                'count': {'type': 'integer', 'description': '爬取目标数量，默认 quality.target_count'},
                'work_dir': {'type': 'string', 'description': '任务目录名或路径（留空自动新建）'},
            },
            'required': ['celebrity'],
        },
        handler=_crawl_images,
        check_fn=_check_crawl,
        risk='write',
        category='pipeline',
    ))
    registry.register(ToolSpec(
        name='run_pipeline',
        description='对任务目录执行完整流水线：检查/去重 → 模型判断 → 相似去重 → 打标签 → 打包 zip',
        parameters={
            'type': 'object',
            'properties': {
                'work_dir': {'type': 'string', 'description': '任务目录名或路径（留空用最近任务）'},
                'celebrity': {'type': 'string', 'description': '明星名称（用于 zip 文件名）'},
                'caption_prompt': {'type': 'string', 'description': '自定义 caption 提示词（可空）'},
                'target_count': {'type': 'integer', 'description': '目标图片数；不足时工具会提示继续爬取（默认 quality.target_count）'},
            },
        },
        handler=_run_pipeline,
        check_fn=_check_pipeline,
        risk='write',
        category='pipeline',
    ))
    registry.register(ToolSpec(
        name='package_dataset',
        description='把 final/ 数据集打包为 zip 到 outputs/',
        parameters={
            'type': 'object',
            'properties': {
                'work_dir': {'type': 'string', 'description': '任务目录名或路径（留空用最近任务）'},
                'celebrity': {'type': 'string', 'description': '明星名称（用于 zip 文件名）'},
            },
        },
        handler=_package_dataset,
        risk='write',
        category='pipeline',
    ))
    registry.register(ToolSpec(
        name='dataset_status',
        description='查看任务目录的当前状态（raw/final 数量、已完成的阶段）',
        parameters={
            'type': 'object',
            'properties': {
                'work_dir': {'type': 'string', 'description': '任务目录名或路径（留空用最近任务）'},
            },
        },
        handler=_dataset_status,
        risk='read',
        category='pipeline',
    ))
    registry.register(ToolSpec(
        name='deploy_spider',
        description='部署/检查 Spider_XHS 爬虫（clone、依赖检查、启动冒烟测试）',
        parameters={'type': 'object', 'properties': {}},
        handler=_deploy_spider,
        risk='write',
        category='pipeline',
    ))


def _check_crawl(ctx):
    if not deploy.spider_dir(ctx.cfg).is_dir():
        return False, 'Spider_XHS 未部署（请先运行 celebrity deploy）'
    if not shutil.which('node'):
        return False, '缺少 Node.js 20+'
    if not ctx.env.get('XHS_COOKIE'):
        return False, '缺少 XHS_COOKIE（请在 .env 中设置小红书 Cookie）'
    return True, 'ok'


def _check_pipeline(ctx):
    for mod in ('PIL', 'numpy', 'imagehash'):
        if importlib.util.find_spec(mod) is None:
            return False, f'缺少依赖 {mod}（pip install .）'
    return True, 'ok'


def _crawl_images(ctx, celebrity, aliases='', count=None, work_dir='', **kwargs):
    from ... import crawler, ui
    cfg = ctx.cfg
    target = int(count or cfgmod.get(cfg, 'quality.target_count', 500) or 500)
    if work_dir:
        wd = security.ensure_within(Path(ctx.work_dirs['datasets_dir']), work_dir)
        wd.mkdir(parents=True, exist_ok=True)
    else:
        from ...pipeline.runner import create_work_dir
        wd, _params = create_work_dir(cfg, celebrity)
    raw_dir = wd / 'raw'
    ui.info(f'保存目录: {raw_dir}')
    progress = ui.make_progress()
    task = progress.add_task(f'爬取 {celebrity} 图片', total=target)
    try:
        progress.start()

        def _cb(done, total):
            progress.update(task, completed=done, total=total)

        saved = crawler.run_crawl(
            deploy.spider_dir(cfg),
            celebrity,
            [a.strip() for a in aliases.split(',') if a.strip()],
            ctx.env.get('XHS_COOKIE', ''),
            target,
            wd,
            quiet=True,
            progress_cb=_cb,
            cfg=cfg,
        )
    finally:
        progress.stop()
    return {'saved': saved, 'target': target, 'work_dir': str(wd), 'raw_dir': str(raw_dir)}


def _run_pipeline(ctx, work_dir='', celebrity='', caption_prompt='', target_count=None, **kwargs):
    from ...pipeline.runner import run_pipeline
    wd = _resolve_work_dir(ctx, work_dir)
    params = sessions.load_task(wd)
    name = celebrity or params.get('celebrity') or 'celebrity'
    vision = _vision_or_yunet(ctx)
    final_dir, zip_path, labels = run_pipeline(
        wd, ctx.cfg, vision, celebrity=name, caption_prompt=caption_prompt)
    count = len(labels) if labels else 0
    check = _check_target(count, target_count or cfgmod.get(ctx.cfg, 'quality.target_count', 0))
    result = {
        'work_dir': str(wd),
        'final_dir': str(final_dir) if final_dir else None,
        'zip_path': str(zip_path) if zip_path else None,
        'count': count,
        **check,
    }
    if check['needs_more']:
        message = (
            f'数量不足：当前 {count} 张，目标 {check["target"]} 张，缺少 {check["missing"]} 张。'
            '请调用 crawl_images 继续爬取补充（count 设为缺少数量），然后再次运行 run_pipeline。')
        return ToolResult.success(message, data=result)
    return result


def _package_dataset(ctx, work_dir='', celebrity='', **kwargs):
    from ...pipeline import steps
    wd = _resolve_work_dir(ctx, work_dir)
    final_dir = wd / 'final'
    if not final_dir.is_dir():
        raise RuntimeError(f'缺少 final/ 目录，请先运行 run_pipeline: {wd}')
    params = sessions.load_task(wd)
    name = celebrity or params.get('celebrity') or 'celebrity'
    zip_path, count = steps.package_zip(final_dir, Path(ctx.work_dirs['outputs_dir']), name)
    return {'zip_path': str(zip_path), 'count': count}


def _dataset_status(ctx, work_dir='', **kwargs):
    wd = _resolve_work_dir(ctx, work_dir)
    raw_count, final_count = sessions.count_state(wd)
    stages = []
    for name in ('check_report.json', 'judgment.json', 'similarity_report.json', 'task.json'):
        stages.append(name if (wd / name).exists() else None)
    return {
        'work_dir': str(wd),
        'raw_count': raw_count,
        'final_count': final_count,
        'stages': [s for s in stages if s],
    }


def _deploy_spider(ctx, **kwargs):
    spider_dir = deploy.deploy(ctx.cfg)
    return {'spider_dir': str(spider_dir)}
