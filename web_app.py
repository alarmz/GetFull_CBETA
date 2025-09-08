from pathlib import Path
from nicegui import ui
from download_dila_iiif_max import download_image


def download_by_uv3():
    try:
        path = download_image(uv3=url_input.value)
        ui.notify(f'Saved to {path}')
        if Path(path).exists():
            ui.image(path)
    except Exception as e:
        ui.notify(str(e), color='negative')


with ui.card():
    ui.label('Download by UV3 URL')
    url_input = ui.input('UV3 URL')
    ui.button('Download', on_click=download_by_uv3)

ui.run()
