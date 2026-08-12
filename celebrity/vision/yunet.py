# -*- coding: utf-8 -*-
"""YuNet single-face detection (lightweight local vision provider).

Only a single face is accepted; angle/composition are classified from
landmarks. Requires opencv-python (optional extra `cv`).
"""
import math
from pathlib import Path

from .. import config as cfgmod
from .base import Verdict, VisionProvider

YUNET_FILENAME = 'face_detection_yunet_2023mar.onnx'


def ensure_yunet(cfg, confirm=None):
    """Download the YuNet ONNX model (after user confirmation) if missing."""
    from .. import ui as _ui

    models_dir = cfgmod.ensure_work_dirs(cfg)['models_dir']
    dest = models_dir / YUNET_FILENAME
    if dest.exists():
        return dest
    url = cfgmod.get(cfg, 'vision.yunet.url') or ''
    if not url:
        raise RuntimeError('未配置 YuNet 下载地址（vision.yunet.url）')
    if confirm is not None and not confirm(
            f'需要下载 YuNet 人脸检测模型（约 230KB，来自 opencv_zoo），是否继续？'):
        raise RuntimeError('用户已取消下载 YuNet 模型')
    import urllib.request
    _ui.info(f'下载 YuNet 模型: {url}')
    urllib.request.urlretrieve(url, dest)
    _ui.success(f'YuNet 模型已保存: {dest}')
    return dest


class YunetVision(VisionProvider):
    name = 'yunet'

    def __init__(self, cfg):
        self.cfg = cfg
        self.detector = None

    def _model_path(self) -> Path:
        cfg_path = cfgmod.get(self.cfg, 'model.yunet_url')  # legacy, keep signature safe
        models_dir = cfgmod.ensure_work_dirs(self.cfg)['models_dir']
        return models_dir / YUNET_FILENAME

    def check(self) -> tuple[bool, str]:
        try:
            import cv2  # noqa: F401
        except Exception:
            return False, '缺少 opencv-python（pip install celebrity[cv]）'
        if not self._model_path().exists():
            return False, f'缺少 YuNet 模型: {self._model_path()}'
        return True, f'YuNet（{self._model_path().name}）'

    def _load(self):
        import cv2
        self.cv2 = cv2

    def _read_image(self, path):
        """Read an image as a BGR numpy array.

        PIL-first so Windows Unicode paths (e.g. 宋雨琦_...) and non-JPEG
        formats work; cv2.imread cannot open Unicode paths on Windows.
        """
        import numpy as np
        from PIL import Image

        try:
            with Image.open(path) as im:
                arr = np.asarray(im.convert('RGB'))
            return self.cv2.cvtColor(arr, self.cv2.COLOR_RGB2BGR)
        except Exception:
            return self.cv2.imread(path)

    def _detect(self, img):
        import cv2
        h, w = img.shape[:2]
        if self.detector is None:
            self.detector = cv2.FaceDetectorYN.create(
                str(self._model_path()), '', (w, h),
                score_threshold=0.6, nms_threshold=0.3, top_k=5000)
        else:
            self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(img)
        return faces

    @staticmethod
    def _classify(bbox, landmarks, img_h):
        bx, by, bw, bh = (float(v) for v in bbox[:4])
        reye, leye, nose, rmouth, lmouth = landmarks
        eye_dx = leye[0] - reye[0]
        eye_dy = leye[1] - reye[1]
        eye_dist = max(math.hypot(eye_dx, eye_dy), 1e-6)
        eye_cx = (reye[0] + leye[0]) / 2.0
        eye_cy = (reye[1] + leye[1]) / 2.0
        mouth_cx = (rmouth[0] + lmouth[0]) / 2.0
        mouth_cy = (rmouth[1] + lmouth[1]) / 2.0
        mid_y = (eye_cy + mouth_cy) / 2.0
        nose_off_x = (nose[0] - eye_cx) / eye_dist
        nose_off_y = (nose[1] - mid_y) / eye_dist
        face_wh = bw / max(bh, 1e-6)
        if abs(nose_off_x) > 0.32 or face_wh < 0.62:
            angle = '右侧面' if nose_off_x > 0 else '左侧面'
        else:
            if nose_off_y < -0.16:
                angle = '仰拍'
            elif nose_off_y > 0.16:
                angle = '俯拍'
            else:
                angle = '正面'
        face_h_ratio = bh / max(img_h, 1e-6)
        if face_h_ratio > 0.32:
            comp = '特写'
        elif face_h_ratio >= 0.16:
            comp = '半身'
        else:
            comp = '全身'
        return angle, comp

    def judge(self, image_path) -> Verdict:
        self._load()
        img = self._read_image(str(image_path))
        if img is None:
            return Verdict(ok=False, reason='图片无法读取', meta={})
        h, w = img.shape[:2]
        try:
            faces = self._detect(img)
        except Exception as exc:
            return Verdict(ok=False, reason=f'检测失败: {exc}', meta={})
        if faces is None or len(faces) != 1:
            return Verdict(
                ok=False,
                reason='人脸数不为 1（可能含他人或无人脸）',
                meta={'faces': 0 if faces is None else int(len(faces))},
            )
        det = faces[0]
        pts = det[4:14].reshape(5, 2)
        angle, comp = self._classify(det[:4], pts, h)
        return Verdict(
            ok=True,
            reason='单人通过',
            meta={
                'faces': 1,
                'single_person': 'yes',
                'angle': angle,
                'composition': comp,
                'width': int(w),
                'height': int(h),
            },
        )
