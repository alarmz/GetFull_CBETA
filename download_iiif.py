import os
import math
import requests
from PIL import Image
from io import BytesIO

# IIIF 參數
BASE_URL = "https://dia.dila.edu.tw/iiif/2/Tv01p0300%2F309"  # 第309頁
TILE_SIZE = 512  # 這個值可以從 Network 裡面 tile URL 看出來
OUTPUT_FILE = "page309_full.jpg"

def get_info_json():
    """取得 IIIF info.json 包含圖像寬高"""
    info_url = f"{BASE_URL}/info.json"
    r = requests.get(info_url)
    r.raise_for_status()
    return r.json()

def download_tile(x, y, w, h):
    """下載單個 tile"""
    region = f"{x},{y},{w},{h}"
    url = f"{BASE_URL}/{region}/full/0/default.jpg"
    r = requests.get(url)
    r.raise_for_status()
    return Image.open(BytesIO(r.content))

def main():
    info = get_info_json()
    width = info["width"]
    height = info["height"]

    cols = math.ceil(width / TILE_SIZE)
    rows = math.ceil(height / TILE_SIZE)

    print(f"Image size: {width}x{height}, tiles: {cols} x {rows}")

    full_img = Image.new("RGB", (width, height))

    for row in range(rows):
        for col in range(cols):
            x = col * TILE_SIZE
            y = row * TILE_SIZE
            w = min(TILE_SIZE, width - x)
            h = min(TILE_SIZE, height - y)
            print(f"Downloading tile ({col},{row}) at {x},{y},{w},{h}")
            tile = download_tile(x, y, w, h)
            full_img.paste(tile, (x, y))

    full_img.save(OUTPUT_FILE)
    print(f"Saved {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
