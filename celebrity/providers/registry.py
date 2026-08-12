# -*- coding: utf-8 -*-
"""Provider registry. New vendors can be plain OpenAI-compatible YAML profiles."""
from typing import Callable, Dict, List

from .. import config as cfgmod
from .base import Provider, ProviderError

_FACTORIES: Dict[str, Callable[[dict, str], Provider]] = {}


def register(name: str, factory: Callable[[dict, str], Provider]):
    _FACTORIES[name] = factory


def provider_names() -> List[str]:
    return sorted(_FACTORIES)


def create_provider(cfg: dict, name: str | None = None) -> Provider:
    """Build a provider. Any YAML profile with base_url/model is usable even
    without an explicit factory (OpenAI-compatible)."""
    from .openai_compat import OpenAICompatProvider

    name = name or cfgmod.get(cfg, 'provider.default', 'deepseek')
    factory = _FACTORIES.get(name)
    if factory:
        return factory(cfg, name)
    settings = cfgmod.get(cfg, f'provider.{name}', {})
    if settings and settings.get('base_url'):
        return OpenAICompatProvider(cfg, profile=name)
    raise ProviderError(f'未知或未配置的 provider: {name}')


def _register_builtins():
    from .openai_compat import OpenAICompatProvider

    def factory(cfg, profile):
        return OpenAICompatProvider(cfg, profile=profile)

    for alias in ('deepseek', 'openai', 'openai_compat'):
        register(alias, factory)


_register_builtins()
