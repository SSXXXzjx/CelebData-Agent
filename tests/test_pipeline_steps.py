# -*- coding: utf-8 -*-
"""Pipeline steps over tiny synthetic images."""

import io
import json
import zipfile

import pytest
from PIL import Image

from celebrity.pipeline import steps
from celebrity.vision.base import Verdict


def test_read_cv_image_unicode_path(tmp_path):
    cv2 = pytest.importorskip('cv2')
    from PIL import Image
    from celebrity.similarity import _read_cv_image

    work = tmp_path / '宋雨琦'
    work.mkdir()
    path = work / 'x.jpg'
    Image.new('RGB', (64, 64), (10, 20, 30)).save(path, 'JPEG')
    img = _read_cv_image(str(path))
    assert img is not None


def make_image(path, size=(800, 800), color=(120, 80, 40)):
    img = Image.new('RGB', size, color)
    img.save(path, 'JPEG')


def make_work_dir(tmp_path, n=3, size=(800, 800)):
    raw = tmp_path / 'raw'
    raw.mkdir()
    for i in range(n):
        make_image(raw / f'cand_{i:05d}.jpg', size=size, color=(120 + i * 10, 80, 40))
    return tmp_path


class FakeVision:
    name = 'fake'
    caption_batch_size = 1

    def check(self):
        return True, 'ok'

    def judge(self, image_path):
        return Verdict(ok=True, reason='通过', meta={
            'single_person': 'yes', 'angle': '正面', 'composition': '半身',
            'width': 800, 'height': 600,
        })

    def caption(self, image_path, prompt):
        return 'a young asian woman, front-facing, medium shot'


def test_initial_check_filters_small(tmp_path):
    work = make_work_dir(tmp_path, n=2, size=(800, 800))
    make_image(work / 'raw' / 'small.jpg', size=(400, 300))
    report = steps.initial_check(work / 'raw', min_short_side=720)
    assert len(report['valid']) == 2
    assert any(item['file'] == 'small.jpg' for item in report['invalid'])


def test_dedup_removes_duplicates(tmp_path):
    work = make_work_dir(tmp_path, n=2, size=(800, 800))
    duplicate = work / 'raw' / 'cand_00000.jpg'
    dup_copy = work / 'raw' / 'cand_00010.jpg'
    dup_copy.write_bytes(duplicate.read_bytes())
    report = steps.initial_check(work / 'raw', min_short_side=720)
    kept = steps.dedup(work / 'raw', report['valid'])
    assert len(kept) == 2
    assert not dup_copy.exists()


def test_judge_images_resumable(tmp_path):
    work = make_work_dir(tmp_path, n=2)
    report = steps.initial_check(work / 'raw', min_short_side=720)
    accepted, rejected = steps.judge_images(work / 'raw', FakeVision(), report['valid'])
    assert len(accepted) == 2 and not rejected
    assert (work / 'judgment.json').exists()
    # second run reuses the persisted judgments
    accepted2, _ = steps.judge_images(work / 'raw', FakeVision(), report['valid'])
    assert len(accepted2) == 2


def test_judge_images_none_passes_all(tmp_path):
    work = make_work_dir(tmp_path, n=2)
    report = steps.initial_check(work / 'raw', min_short_side=720)
    accepted, rejected = steps.judge_images(work / 'raw', None, report['valid'])
    assert len(accepted) == 2 and not rejected


def test_build_dataset_and_package(tmp_path):
    work = make_work_dir(tmp_path, n=2)
    accepted = [
        {'file': f'cand_{i:05d}.jpg', 'ok': True, 'reason': '通过',
         'meta': {'single_person': 'yes', 'angle': '正面', 'composition': '半身'}}
        for i in range(2)
    ]
    final_dir, labels = steps.build_dataset(
        work, accepted, prefix='dataset', vision=FakeVision(),
        caption_prompt='caption', caption_enabled=True)
    images = sorted(final_dir.glob('*.jpg'))
    assert len(images) == 2
    assert (final_dir / 'labels.csv').exists()
    assert labels[0]['filename'] == 'dataset_00001.jpg'
    outputs = work.parent / 'outputs'
    outputs.mkdir()
    zip_path, count = steps.package_zip(final_dir, outputs, '宋雨琦')
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if n.endswith('.jpg')]
    assert count == 2 and len(entries) == 2


def test_trim_dataset(tmp_path):
    work = make_work_dir(tmp_path, n=3)
    accepted = [
        {'file': f'cand_{i:05d}.jpg', 'ok': True, 'reason': '通过', 'meta': {}}
        for i in range(3)
    ]
    final_dir, labels = steps.build_dataset(work, accepted, caption_enabled=False)
    kept = steps.trim_dataset(final_dir, labels, 1)
    assert len(kept) == 1
    assert len(list(final_dir.glob('*.jpg'))) == 1
