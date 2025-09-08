from pathlib import Path
from nicegui import ui, app
from download_dila_iiif_max import download_image
import os, uuid, tempfile, time

# ──────────────────────────────────────────────────────────────────────────────
# Shared temp dir for server-side downloads (unique filenames for concurrency)
# ──────────────────────────────────────────────────────────────────────────────
TMP_DIR = Path(tempfile.gettempdir()) / 'iiif_dl'
TMP_DIR.mkdir(exist_ok=True)

# Expose the temp dir at /downloads so users can fetch results
app.add_static_files('/downloads', str(TMP_DIR))

# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────
with ui.card():
    ui.label('請輸入 CBETA 作業網址')
    url_input = ui.input('UV3 URL').style('width: 80vw;').props('clearable')

    # Area to show the generated download links
    links_area = ui.column().classes('gap-2 mt-2')

    def download_by_uv3():
        url = (url_input.value or '').strip()
        if not url:
            ui.notify('請輸入 UV3 URL', type='warning')
            return
        # Unique filename per request (avoid collision when many users click at once)
        filename = f'iiif_{uuid.uuid4().hex}.jpg'
        out_path = TMP_DIR / filename
        try:
            saved_path = download_image(uv3=url, out=str(out_path))
            if not Path(saved_path).exists():
                raise RuntimeError('檔案未成功寫入磁碟')

            public_url = f'/downloads/{filename}'
            ui.notify('下載完成，請點擊連結取得檔案', type='positive')

            # Append a new link row (preserve history of downloads in this session)
            with links_area:
                with ui.row().classes('items-center gap-2'):
                    ui.label('Download URL:')
                    ui.link(public_url, public_url, new_tab=True)
                    # (Optional) also provide a hidden immediate download trigger
                    # dl = ui.download(str(saved_path), filename=filename, hidden=True)
                    # ui.run_javascript(f'document.getElementById("{dl.id}").click()')
        except Exception as e:
            ui.notify(f'下載失敗：{e}', type='negative')

    ui.button('從CBETA拿最高解析度圖片', on_click=download_by_uv3, color='primary')

# ──────────────────────────────────────────────────────────────────────────────
# Housekeeping: clean old files (older than 1 hour)
# ──────────────────────────────────────────────────────────────────────────────

def cleanup_old_files():
    cutoff = time.time() - 3600
    try:
        for p in TMP_DIR.glob('iiif_*.jpg'):
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
    except Exception as e:
        print('Cleanup error:', e)

ui.timer(1800, cleanup_old_files)  # every 30 minutes

ui.run(
    title='文檔處理系統',
    favicon='📄',
    port=80,                     # 改這裡
    host='0.0.0.0',
    reload=False,
    show=True,
)