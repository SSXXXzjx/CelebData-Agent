# -*- coding: utf-8 -*-
"""Tool registry: registration, model-visible schemas, validation, dispatch.

Schema visibility, availability, risk permission, and execution are separate
gates: a schema never grants permission by itself.
"""
import json
from typing import Any, Dict, List, Optional

from ..security import RISK_DESTRUCTIVE
from .base import ToolContext, ToolResult, ToolSpec

_TYPE_CHECK = {
    'string': str,
    'integer': int,
    'number': (int, float),
    'boolean': bool,
    'array': list,
    'object': dict,
}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec):
        if spec.name in self._tools:
            raise ValueError(f'工具重复注册: {spec.name}')
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return sorted(self._tools)

    def definitions(self) -> List[Dict[str, Any]]:
        """Model-visible function schemas (availability is enforced at dispatch)."""
        return [
            {
                'type': 'function',
                'function': {
                    'name': spec.name,
                    'description': spec.description,
                    'parameters': spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    def available(self, name: str, ctx: ToolContext) -> tuple[bool, str]:
        spec = self._tools.get(name)
        if spec is None:
            return False, f'未知工具: {name}'
        if spec.check_fn is not None:
            return spec.check_fn(ctx)
        return True, 'ok'

    @staticmethod
    def _validate(spec: ToolSpec, arguments: Dict[str, Any]) -> Dict[str, Any]:
        schema = spec.parameters or {}
        props = schema.get('properties', {}) or {}
        for required in schema.get('required', []) or []:
            if required not in arguments:
                raise ValueError(f'缺少必要参数: {required}')
        for key, value in arguments.items():
            prop = props.get(key)
            if not prop:
                continue
            expected = _TYPE_CHECK.get(prop.get('type'))
            if expected and not isinstance(value, expected):
                raise ValueError(f'参数 {key} 类型应为 {prop.get("type")}')
        return arguments

    def dispatch(self, name: str, arguments: Dict[str, Any], ctx: ToolContext) -> str:
        """Execute a tool and return a JSON string for the model transcript."""
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult.failure(f'未知工具: {name}').to_json()

        ok, reason = self.available(name, ctx)
        if not ok:
            return ToolResult.failure(f'工具不可用: {reason}').to_json()

        if spec.risk not in (ctx.allowed_risks or ()):
            return ToolResult.failure(f'未授权操作（{spec.name} 需要 {spec.risk} 权限）').to_json()

        if spec.risk == RISK_DESTRUCTIVE and ctx.confirm is not None:
            confirmed = ctx.confirm(f'工具 {spec.name} 将执行删除/覆盖操作，是否继续？')
            if not confirmed:
                return ToolResult.failure('用户拒绝该操作').to_json()

        try:
            args = self._validate(spec, arguments or {})
            result = spec.handler(ctx, **args)
        except PermissionError as exc:
            return ToolResult.failure(f'权限拒绝: {exc}').to_json()
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            return ToolResult.failure(f'工具执行失败: {ctx.redact(message)}').to_json()

        if isinstance(result, ToolResult):
            result.content = ctx.redact(result.content)
            return result.to_json()
        if isinstance(result, str):
            return ToolResult.success(ctx.redact(result)).to_json()
        return ToolResult.success(
            ctx.redact(json.dumps(result, ensure_ascii=False)),
            data=result,
        ).to_json()
