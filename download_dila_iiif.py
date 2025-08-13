#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DILA (dia.dila.edu.tw) IIIF downloader
- Given a uv3 URL (e.g. https://dia.dila.edu.tw/uv3/index.html?id=Tv01p0300#?c=0&m=0&s=0&cv=309&xywh=...)
  or canon/volume/canvas index, download the FULL (max-resolution) image.
- Prefers IIIF Image API "full/full/0/default.jpg".
- If server blocks that route, falls back to stitching tiles from the IIIF Image API.

Usage examples:
  python download_dila_iiif.py --uv3 "https://dia.dila.edu.tw/uv3/index.html?id=Tv01p0300#?c=0&m=0&s=0&cv=309"
  python download_dila_iiif.py --canon T --volume 1 --canvas 309
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

def parse_uv3(url: str):
    """Extract canon, volume and canvas index from a uv3 URL.
       Example id: Tv01p0300 -> canon=T, volume=01; use cv as canvas index (int)."""
    q = urlparse(url)
    # id=Tv01p0300
    id_param = parse_qs(q.query).get('id', [''])[0]
    frag = q.fragment or ''
    # cv=309 in fragment "#?c=0&m=0&s=0&cv=309&xywh=..."
    m_cv = re.search(r'(?:[?&]|^)cv=(\d+)', frag)
    canvas_index = int(m_cv.group(1)) if m_cv else 0

    m_id = re.match(r'^([A-Za-z])v(\d+)', id_param)  # e.g. T v01 ...
    if not m_id:
        raise ValueError(f"Cannot parse id from URL: {id_param}")
    canon = m_id.group(1)  # 'T'
    volume = m_id.group(2) # '01'
    # Normalize volume to 2 digits (site uses v01/v02... for Taisho per uv3 IDs)
    volume_norm = volume.zfill(2)
    return canon, volume_norm, canvas_index

def manifest_url(canon: str, volume_2d: str):
    # According to DILA docs: https://dia.dila.edu.tw/static_pages/iiif
    # 大正藏 第一冊： https://dia.dila.edu.tw/iiif/T/v01/manifest.json
    return f"https://dia.dila.edu.tw/iiif/{canon}/v{volume_2d}/manifest.json"

def pick_canvas_and_service(manifest: dict, canvas_index: int):
    """Return (canvas, image_service_id) for a given index from a IIIF v2 manifest."""
    seqs = manifest.get('sequences') or []
    if not seqs:
        raise ValueError("No sequences in manifest (unexpected IIIF format)")
    canvases = seqs[0].get('canvases') or []
    if not canvases:
        raise ValueError("No canvases in manifest")
    if canvas_index < 0 or canvas_index >= len(canvases):
        raise IndexError(f"Canvas index {canvas_index} out of range (0..{len(canvases)-1})")
    canvas = canvases[canvas_index]

    # images[0].resource.service['@id'] is typical in IIIF v2
    images = canvas.get('images') or []
    if not images:
        raise ValueError("Canvas has no images[]")
    res = images[0].get('resource') or {}
    svc = res.get('service') or {}
    svc_id = svc.get('@id') or svc.get('id')
    if not svc_id:
        # Some manifests may nest under resource['service'][0]
        if isinstance(svc, list) and svc:
            svc_id = svc[0].get('@id') or svc[0].get('id')
    if not svc_id:
        raise ValueError("No IIIF Image API service '@id' found on canvas.resource")
    return canvas, svc_id.rstrip('/')

def url_try(session: requests.Session, url: str, stream=False, ok=(200,)):
    r = session.get(url, timeout=30, stream=stream, headers={"User-Agent":"Mozilla/5.0"})
    if r.status_code not in ok:
        raise requests.HTTPError(f"{r.status_code} for {url}", response=r)
    return r

def download_full_jpg(session: requests.Session, svc_id: str, out_path: str):
    """Try the straightforward full image route."""
    # IIIF Image API 2.0: {base}/{region}/{size}/{rotation}/{quality}.{format}
    # full/full/0/default.jpg
    url = f"{svc_id}/full/full/0/default.jpg"
    r = url_try(session, url)
    with open(out_path, 'wb') as f:
        f.write(r.content)
    return out_path

def get_info(session: requests.Session, svc_id: str):
    # info.json
    info_url = f"{svc_id}/info.json"
    r = url_try(session, info_url)
    return r.json()

def download_and_stitch(session: requests.Session, svc_id: str, out_path: str):
    """Fallback: download tiles and stitch to one full image."""
    info = get_info(session, svc_id)
    width = info.get('width')
    height = info.get('height')
    if not (width and height):
        raise ValueError("info.json missing width/height")

    # Try to read tile size, else assume 512
    tile_w = tile_h = 512
    tiles = info.get('tiles') or []
    if tiles:
        tw = tiles[0].get('width') or tiles[0].get('height')
        if tw:
            tile_w = tile_h = int(tw)

    cols = math.ceil(width / tile_w)
    rows = math.ceil(height / tile_h)

    full_img = Image.new("RGB", (width, height))
    for row in range(rows):
        for col in range(cols):
            x = col * tile_w
            y = row * tile_h
            w = min(tile_w, width - x)
            h = min(tile_h, height - y)
            region = f"{x},{y},{w},{h}"
            tile_url = f"{svc_id}/{region}/full/0/default.jpg"
            r = url_try(session, tile_url)
            tile = Image.open(BytesIO(r.content)).convert("RGB")
            if tile.size != (w, h):
                tile = tile.resize((w, h), Image.LANCZOS)
            full_img.paste(tile, (x, y))

    full_img.save(out_path, quality=95)
    return out_path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uv3', help='uv3 URL like https://dia.dila.edu.tw/uv3/index.html?id=Tv01p0300#?cv=309')
    ap.add_argument('--canon', default='T', help='Canon code, e.g., T, JM, GA (default: T)')
    ap.add_argument('--volume', type=int, help='Volume number (e.g., 1 for v01)')
    ap.add_argument('--canvas', type=int, default=0, help='Canvas index (0-based; matches cv in uv3)')
    ap.add_argument('-o', '--out', default=None, help='Output file path (default: auto)')
    args = ap.parse_args()

    if args.uv3:
        canon, vol2, canvas_idx = parse_uv3(args.uv3)
    else:
        if args.volume is None:
            ap.error("Must provide --uv3 or both --canon and --volume")
        canon = args.canon
        vol2 = str(args.volume).zfill(2)
        canvas_idx = args.canvas

    man_url = manifest_url(canon, vol2)
    print(f"[i] Manifest: {man_url}")
    s = requests.Session()
    m = url_try(s, man_url).json()

    canvas, svc_id = pick_canvas_and_service(m, canvas_idx)
    label = canvas.get('label') or canvas.get('label',{}).get('@value') or f"cv{canvas_idx}"
    if isinstance(label, dict):
        label = label.get('@value') or label.get('en') or label.get('zh') or f"cv{canvas_idx}"

    out_name = args.out or f"{canon}v{vol2}_{label}.jpg"
    out_path = os.path.abspath(out_name)
    print(f"[i] Image service: {svc_id}")
    print(f"[i] Output: {out_path}")

    try:
        print("[i] Trying full/full/0/default.jpg ...")
        download_full_jpg(s, svc_id, out_path)
        print(f"[✓] Saved (direct full): {out_path}")
    except Exception as e:
        print(f"[!] Direct full failed: {e}")
        print("[i] Falling back to tile stitching via info.json ...")
        stitched = download_and_stitch(s, svc_id, out_path)
        print(f"[✓] Saved (stitched): {stitched}")

if __name__ == '__main__':
    main()
