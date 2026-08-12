# -*- coding: utf-8 -*-
"""OpenAI-compatible vision provider (e.g. Qwen-VL via DashScope).

Images are sent as bounded base64 data URLs. The same provider abstraction
serves both judging and captioning; DeepSeek chat is text-only, so configure
a vision-capable endpoint for image work.
"""
import base64
import io
import os
from pathlib import Path
from typing import Dict, Optional

import httpx
from PIL import Image

from .. import config as cfgmod
from .base import Verdict, VisionProvider, parse_json_answer

_JUDGE_PROMPT = (
    '你是一个明星图片审核模型。请判断这张图片是否符合要求：'
    '1) 图片主体必须是目标人物本人（画面中不能出现任何其他人物）；'
    '2) 判断拍摄角度（正面/左侧面/右侧面/仰拍/俯拍/背面/其他）与构图（特写/半身/全身/其他）。'
    '只输出 JSON，不要输出其它内容，格式：'
    '{"is_target": true/false, "single_person": true/false, '
    '"angle": "角度", "composition": "构图", "reason": "简短中文原因"}'
)


class OpenAICompatVision(VisionProvider):
    name = 'openai'

    def __init__(self, cfg, profile='openai'):
        self.cfg = cfg
        self.profile = profile
        settings = cfgmod.get(cfg, f'vision.{profile}', {}) or {}
        self.base_url = settings.get('base_url') or ''
        self.model = settings.get('model') or 'qwen-vl-plus'
        self.api_key_env = settings.get('api_key_env') or 'DASHSCOPE_API_KEY'
        self.api_key = os.environ.get(self.api_key_env, '')
        self.max_image_mb = int(settings.get('max_image_mb', 20))
        self.timeout = float(cfgmod.get(cfg, 'agent.timeout_seconds', 120) or 120)
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def check(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, '未配置 vision.openai.base_url'
        if not self.api_key:
            return False, f'缺少视觉 API Key：请在 .env 中设置 {self.api_key_env}'
        return True, f'OpenAI 兼容视觉（{self.model}）'

    def _data_url(self, image_path) -> str:
        path = Path(image_path)
        if path.stat().st_size > self.max_image_mb * 1024 * 1024:
            raise ValueError(f'图片超过 {self.max_image_mb}MB 限制: {path.name}')
        with Image.open(path) as im:
            img = im.convert('RGB')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=88)
        b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
        return f'data:image/jpeg;base64,{b64}'

    def _complete(self, messages, temperature=0.0) -> str:
        payload = {'model': self.model, 'messages': messages, 'temperature': temperature}
        resp = self.client.post(
            cfgmod.get(self.cfg, 'vision.openai.base_url', self.base_url).rstrip('/') + '/chat/completions'
            if not self.base_url.endswith('/chat/completions')
            else self.base_url,
            json=payload,
            headers={'Authorization': f'Bearer {self.api_key}'},
        )
        resp.raise_for_status()
        choices = resp.json().get('choices') or []
        if not choices:
            raise RuntimeError('视觉接口响应缺少 choices')
        return (choices[0].get('message') or {}).get('content') or ''

    def judge(self, image_path) -> Verdict:
        from PIL import Image as _PIL
        try:
            with _PIL.open(str(image_path)) as im:
                w, h = im.size
        except Exception as exc:
            return Verdict(ok=False, reason=f'图片无法读取: {exc}', meta={})
        data_url = self._data_url(image_path)
        content = [
            {'type': 'image_url', 'image_url': {'url': data_url}},
            {'type': 'text', 'text': _JUDGE_PROMPT},
        ]
        answer = self._complete([{'role': 'user', 'content': content}])
        parsed = parse_json_answer(answer)
        is_target = bool(parsed.get('is_target', False))
        single = bool(parsed.get('single_person', True))
        ok = bool(is_target and single)
        return Verdict(
            ok=ok,
            reason=str(parsed.get('reason') or ('模型判断通过' if ok else '模型判断未通过')),
            meta={
                'single_person': 'yes' if single else 'no',
                'angle': str(parsed.get('angle', '未知')),
                'composition': str(parsed.get('composition', '未知')),
                'width': int(w),
                'height': int(h),
                'vlm_reason': str(parsed.get('reason', '')),
            },
        )

    def caption(self, image_path, prompt: str) -> str:
        data_url = self._data_url(image_path)
        content = [
            {'type': 'image_url', 'image_url': {'url': data_url}},
            {'type': 'text', 'text': prompt},
        ]
        return self._complete([{'role': 'user', 'content': content}], temperature=0.0).strip()
