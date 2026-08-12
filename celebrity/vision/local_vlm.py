# -*- coding: utf-8 -*-
"""Local Qwen3-VL vision provider (optional, extra `vlm`).

Lazy imports keep the default install light: torch/transformers/modelscope
are only loaded when this provider is selected. Loading and inference follow
the ModelScope official example: dtype=auto + device_map=auto, flash_attention_2
with automatic fallback, and apply_chat_template(tokenize=True).
"""
import importlib.util
from pathlib import Path

from .. import config as cfgmod
from .base import Verdict, VisionProvider, parse_json_answer

_VLM_PROMPT = (
    '你是一个明星图片审核模型。请判断这张图片是否符合要求：'
    '1) 图片主体必须是目标人物本人（画面中不能出现任何其他人物）；'
    '2) 判断拍摄角度（正面/左侧面/右侧面/仰拍/俯拍/背面/其他）与构图（特写/半身/全身/其他）。'
    '只输出 JSON，不要输出其它内容，格式：'
    '{"is_target": true/false, "single_person": true/false, '
    '"angle": "角度", "composition": "构图", "reason": "简短中文原因"}'
)


def _vlm_ready(path: Path) -> bool:
    path = Path(path)
    if not path.is_dir() or not (path / 'config.json').exists():
        return False
    return len(list(path.glob('*.safetensors'))) > 0


def ensure_vlm(cfg, confirm=None):
    """Download Qwen3-VL via ModelScope (after user confirmation) if missing."""
    from .. import ui as _ui

    vision = LocalVLMVision(cfg)
    ok, _reason = vision.check()
    if ok:
        return vision.model_dir
    repo = cfgmod.get(cfg, 'vision.local_vlm.repo') or 'Qwen/Qwen3-VL-8B-Instruct'
    if confirm is not None and not confirm(
            f'需要下载本地 VLM 模型（{repo}，约 16GB，来自 ModelScope），是否继续？'):
        raise RuntimeError('用户已取消下载 VLM 模型')
    try:
        import modelscope  # noqa: F401
    except Exception as exc:
        raise RuntimeError(f'缺少 modelscope 依赖，无法下载 VLM 模型: {exc}')
    from modelscope import snapshot_download
    vision.model_dir.mkdir(parents=True, exist_ok=True)
    _ui.info(f'开始下载 {repo} 到 {vision.model_dir} ...')
    snapshot_download(repo, local_dir=str(vision.model_dir))
    if not _vlm_ready(vision.model_dir):
        raise RuntimeError('VLM 模型下载可能未完成，请检查模型目录')
    return vision.model_dir


