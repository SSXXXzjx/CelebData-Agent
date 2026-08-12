# -*- coding: utf-8 -*-
"""tui-banner 二进制自动下载与渲染（Windows/Linux/macOS）"""
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from . import config as cfgmod
from . import ui

TOOLS_DIR = Path(__file__).resolve().parent.parent / 'tools'


def _machine():
    m = platform.machine().lower()
    if m in ('x86_64', 'amd64', 'x64'):
        return 'x86_64'
    if m in ('aarch64', 'arm64'):
        return 'aarch64'
    return m


def platform_subdir():
    """返回内置二进制所在子目录与可执行文件名"""
    system = platform.system().lower()
    arch = _machine()
    if system == 'windows':
        return 'win-x86_64', 'tui-banner.exe'
    if system == 'darwin':
        if arch == 'aarch64':
            return 'darwin-aarch64', 'tui-banner'
        return None, None  # x86_64 mac 无官方发布包，走 ASCII 回退
    if system == 'linux':
        return ('linux-aarch64' if arch == 'aarch64' else 'linux-x86_64'), 'tui-banner'
    return None, None


def detect_asset():
    system = platform.system().lower()
    version = 'v0.2.2'
    sub, exe = platform_subdir()
    if sub is None:
        return version, None, exe
    if system == 'windows':
        return version, f'tui-banner-{version}-x86_64-pc-windows-msvc.zip', exe
    if system == 'darwin':
        return version, f'tui-banner-{version}-aarch64-apple-darwin.tar.gz', exe
    suffix = 'aarch64-unknown-linux-gnu' if sub == 'linux-aarch64' else 'x86_64-unknown-linux-gnu'
    return version, f'tui-banner-{version}-{suffix}.tar.gz', exe


def _download(url, dest):
    ui.info(f'下载 tui-banner: {url}')
    req = urllib.request.Request(url, headers={'User-Agent': 'celebrity-cli'})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, 'wb') as f:
        shutil.copyfileobj(resp, f, length=1024 * 256)
    return dest


def _extract(archive, exe_name, target_dir):
    target_dir.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.namelist():
                if member.endswith(exe_name) or member.endswith('/' + exe_name):
                    with zf.open(member) as src, open(target_dir / exe_name, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    break
    else:
        with tarfile.open(archive, 'r:gz') as tf:
            for member in tf.getmembers():
                if member.name.endswith(exe_name):
                    src = tf.extractfile(member)
                    with open(target_dir / exe_name, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    break
    binary = target_dir / exe_name
    if not binary.exists():
        raise RuntimeError(f'解压后未找到 {exe_name}')
    if os.name != 'nt':
        binary.chmod(0o755)
    return binary


def ensure_binary(cfg=None):
    """确保 tui-banner 二进制可用：优先使用内置（tools/<平台>/），缺失才自动下载"""
    cfg = cfg or cfgmod.load_config()
    version, asset, exe_name = detect_asset()
    sub, _ = platform_subdir()
    if sub:
        bundled = TOOLS_DIR / sub / exe_name
        if bundled.exists():
            if os.name != 'nt':
                try:
                    bundled.chmod(0o755)  # 防止拷贝后丢失执行权限
                except Exception:
                    pass
            return bundled
    legacy = TOOLS_DIR / exe_name
    if legacy.exists():
        return legacy
    if asset is None:
        return None
    target_dir = (TOOLS_DIR / sub) if sub else TOOLS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    base = cfg.get('tui_banner', {}).get('base_url') or 'https://github.com/coolbeevip/tui-banner/releases/download'
    url = f'{base}/{version}/{asset}'
    archive = target_dir / asset
    try:
        _download(url, archive)
        return _extract(archive, exe_name, target_dir)
    except Exception as exc:
        ui.warn(f'tui-banner 自动下载失败（{exc}），将使用内置纯文本横幅。')
        return None
    finally:
        if archive.exists():
            try:
                archive.unlink()
            except Exception:
                pass


_FALLBACK_LINES = [
    '   ██████████  █████        ██████████  ███████████   ███████████    █████  ███████████',
    '█ ░░███░░░░░█ ░░███        ░░███░░░░░█ ░░███░░░░░███ ░░███░░░░░███  ░░███  ░█░░░███░░░█',
    '   ░███  █ ░   ░███         ░███  █ ░   ░███    ░███  ░███    ░███   ░███  ░   ░███  ░',
    '   ░██████     ░███         ░██████     ░██████████   ░██████████    ░███      ░███',
    '   ░███░░█     ░███         ░███░░█     ░███░░░░░███  ░███░░░░░███   ░███      ░███',
    '█  ░███ ░   █  ░███      █  ░███ ░   █  ░███    ░███  ░███    ░███   ░███      ░███',
    '   ██████████  ███████████  ██████████  ███████████   █████   █████  █████     █████',
    '  ░░░░░░░░░░  ░░░░░░░░░░░  ░░░░░░░░░░  ░░░░░░░░░░░   ░░░░░   ░░░░░  ░░░░░     ░░░░░',
]


def _fallback_banner(text):
    try:
        p = Path(__file__).resolve().parent.parent / 'assets' / 'banner.txt'
        if p.exists():
            lines = [ln.rstrip() for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()]
            if lines:
                return '\n'.join(lines)
    except Exception:
        pass
    return '\n'.join(_FALLBACK_LINES)


def render(text, cfg=None, width=80):
    """渲染横幅；优先 tui-banner，失败用内置文本横幅"""
    cfg = cfg or cfgmod.load_config()
    binary = ensure_binary(cfg)
    if binary:
        style = cfg.get('tui_banner', {}).get('style', 'forest-sky')
        palette = cfg.get('tui_banner', {}).get('palette', '')
        try:
            cmd = [str(binary), '--text', text, '--style', style, '--color-mode', 'auto']
            if palette:
                cmd += ['--palette', palette]
            proc = subprocess.run(
                cmd,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
            )
            out = (proc.stdout or '').strip()
            if out:
                print(out)
                return
        except Exception:
            pass
    fallback = _fallback_banner(text.upper())
    style = cfg.get('tui_banner', {}).get('fallback_text_style', 'bold magenta')
    ui.console.print(f'[{style}]{fallback}[/{style}]')