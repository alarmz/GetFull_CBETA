# ===============================
# download_dila_iiif_max.py
# (with TLS whitelist skip for dia.dila.edu.tw via env DILA_SKIP_TLS_VERIFY)
# ===============================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DILA (dia.dila.edu.tw) IIIF downloader — max resolution
- Resolve canvas via manifest.
- Try best-order: explicit intrinsic width, "max", then stitch tiles.
- While stitching, request region with exact pixel width to avoid downsampling.
- NEW: Only for dia.dila.edu.tw, if env DILA_SKIP_TLS_VERIFY=1/true/yes, skip TLS verify.
"""

import re
import os
import sys
import json
import math
import argparse
from urllib.parse import urlparse, parse_qs
from io import BytesIO

import requests
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0"}

# ──────────────────────────────────────────────────────────────────────────────
# TLS verify control (domain whitelist)
# ──────────────────────────────────────────────────────────────────────────────
_SKIP_RAW = os.getenv('DILA_SKIP_TLS_VERIFY', '0').strip().lower()
_SKIP_TLS = _SKIP_RAW in {'1', 'true', 'yes'}


def _skip_verify_for(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ''
    except Exception:
        return False
    return _SKIP_TLS and host.endswith('dia.dila.edu.tw')


# ──────────────────────────────────────────────────────────────────────────────
# UV3 helpers
# ──────────────────────────────────────────────────────────────────────────────

def parse_uv3(url: str):
    q = urlparse(url)
    id_param = parse_qs(q.query).get('id', [''])[0]
    frag = q.fragment or ''
    m_cv = re.search(r'(?:[?&]|^)cv=(\d+)', frag)
    canvas_index = int(m_cv.group(1)) if m_cv else 0

    m_id = re.match(r'^([A-Za-z])v(\d+)', id_param)
    if not m_id:
        raise ValueError(f"Cannot parse id from URL: {id_param}")
    canon = m_id.group(1)
    volume = m_id.group(2).zfill(2)
    return canon, volume, canvas_index


def manifest_url(canon: str, volume_2d: str):
    return f"https://dia.dila.edu.tw/iiif/{canon}/v{volume_2d}/manifest.json"


def pick_canvas_service(manifest: dict, canvas_index: int):
    seqs = manifest.get('sequences') or []
    if not seqs:
        raise ValueError("No sequences[]")
    canvases = seqs[0].get('canvases') or []
    if not canvases:
        raise ValueError("No canvases[]")
    if canvas_index < 0 or canvas_index >= len(canvases):
        raise IndexError(f"cv {canvas_index} out of range 0..{len(canvases)-1}")
    canvas = canvases[canvas_index]

    images = canvas.get('images') or []
    if not images:
        raise ValueError("Canvas has no images[]")
    res = images[0].get('resource') or {}
    svc = res.get('service')
    if isinstance(svc, list) and svc:
        svc = svc[0]
    if not isinstance(svc, dict):
        raise ValueError("No Image API service on resource")
    svc_id = (svc.get('@id') or svc.get('id') or '').rstrip('/')
    if not svc_id:
        raise ValueError("Missing service @id")
    return canvas, svc_id


# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────

def http_ok_old(session, url, stream=False, ok=(200,)):
    r = session.get(url, timeout=30, stream=stream, headers=UA,
                    verify=not _skip_verify_for(url))
    if r.status_code not in ok:
        raise requests.HTTPError(f"{r.status_code} for {url}", response=r)
    return r

from urllib.parse import urlparse

def http_ok(session, url, stream=False, ok=(200,)):
    # 判斷 domain
    domain = urlparse(url).hostname or ""
    # 只對 dia.dila.edu.tw 關閉 verify
    verify = True
    if domain.endswith("dia.dila.edu.tw"):
        verify = False

    r = session.get(url, timeout=30, stream=stream, headers=UA, verify=verify)
    if r.status_code not in ok:
        raise requests.HTTPError(f"{r.status_code} for {url}", response=r)
    return r



def get_info(session, svc_id: str):
    info_url = f"{svc_id}/info.json"
    r = http_ok(session, info_url)
    return r.json()


# ──────────────────────────────────────────────────────────────────────────────
# Direct max try + Tile stitching
# ──────────────────────────────────────────────────────────────────────────────

def try_direct_best(session, svc_id: str, info: dict, out: str):
    """Try explicit intrinsic width, then 'max', then generic full/full."""
    width = info.get('width')
    tried = []

    if width:
        urls = [
            f"{svc_id}/full/{width},/0/default.jpg",  # explicit intrinsic width
            f"{svc_id}/full/max/0/default.jpg",       # IIIF level 2 'max'
            f"{svc_id}/full/full/0/default.jpg",      # generic
        ]
    else:
        urls = [
            f"{svc_id}/full/max/0/default.jpg",
            f"{svc_id}/full/full/0/default.jpg",
        ]

    for u in urls:
        try:
            r = http_ok(session, u)
            with open(out, 'wb') as f:
                f.write(r.content)
            return u
        except Exception as e:
            tried.append((u, str(e)))
    raise RuntimeError("Direct full download failed", tried)


def fetch_tile_exact(session, svc_id: str, x, y, w, h):
    """Fetch a tile region with no downscaling. Prefer size '{w},' (exact width)."""
    urls = [
        f"{svc_id}/{x},{y},{w},{h}/{w},/0/default.jpg",
        f"{svc_id}/{x},{y},{w},{h}/pct:100/0/default.jpg",
        f"{svc_id}/{x},{y},{w},{h}/full/0/default.jpg",
    ]
    for u in urls:
        r = http_ok(session, u)
        img = Image.open(BytesIO(r.content)).convert("RGB")
        if img.size == (w, h):
            return img
        img = img.resize((w, h), Image.LANCZOS)
        return img
    raise RuntimeError("Failed to fetch tile region")


def stitch(session, svc_id: str, info: dict, out: str):
    width = info['width']; height = info['height']
    tile_w = tile_h = 512
    tiles = info.get('tiles') or []
    if tiles:
        tw = tiles[0].get('width') or tiles[0].get('height')
        if tw:
            tile_w = tile_h = int(tw)

    cols = math.ceil(width / tile_w)
    rows = math.ceil(height / tile_h)

    full = Image.new("RGB", (width, height))
    for row in range(rows):
        for col in range(cols):
            x = col * tile_w
            y = row * tile_h
            w = min(tile_w, width - x)
            h = min(tile_h, height - y)
            tile = fetch_tile_exact(session, svc_id, x, y, w, h)
            full.paste(tile, (x, y))
    full.save(out, quality=95)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def download_image(uv3: str | None = None, canon: str = 'T', volume: int | None = None,
                   canvas: int = 0, out: str | None = None) -> str:
    """Download one IIIF image and return the saved path."""
    if uv3:
        canon, vol2, cv = parse_uv3(uv3)
    else:
        if volume is None:
            raise ValueError("Provide uv3 or volume")
        vol2 = str(volume).zfill(2)
        cv = canvas

    man = manifest_url(canon, vol2)
    s = requests.Session()
    m = http_ok(s, man).json()
    canvas_obj, svc_id = pick_canvas_service(m, cv)

    label = canvas_obj.get('label')
    if isinstance(label, dict):
        label = label.get('@value') or label.get('en') or label.get('zh')
    label = label or f"cv{cv}"
    out = out or f"{canon}v{vol2}_{label}.jpg"
    out = os.path.abspath(out)

    print(f"[i] manifest: {man}")
    print(f"[i] svc_id  : {svc_id}")
    info = get_info(s, svc_id)
    w, h = info.get('width'), info.get('height')
    print(f"[i] intrinsic size: {w}x{h}")
    maxW = info.get('maxWidth'); maxH = info.get('maxHeight'); maxA = info.get('maxArea')
    try_direct = True
    if (maxW and w and maxW < w) or (maxH and h and maxH < h):
        try_direct = False
    if maxA and w and h and (w * h) > maxA:
        try_direct = False

    if try_direct:
        try:
            used = try_direct_best(s, svc_id, info, out)
            print(f"[✓] saved direct: {out} ({used})")
            got = Image.open(out)
            if w and got.width < w:
                print(f"[!] direct result width {got.width} < intrinsic {w}, stitching instead...")
                stitch(s, svc_id, info, out)
                print(f"[✓] saved stitched: {out}")
        except Exception as e:
            print(f"[!] direct failed: {e}; stitching...")
            stitch(s, svc_id, info, out)
            print(f"[✓] saved stitched: {out}")
    else:
        print("[i] Direct full is capped by maxWidth/maxHeight/maxArea; stitching...")
        stitch(s, svc_id, info, out)
        print(f"[✓] saved stitched: {out}")

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uv3', help='uv3 URL like https://dia.dila.edu.tw/uv3/index.html?id=Tv01p0300#?cv=309')
    ap.add_argument('--canon', default='T')
    ap.add_argument('--volume', type=int)
    ap.add_argument('--canvas', type=int, default=0)
    ap.add_argument('-o', '--out', default=None)
    args = ap.parse_args()
    download_image(args.uv3, args.canon, args.volume, args.canvas, args.out)


if __name__ == '__main__':
    main()