class LocalVLMVision(VisionProvider):
    name = 'local_vlm'

    def __init__(self, cfg):
        self.cfg = cfg
        settings = cfgmod.get(cfg, 'vision.local_vlm', {}) or {}
        self.model_dir = Path(settings.get('model_dir') or 'models/Qwen3-VL-8B-Instruct')
        if not self.model_dir.is_absolute():
            self.model_dir = cfgmod.ROOT / self.model_dir
        self._attn_implementation = (settings.get('attn_implementation') or '').strip().lower()
        self._caption_batch_size = max(1, int(settings.get('caption_batch_size') or 1))
        self.caption_max_new_tokens = int(settings.get('caption_max_new_tokens') or 512)
        self.judge_max_new_tokens = int(settings.get('judge_max_new_tokens') or 160)
        self._model = None
        self._processor = None
        self._device = None
        self._torch = None

    @property
    def caption_batch_size(self):
        return self._caption_batch_size

    def check(self) -> tuple[bool, str]:
        if importlib.util.find_spec('torch') is None or importlib.util.find_spec('transformers') is None:
            return False, '缺少 torch/transformers（pip install celebrity[vlm]）'
        if not _vlm_ready(self.model_dir):
            return False, f'VLM 模型不完整: {self.model_dir}'
        return True, f'本地 VLM（{self.model_dir.name}）'

    @staticmethod
    def _import_vlm_classes():
        """Prefer the modelscope official entry; fall back to transformers."""
        try:
            from modelscope import Qwen3VLForConditionalGeneration, AutoProcessor
            return Qwen3VLForConditionalGeneration, AutoProcessor
        except Exception:
            pass
        try:
            from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
            return Qwen3VLForConditionalGeneration, AutoProcessor
        except Exception:
            try:
                from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
                return Qwen2_5_VLForConditionalGeneration, AutoProcessor
            except Exception:
                from transformers import AutoModelForImageTextToText, AutoProcessor
                return AutoModelForImageTextToText, AutoProcessor

    def _load(self):
        if self._model is not None:
            return
        if not _vlm_ready(self.model_dir):
            raise RuntimeError(f'VLM 模型不完整: {self.model_dir}')
        try:
            import torch
        except Exception as exc:
            raise RuntimeError(
                f'缺少 VLM 运行依赖（torch/transformers），请执行: pip install celebrity[vlm]。原因: {exc}')
        self._device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self._torch = torch
        vlm_cls, processor_cls = self._import_vlm_classes()
        self._processor = processor_cls.from_pretrained(str(self.model_dir))
        self._model = self._load_model(vlm_cls)
        self._model.eval()

    def _load_model(self, vlm_cls):
        torch = self._torch
        cuda = self._device == 'cuda'
        use_device_map = False
        if cuda:
            try:
                import accelerate  # noqa: F401
                use_device_map = True
            except Exception:
                pass

        if self._attn_implementation:
            attempts = [self._attn_implementation]
            if cuda and self._attn_implementation != 'sdpa':
                attempts.append('sdpa')
        elif cuda:
            attempts = ['flash_attention_2', 'sdpa']
        else:
            attempts = ['']

        last_exc = None
        for impl in attempts:
            try:
                if cuda and use_device_map:
                    load_kwargs = {'device_map': 'auto', 'dtype': 'auto'}
                elif cuda:
                    load_kwargs = {'dtype': torch.bfloat16}
                else:
                    load_kwargs = {'dtype': torch.float32}
                if impl:
                    load_kwargs['attn_implementation'] = impl
                try:
                    model = vlm_cls.from_pretrained(str(self.model_dir), **load_kwargs)
                except TypeError:
                    legacy_kwargs = {'torch_dtype': torch.bfloat16 if cuda else torch.float32}
                    if cuda and use_device_map:
                        legacy_kwargs['device_map'] = 'auto'
                    if impl:
                        legacy_kwargs['attn_implementation'] = impl
                    model = vlm_cls.from_pretrained(str(self.model_dir), **legacy_kwargs)
                if not use_device_map:
                    model = model.to(self._device)
                return model
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(f'VLM 模型加载失败: {last_exc}')

    @staticmethod
    def _message(image, prompt):
        return [{
            'role': 'user',
            'content': [
                {'type': 'image', 'image': image},
                {'type': 'text', 'text': prompt},
            ],
        }]

    @staticmethod
    def _collect_images(conversations):
        result = []
        for conversation in conversations:
            imgs = []
            for item in (conversation[0].get('content') or []):
                if item.get('type') == 'image':
                    imgs.append(item['image'])
            result.append(imgs)
        return result

    def _build_inputs(self, messages, padding=True):
        conversations = messages if (messages and isinstance(messages[0], list)) else [messages]
        try:
            if len(conversations) == 1:
                inputs = self._processor.apply_chat_template(
                    conversations[0], tokenize=True, add_generation_prompt=True,
                    return_dict=True, return_tensors='pt', padding=padding)
            else:
                inputs = self._processor.apply_chat_template(
                    conversations, tokenize=True, add_generation_prompt=True,
                    return_dict=True, return_tensors='pt', padding=padding)
        except Exception:
            texts = [self._processor.apply_chat_template(
                m, tokenize=False, add_generation_prompt=True) for m in conversations]
            inputs = self._processor(
                text=texts, images=self._collect_images(conversations),
                padding=padding, return_tensors='pt')
        return inputs.to(self._device)

    def _generate(self, messages, max_new_tokens):
        self._load()
        inputs = self._build_inputs(messages)
        with self._torch.no_grad():
            generated_ids = self._model.generate(
                **inputs, max_new_tokens=max_new_tokens, do_sample=False, temperature=0)
        trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        return self._processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)

    def judge(self, image_path) -> Verdict:
        self._load()
        from PIL import Image
        try:
            with Image.open(str(image_path)) as im:
                w, h = im.size
        except Exception as exc:
            return Verdict(ok=False, reason=f'图片无法读取: {exc}', meta={})
        answers = self._generate(
            self._message(str(image_path), _VLM_PROMPT), self.judge_max_new_tokens)
        parsed = parse_json_answer(answers[0])
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
        answers = self._generate(
            self._message(str(image_path), prompt), self.caption_max_new_tokens)
        return answers[0].strip()

    def caption_batch(self, image_paths, prompt: str, batch_size: int = 1) -> dict:
        self._load()
        bs = max(1, int(batch_size or self.caption_batch_size or 1))
        results = {}
        paths = [str(p) for p in image_paths]
        for start in range(0, len(paths), bs):
            chunk = paths[start:start + bs]
            messages = [self._message(p, prompt) for p in chunk]
            answers = self._generate(messages, self.caption_max_new_tokens)
            for p, ans in zip(chunk, answers):
                results[p] = ans.strip()
        return results
