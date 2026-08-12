# -*- coding: utf-8 -*-
"""Built-in tools: registered at startup, safe by default."""
from ...tools.registry import ToolRegistry


def register_builtins(registry: ToolRegistry):
    from . import filesystem, help_tools, pipeline_tools
    filesystem.register(registry)
    help_tools.register(registry)
    pipeline_tools.register(registry)
