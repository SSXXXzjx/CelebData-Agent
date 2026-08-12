# -*- coding: utf-8 -*-
"""相似去重：打标签前用感知哈希或 ONNX 小模型特征找出高度相似图片，每组保留首张

- method='phash'（默认，极快，无需模型）：
  imagehash pHash（64bit），汉明距离 <= threshold（默认 8）判为相似。
- method='onnx'：
  使用任意 ONNX 特征提取小模型（如 MobileNet 系列），
  输出向量归一化后计算余弦相似度 >= threshold（默认 0.92）判为相似。
"""
import os

import numpy as np


def _default_threshold(method):
    return 0.92 if method == 'onnx' else 8


def _phash(path):
    import imagehash
    from PIL import Image
    with Image.open(path) as im:
        return imagehash.phash(im.convert('RGB'))


def _load_onnx_net(model_path):
    import cv2
    net = cv2.dnn.readNetFromONNX(str(model_path))
    return net


def _read_cv_image(path):
    """Read an image for ONNX embedding; PIL fallback handles Unicode paths."""
    import cv2
    img = cv2.imread(str(path))
    if img is not None:
        return img
    from PIL import Image
    with Image.open(path) as im:
        arr = np.asarray(im.convert('RGB'))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _onnx_embedding(net, img):
    import cv2
    blob = cv2.dnn.blobFromImage(
        img, scalefactor=1.0 / 127.5, size=(224, 224),
        mean=(127.5, 127.5, 127.5), swapRB=True, crop=False)
    net.setInput(blob)
    out = net.forward()
    vec = out.flatten().astype(np.float64)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 1e-12 else vec


def dedup_similar(paths, method='phash', threshold=None, model_path=None, progress_cb=None):
    """输入图片路径列表，按相似度分组，返回 (keep, remove)，keep 为每组首张（保持输入顺序）"""
    method = (method or 'phash').strip().lower()
    if threshold is None:
        threshold = _default_threshold(method)
    threshold = float(threshold)

    cache = {}

    def feature(p):
        if p not in cache:
            try:
                if method == 'onnx':
                    img = _read_cv_image(p)
                    if img is None:
                        return None
                    cache[p] = _onnx_embedding(_net, img)
                else:
                    cache[p] = _phash(p)
            except Exception:
                cache[p] = None
        return cache[p]

    _net = None
    if method == 'onnx':
        if not model_path or not os.path.exists(model_path):
            raise RuntimeError(f'onnx 相似度模型不存在: {model_path}')
        _net = _load_onnx_net(model_path)

    def similar(a, b):
        if a is None or b is None:
            return False
        if method == 'onnx':
            return float(np.dot(a, b)) >= threshold
        return (a - b) <= threshold

    groups = []
    processed = 0
    for p in paths:
        feat = feature(p)
        placed = False
        for g in groups:
            if similar(feat, g[1]):
                g[0].append(p)
                placed = True
                break
        if not placed:
            groups.append(([p], feat))
        processed += 1
        if progress_cb:
            progress_cb(processed, len(paths))

    keep = [g[0][0] for g in groups]
    remove = [p for g in groups for p in g[0][1:]]
    return keep, remove
