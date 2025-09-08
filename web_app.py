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


def download_by_params():
    try:
        path = download_image(
            uv3=None,
            canon=canon_input.value,
            volume=int(volume_input.value),
            canvas=int(canvas_input.value),
        )
        ui.notify(f'Saved to {path}')
        if Path(path).exists():
            ui.image(path)
    except Exception as e:
        ui.notify(str(e), color='negative')


with ui.card():
    ui.label('Download by UV3 URL')
    url_input = ui.input('UV3 URL')
    ui.button('Download', on_click=download_by_uv3)

with ui.card():
    ui.label('Download by Canon/Volume/Canvas')
    canon_input = ui.input('Canon', value='T')
    volume_input = ui.input('Volume', value='1')
    canvas_input = ui.input('Canvas', value='0')
    ui.button('Download', on_click=download_by_params)

ui.run()
