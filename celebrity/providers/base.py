# -*- coding: utf-8 -*-
"""Provider boundary: a normalized chat request/response contract.

Transport quirks, auth, retries, and base URLs belong to provider
implementations; core conversation logic never branches per vendor.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ProviderError(Exception):
    """Structured provider failure. retriable=True means bounded retry applies."""

    def __init__(self, message: str, retriable: bool = False):
        super().__init__(message)
        self.retriable = retriable


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatResult:
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


class Provider(ABC):
    """Normalized chat provider. Implementations must be lazy and cheap."""

    name = 'base'

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResult:
        """Send a completion request and return the normalized result."""

    def check(self) -> tuple[bool, str]:
        """Side-effect-free availability probe (e.g. key presence)."""
        return True, 'ok'
