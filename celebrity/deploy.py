# -*- coding: utf-8 -*-
"""Spider_XHS deploy and readiness checks."""
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as cfgmod
from . import ui


def _run(cmd, cwd, timeout=1800):
    ui.info('执行: ' + ' '.join(str(c) for c in cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or '').strip().splitlines()[-15:]
        raise RuntimeError('\n'.join(tail))
    return proc


def spider_dir(cfg):
    rel = cfg.get('spider_xhs', {}).get('dir', '') or 'third_party/Spider_XHS'
    p = Path(rel)
    if not p.is_absolute():
        p = cfgmod.ROOT / p
    return p


def ensure_spider_xhs(cfg):
    target = spider_dir(cfg)
    if target.is_dir():
        ui.success(f'Spider_XHS 已存在: {target}')
        return target
    repo = cfg.get('spider_xhs', {}).get('repo') or 'https://github.com/cv-cat/Spider_XHS.git'
    ui.info(f'未找到 Spider_XHS，正在从 {repo} 克隆到 {target} ...')
    git = shutil.which('git')
    if not git:
        raise RuntimeError('未找到 git，请先安装 git')
    target.parent.mkdir(parents=True, exist_ok=True)
    _run([git, 'clone', '--depth', '1', repo, str(target)], cwd=target.parent)
    ui.success('克隆完成')
    return target


def install_deps(spider_dir):
    spider_dir = Path(spider_dir)
    _run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=spider_dir)
    ui.success('Python 依赖安装完成')
    pkg = spider_dir / 'package.json'
    if pkg.exists():
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if npm:
            cache_dir = spider_dir / '.npm-cache'
            cache_dir.mkdir(parents=True, exist_ok=True)
            _run([npm, 'install', '--cache', str(cache_dir)], cwd=spider_dir)
            ui.success('Node 依赖安装完成')
    else:
        ui.warn('未发现 package.json，跳过 npm install')


def start_check(spider_dir):
    spider_dir = Path(spider_dir)
    code = (
        "import sys; sys.path.insert(0, '.'); "
        "from xhs_utils.common_util import init; "
        "cookies, base = init(); "
        "import apis.xhs_pc_apis; import apis.xhs_creator_apis; "
        "import spider.spider; print('SPIDER_START_OK')"
    )
    proc = subprocess.run(
        [sys.executable, '-c', code], cwd=str(spider_dir),
        capture_output=True, text=True, timeout=120)
    out = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode == 0 and 'SPIDER_START_OK' in out:
        ui.success('Spider_XHS 启动检查通过（模块导入与初始化正常）')
        return True
    ui.error('Spider_XHS 启动检查未通过，输出：')
    print(out[-2000:])
    return False


def check_deps(spider_dir):
    """Return a list of missing dependency descriptions (does not install)."""
    spider_dir = Path(spider_dir)
    missing = []
    py_check = (
        'import loguru, dotenv, requests, curl_cffi, execjs, qrcode, '
        'openpyxl, aiohttp, retry, cv2, numpy'
    )
    try:
        proc = subprocess.run(
            [sys.executable, '-c', py_check], cwd=str(spider_dir),
            capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            missing.append('Python 依赖未安装（cd third_party/Spider_XHS && pip install -r requirements.txt）')
    except Exception:
        missing.append('Python 依赖检查失败')
    if not shutil.which('node'):
        missing.append('Node.js 未安装')
    if not (spider_dir / 'node_modules' / 'crypto-js').exists():
        missing.append('Node 依赖未安装（cd third_party/Spider_XHS && npm install）')
    return missing


def deploy(cfg):
    """Clone (if needed), check deps without auto-installing, smoke test."""
    spider_dir = ensure_spider_xhs(cfg)
    missing = check_deps(spider_dir)
    if missing:
        ui.warn('检测到依赖未安装，Celebrity 不会自动安装，请手动执行：')
        for item in missing:
            ui.info(f'  - {item}')
    else:
        ui.success('依赖检查通过（Python + Node）')
    start_check(spider_dir)
    return spider_dir
