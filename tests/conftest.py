# -*- coding: utf-8 -*-
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def cfg(tmp_path):
    return {
        'agent': {
            'max_turns': 5,
            'temperature': 0.0,
            'timeout_seconds': 30,
            'retries': 2,
            'allow_risk': ['read', 'write'],
        },
        'provider': {
            'default': 'deepseek',
            'deepseek': {
                'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-v4-flash',
                'api_key_env': 'DEEPSEEK_API_KEY',
            },
        },
        'vision': {'provider': ''},
        'work': {
            'datasets_dir': str(tmp_path / 'datasets'),
            'models_dir': str(tmp_path / 'models'),
            'outputs_dir': str(tmp_path / 'outputs'),
        },
        'crawl': {
            'keywords': ['写真'],
            'sort_types': [0],
            'notes_per_query': 40,
            'api_sleep': 0.01,
            'download_sleep': 0.01,
        },
        'quality': {
            'min_short_side': 720,
            'target_count': 10,
            'similarity_dedup': False,
            'similarity_method': 'phash',
        },
        'label': {'filename_prefix': 'dataset', 'caption_enabled': True},
    }
