# genie-vid2pdf

會議/課程錄屏 → PDF:畫面變化偵測截圖 + 語音字幕燒錄,每個場景一組頁面。

## 需求

- macOS(Apple Silicon 建議)+ `ffmpeg`
- genie-core(`[mlx]` extra 供語音轉文字)
- 不需要 LLM

## 用法

```bash
genie-vid2pdf recording.mp4                      # 輸出 recording.pdf
genie-vid2pdf recording.mp4 -o out.pdf \
    --interval 30 --threshold 0.3 --language zh
```

| 參數 | 預設 | 說明 |
|---|---|---|
| `input` | — | 影片檔(.mp4/.mov) |
| `-o, --output` | `<input>.pdf` | 輸出 PDF 路徑 |
| `--interval` | 30 | 定時截圖間隔(秒);場景偵測之外的保底截圖 |
| `--threshold` | 0.3 | 場景變化敏感度 0-1,越小越敏感(頁數越多) |
| `--language` | zh | whisper 語言碼 |

## 行為說明

- 每個場景收集該時段全部語音;字幕超過 2 行 × 30 字自動拆頁(同畫面複用)
- 跨場景邊界的語音段以**中點**歸屬單一場景(不重複)
- 已有 transcript 時可跳過 whisper:程式介面 `video_to_pdf(..., transcript_path="xx.json")` 支援 .json / .srt
- 零場景或全部截圖失敗會**報錯退出**,不會靜默產出空 PDF

## 已知坑

- 長影片記憶體佔用已優化(截圖以 generator 逐張餵入 PDF),數百頁無壓力
- 字幕含特殊字元(`%{}`、引號)已透過 ffmpeg `textfile=` 處理,無需轉義
