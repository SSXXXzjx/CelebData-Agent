# -*- coding: utf-8 -*-
"""Security helpers: secret redaction, path containment, risk gates."""
from pathlib import Path

RISK_READ = 'read'
RISK_WRITE = 'write'
RISK_DESTRUCTIVE = 'destructive'
ALL_RISKS = (RISK_READ, RISK_WRITE, RISK_DESTRUCTIVE)


class Redactor:
    """Mask known secrets in any user-facing or persisted text."""

    def __init__(self, secrets=()):
        self._secrets = self._clean(secrets)

    @staticmethod
    def _clean(secrets):
        return sorted(
            {s for s in secrets if s and len(s) >= 4},
            key=len, reverse=True,
        )

    def add(self, value):
        if value and len(value) >= 4 and value not in self._secrets:
            self._secrets.append(value)
            self._secrets.sort(key=len, reverse=True)

    @property
    def secrets(self):
        return tuple(self._secrets)

    def redact(self, text):
        if not text or not self._secrets:
            return text
        for secret in self._secrets:
            text = text.replace(secret, '***')
        return text


def ensure_within(root, target):
    """Resolve target relative to root and refuse paths escaping root.

    Raises PermissionError on escape so callers fail closed.
    """
    root = Path(root).resolve()
    target = Path(target)
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if target != root and root not in target.parents:
        raise PermissionError(f'路径越界，已拒绝: {target}')
    return target


def mask_cookie(cookie):
    """Show only a hint of a cookie for status output."""
    if not cookie:
        return '（未设置）'
    return f'{cookie[:6]}...{cookie[-4:]}（已设置）' if len(cookie) > 12 else '（已设置）'


def mask_secret(value):
    """Redacted hint for any secret (API key, cookie, password)."""
    if not value:
        return ''
    if len(value) <= 8:
        return '***'
    return f'{value[:4]}***{value[-2:]}'
