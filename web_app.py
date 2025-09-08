# web_app.py
from pathlib import Path
from nicegui import ui, app
from download_dila_iiif_max import download_image  # ← 同目錄匯入
import os, uuid, tempfile, time

# ──────────────────────────────────────────────────────────────────────────────
# 共享暫存資料夾（多人同時使用以 UUID 檔名避衝突）
# ──────────────────────────────────────────────────────────────────────────────
TMP_DIR = Path(tempfile.gettempdir()) / 'iiif_dl'
TMP_DIR.mkdir(exist_ok=True)

# 將暫存目錄掛載為 /downloads，讓用戶能以 URL 下載
app.add_static_files('/downloads', str(TMP_DIR))

# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────
with ui.card():
    ui.label('請輸入 CBETA 作業網址')
    url_input = ui.input('UV3 URL').style('width: 80vw;').props('clearable')

    links_area = ui.column().classes('gap-2 mt-2')

    def download_by_uv3():
        url = (url_input.value or '').strip()
        if not url:
            ui.notify('請輸入 UV3 URL', type='warning')
            return

        # 以唯一檔名輸出（避免併發衝突）
        filename = f'iiif_{uuid.uuid4().hex}.jpg'
        out_path = TMP_DIR / filename
        try:
            saved = download_image(uv3=url, out=str(out_path))
            if not Path(saved).exists():
                raise RuntimeError('檔案未成功寫入磁碟')

            public_url = f'/downloads/{filename}'
            ui.notify('下載完成', type='positive')

            with links_area:
                with ui.row().classes('items-center gap-2'):
                    ui.label('Download URL:')
                    ui.link(public_url, public_url, new_tab=True)

            # 若你想自動觸發下載，可開啟以下兩行
            # dl = ui.download(saved, filename=filename, hidden=True)
            # ui.run_javascript(f'document.getElementById("{dl.id}").click()')
        except Exception as e:
            ui.notify(f'下載失敗：{e}', type='negative')

    ui.button('從CBETA拿最高解析度圖片', on_click=download_by_uv3, color='primary')

# ──────────────────────────────────────────────────────────────────────────────
# 定時清理舊檔（> 1 小時）
# ──────────────────────────────────────────────────────────────────────────────
def cleanup_old_files():
    cutoff = time.time() - 3600
    try:
        for p in TMP_DIR.glob('iiif_*.jpg'):
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
    except Exception as e:
        print('Cleanup error:', e)

ui.timer(1800, cleanup_old_files)  # 每 30 分鐘清一次

# Render 預設會幫你配 HTTPS；此處 port/host 可依環境調整
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(host='0.0.0.0', port=int(os.getenv('PORT', '80')))
