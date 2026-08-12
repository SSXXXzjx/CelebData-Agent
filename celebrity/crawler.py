# -*- coding: utf-8 -*-
"""Spider_XHS crawl integration.

Imports of the vendored Spider_XHS happen lazily inside _run_crawl_impl so the
agent core stays light. The Xiaohongshu cookie is read from XHS_COOKIE env or
passed explicitly; it is never logged.

Standalone: python -m celebrity.crawler --spider-dir <dir> --celebrity 宋雨琦
            --aliases YUQI --count 600 --out <raw_dir>
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import requests
from loguru import logger
from retry import retry

from . import config as cfgmod

DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _next_cand_no(raw_dir):
    """Next candidate file number so a resumed crawl never overwrites files."""
    nos = []
    for p in Path(raw_dir).glob('cand_*.jpg'):
        try:
            nos.append(int(p.stem.split('_')[1]))
        except (IndexError, ValueError):
            pass
    return max(nos, default=0)


def normalize_image(path):
    """Validate a downloaded image and normalize it to standard JPEG (RGB).

    Returns True when the file was decodable and has been rewritten as JPEG;
    False when the bytes are not an image (e.g. HTML error pages).
    """
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.load()
            rgb = im.convert('RGB')
        rgb.save(path, 'JPEG', quality=90)
        return True
    except Exception:
        return False


@retry(tries=3, delay=1.0)
def download_image(url, path):
    resp = requests.get(url, timeout=30, headers={'User-Agent': DEFAULT_USER_AGENT})
    resp.raise_for_status()
    with open(path, 'wb') as f:
        f.write(resp.content)


def clean_image_url(raw_url, xhs_apis):
    try:
        ok, msg, new_url = xhs_apis.get_note_no_water_img(raw_url)
        if ok and new_url:
            return new_url
    except Exception:
        pass
    return raw_url


def build_queries(celebrity, aliases, keywords=None, sort_types=None):
    """Compose content-type keyword queries (写真/单人照/自拍/生活照 etc.)."""
    keywords = keywords or ['写真', '单人照', '自拍', '生活照', '高清写真', '画报', '杂志', '日常', '随拍', '美图']
    sort_types = sort_types or [0, 2]
    names = [celebrity] + [a for a in aliases if a and a != celebrity]
    queries = []
    for idx, name in enumerate(names):
        tails = keywords if idx == 0 else ['写真', '自拍', '美图']
        for tail in tails:
            q = f'{name} {tail}'.strip()
            for st in sort_types:
                queries.append((q, st))
    return queries


def collect_note_urls(api, queries, notes_per_query=40, api_sleep=1.2):
    seen_ids = set()
    urls = []
    for query, sort_type in queries:
        logger.info(f'搜索笔记: {query} (排序 {sort_type})')
        try:
            success, msg, notes = api.search_some_note(
                query, notes_per_query, sort_type_choice=sort_type)
        except Exception as exc:
            logger.warning(f'搜索异常 {query}: {exc}')
            time.sleep(api_sleep)
            continue
        if not success:
            logger.warning(f'搜索失败 {query}: {msg}')
            time.sleep(api_sleep)
            continue
        new = 0
        for item in notes:
            if item.get('model_type') != 'note':
                continue
            nid = item.get('id')
            token = item.get('xsec_token')
            if not nid or not token or nid in seen_ids:
                continue
            seen_ids.add(nid)
            urls.append(
                f'https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source=pc_search')
            new += 1
        logger.info(f'{query}: 新增 {new} 条, 累计 {len(urls)}')
        time.sleep(api_sleep)
    return urls


def collect_user_notes(api, celebrity, aliases, max_users=2, max_notes=30, api_sleep=1.2):
    urls = []
    seen_ids = set()
    names = [celebrity] + [a for a in aliases if a and a != celebrity]
    for name in names:
        logger.info(f'搜索用户: {name}')
        try:
            success, msg, users = api.search_some_user(name, max_users)
        except Exception as exc:
            logger.warning(f'用户搜索异常 {name}: {exc}')
            continue
        if not success:
            logger.warning(f'用户搜索失败 {name}: {msg}')
            continue
        for user in users[:max_users]:
            uid = user.get('user_id') or user.get('id')
            token = user.get('xsec_token', '')
            if not uid:
                continue
            user_url = (f'https://www.xiaohongshu.com/user/profile/{uid}'
                        f'?xsec_token={token}&xsec_source=pc_search')
            try:
                ok, msg, note_list = api.get_user_all_notes(user_url)
            except Exception as exc:
                logger.warning(f'用户笔记异常 {uid}: {exc}')
                continue
            if not ok:
                logger.warning(f'用户笔记失败 {uid}: {msg}')
                continue
            new = 0
            for n in note_list[:max_notes]:
                nid = n.get('note_id')
                token2 = n.get('xsec_token')
                if not nid or not token2 or nid in seen_ids:
                    continue
                seen_ids.add(nid)
                urls.append(
                    f'https://www.xiaohongshu.com/explore/{nid}?xsec_token={token2}&xsec_source=pc_user')
                new += 1
            logger.info(f'用户 {uid}: 新增 {new} 条, 累计 {len(urls)}')
            time.sleep(api_sleep)
    return urls


def extract_images(api, note_url):
    try:
        success, msg, res = api.get_note_info(note_url)
    except Exception as exc:
        logger.warning(f'笔记详情异常 {note_url}: {exc}')
        return []
    if not success:
        logger.warning(f'笔记详情失败 {note_url}: {msg}')
        return []
    items = (res.get('data') or {}).get('items') or []
    if not items:
        return []
    card = items[0].get('note_card') or {}
    urls = []
    for img in card.get('image_list') or []:
        try:
            raw = img['info_list'][1]['url']
        except (KeyError, IndexError, TypeError):
            continue
        urls.append(clean_image_url(raw, api))
    return urls


def run_crawl(spider_dir, celebrity, aliases, cookie, count, out_dir,
              progress_cb=None, quiet=False, cfg=None, work_root=None):
    """Crawl candidate images into <out_dir>/raw with a manifest.json."""
    cfg = cfg or cfgmod.load_config()
    crawl_cfg = cfg.get('crawl', {}) or {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'crawl.log'
    if quiet:
        logger.remove()
        logger.add(str(log_path), encoding='utf-8', level='INFO')
    try:
        return _run_crawl_impl(
            Path(spider_dir), celebrity, aliases, cookie, count, out_dir, progress_cb,
            keywords=crawl_cfg.get('keywords'),
            sort_types=crawl_cfg.get('sort_types'),
            notes_per_query=crawl_cfg.get('notes_per_query'),
            api_sleep=crawl_cfg.get('api_sleep', 1.2),
            download_sleep=crawl_cfg.get('download_sleep', 0.5),
        )
    finally:
        if quiet:
            logger.remove()
            logger.add(sys.stderr)


def _check_signing_env(spider_dir):
    node = shutil.which('node')
    if not node:
        raise RuntimeError(
            '未检测到 Node.js。请先安装 Node.js 20+ 并加入 PATH，'
            f'然后在 {spider_dir} 目录执行 npm install（Windows 用 npm.cmd install）')
    if not (Path(spider_dir) / 'node_modules' / 'crypto-js').is_dir():
        raise RuntimeError(
            f'缺少 Node 依赖 crypto-js：请在 {spider_dir} 目录执行 npm install'
            '（Windows 用 npm.cmd install）')


def _run_crawl_impl(spider_dir, celebrity, aliases, cookie, count, out_dir, progress_cb,
                    keywords=None, sort_types=None, notes_per_query=None,
                    api_sleep=1.2, download_sleep=0.5):
    _check_signing_env(spider_dir)
    sys.path.insert(0, str(spider_dir))
    from apis.xhs_pc_apis import XHS_Apis
    from xhs_utils.xhs_pc import XHSPcAuth

    if not cookie:
        raise RuntimeError('未提供 Cookie（请在 .env 设置 XHS_COOKIE 或用 --cookie）')

    auth = XHSPcAuth.from_cookie(cookie)
    api = XHS_Apis(auth)
    api.bootstrap()

    npq = notes_per_query or 40
    queries = build_queries(celebrity, aliases, keywords, sort_types)
    note_urls = collect_note_urls(api, queries, npq, api_sleep)
    note_urls += collect_user_notes(api, celebrity, aliases, api_sleep=api_sleep)
    logger.info(f'共收集 {len(note_urls)} 个笔记链接，开始下载图片...')

    raw_dir = out_dir / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / 'manifest.json'
    seen_urls = set()
    seen_hashes = set()
    existing = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            for fname, meta in existing.items():
                if meta.get('url'):
                    seen_urls.add(meta['url'])
        except Exception:
            existing = {}
    for p in raw_dir.glob('*.jpg'):
        seen_hashes.add(md5_of_file(str(p)))

    saved = 0
    no = _next_cand_no(raw_dir)
    for note_url in note_urls:
        if saved >= count:
            break
        imgs = extract_images(api, note_url)
        time.sleep(api_sleep)
        for img_url in imgs:
            if saved >= count:
                break
            if not img_url or img_url in seen_urls:
                continue
            seen_urls.add(img_url)
            no += 1
            tmp = raw_dir / f'cand_{no:05d}.jpg'
            try:
                download_image(img_url, tmp)
            except Exception as exc:
                logger.warning(f'下载失败 {img_url}: {exc}')
                continue
            if not normalize_image(tmp):
                logger.warning(f'下载内容不是有效图片，已丢弃 {img_url}')
                tmp.unlink(missing_ok=True)
                continue
            digest = md5_of_file(tmp)
            if digest in seen_hashes:
                tmp.unlink(missing_ok=True)
                continue
            seen_hashes.add(digest)
            existing[tmp.name] = {'url': img_url, 'note': note_url}
            saved += 1
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            logger.info(f'[{saved}/{count}] 已下载 {tmp.name}')
            if progress_cb:
                progress_cb(saved, count)
            time.sleep(download_sleep)

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    logger.info(f'爬取完成：{saved} 张 → {raw_dir}')
    return saved


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    parser = argparse.ArgumentParser(prog='celebrity.crawler')
    parser.add_argument('--spider-dir', required=True)
    parser.add_argument('--celebrity', required=True)
    parser.add_argument('--aliases', default='')
    parser.add_argument('--count', type=int, default=500)
    parser.add_argument('--out', required=True)
    parser.add_argument('--cookie', default='')
    args = parser.parse_args()
    cookie = args.cookie or os.environ.get('XHS_COOKIE', '')
    saved = run_crawl(
        args.spider_dir, args.celebrity,
        [a.strip() for a in args.aliases.split(',') if a.strip()],
        cookie, args.count, args.out)
    print(f'CRAWL_DONE {saved}')


if __name__ == '__main__':
    main()
