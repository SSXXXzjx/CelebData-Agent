# -*- coding: utf-8 -*-
"""Meta tools: about and capability listing."""
from ... import __version__
from ...tools.base import ToolSpec


def register(registry):
    registry.register(ToolSpec(
        name='about',
        description='Celebrity 版本、可用工具与工作目录信息',
        parameters={'type': 'object', 'properties': {}},
        handler=_about,
        risk='read',
        category='meta',
    ))
    registry.register(ToolSpec(
        name='list_tools',
        description='列出当前可用的全部工具及其说明',
        parameters={'type': 'object', 'properties': {}},
        handler=_list_tools,
        risk='read',
        category='meta',
    ))


def _about(ctx, **kwargs):
    return {
        'name': 'Celebrity',
        'version': __version__,
        'work_dirs': {k: str(v) for k, v in ctx.work_dirs.items()},
        'vision': (getattr(ctx.vision, 'name', None) if ctx.vision else None),
    }


def _list_tools(ctx, **kwargs):
    registry = kwargs.pop('_registry', None)
    return {'tools': [t.name for t in registry._tools.values()]}
