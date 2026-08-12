# -*- coding: utf-8 -*-
"""Read-only filesystem tools bound to the configured work directories."""
import fnmatch
from pathlib import Path

from ... import security
from ...tools.base import ToolSpec


def register(registry):
    registry.register(ToolSpec(
        name='list_work_files',
        description='列出工作目录下的文件（默认 raw/*.jpg），用于查看爬取/构建进度',
        parameters={
            'type': 'object',
            'properties': {
                'work_dir': {'type': 'string', 'description': '任务目录名或路径（留空用最近任务）'},
                'pattern': {'type': 'string', 'description': '文件名通配符，默认 *.jpg'},
                'limit': {'type': 'integer', 'description': '最多返回条数，默认 100'},
            },
        },
        handler=_list_files,
        risk='read',
        category='filesystem',
    ))


def _list_files(ctx, work_dir='', pattern='*.jpg', limit=100):
    from ... import sessions
    datasets_dir = Path(ctx.work_dirs['datasets_dir'])
    if work_dir:
        wd = security.ensure_within(datasets_dir, work_dir)
    else:
        wd = sessions.latest_work_dir(ctx.cfg)
    if wd is None or not wd.is_dir():
        raise RuntimeError('没有可用的任务目录')
    files = sorted(
        p for p in wd.rglob('*') if p.is_file() and fnmatch.fnmatch(p.name, pattern)
    )
    limited = files[:max(0, int(limit or 100))]
    return {
        'work_dir': str(wd),
        'total': len(files),
        'files': [str(p.relative_to(wd)) for p in limited],
    }
