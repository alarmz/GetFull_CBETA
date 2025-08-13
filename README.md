# GetFull_CBETA
使用方法
A. 直接貼 uv3 網址（你給的那種）
python download_dila_iiif_max.py --uv3 "https://dia.dila.edu.tw/uv3/index.html?id=Tv01p0300#?c=0&m=0&s=0&cv=309"

B. 手動指定典籍 / 冊數 / 頁索引
python download_dila_iiif_max.py --canon T --volume 1 --canvas 309 -o page309_max.jpg

必要套件
pip install requests pillow

檢查你是否真的拿到最大解析度

執行腳本時，會先印出 intrinsic size: WxH（來自 info.json）。

直連成功後，我會開啟實際下載的 JPG 比對寬度；若寬度 < intrinsic，就自動改成拼圖拿滿分辨率。

最終輸出就是與 info.json 的 width×height 一致的最大尺寸。

如果你用這個新版腳本跑 cv=309 仍然覺得不夠大，回我一行 console 輸出（含 intrinsic size 與 saved direct/stitched 那幾行），我幫你針對該頁做更精細的調整（例如改用特定 scaleFactor、或偵測多個 service @id 時選擇高解析那個）。
