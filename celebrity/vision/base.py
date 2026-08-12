# -*- coding: utf-8 -*-
"""Vision provider boundary."""
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict


def parse_json_answer(answer: str) -> Dict:
    """Extract the first JSON object from a model reply (robust to fences)."""
    text = (answer or '').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


@dataclass
class Verdict:
    ok: bool
    reason: str
    meta: Dict = field(default_factory=dict)


class VisionProvider(ABC):
    name = 'base'

    @abstractmethod
    def check(self) -> tuple[bool, str]:
        """Side-effect-free availability probe."""

    @abstractmethod
    def judge(self, image_path) -> Verdict:
        """Decide whether an image is a single-person shot of the target."""

    def caption(self, image_path, prompt: str) -> str:
        raise NotImplementedError('当前视觉模型不支持 caption 生成')

    def caption_batch(self, image_paths, prompt: str, batch_size: int = 1) -> Dict[str, str]:
        return {str(p): self.caption(p, prompt) for p in image_paths}

    @property
    def caption_batch_size(self) -> int:
        return 1
