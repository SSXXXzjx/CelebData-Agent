# -*- coding: utf-8 -*-
"""Tool contract: schema, availability gate, risk level, and handler."""
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..security import RISK_READ


@dataclass
class ToolContext:
    """Runtime context handed to every tool handler."""

    cfg: Dict[str, Any]
    work_dirs: Dict[str, Any]
    redactor: Any = None
    vision: Any = None
    confirm: Optional[Callable[[str], bool]] = None
    allowed_risks: tuple = (RISK_READ,)
    env: Dict[str, str] = field(default_factory=dict)
    tool_names: Optional[Callable[[], List[str]]] = None

    def redact(self, text):
        return self.redactor.redact(text) if self.redactor else text


@dataclass
class ToolResult:
    ok: bool
    content: str
    data: Optional[Dict[str, Any]] = None

    @classmethod
    def success(cls, content: str, data: Optional[Dict[str, Any]] = None) -> 'ToolResult':
        return cls(ok=True, content=content, data=data)

    @classmethod
    def failure(cls, content: str, data: Optional[Dict[str, Any]] = None) -> 'ToolResult':
        return cls(ok=False, content=content, data=data)

    def to_json(self) -> str:
        return json.dumps(
            {'ok': self.ok, 'content': self.content, 'data': self.data},
            ensure_ascii=False,
        )


@dataclass
class ToolSpec:
    """One model-callable capability."""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON schema: {type, properties, required}
    handler: Callable[..., Any]  # handler(ctx, **arguments)
    check_fn: Optional[Callable[[ToolContext], tuple[bool, str]]] = None
    risk: str = RISK_READ
    category: str = 'general'
