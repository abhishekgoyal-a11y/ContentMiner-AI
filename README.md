# ContentMiner AI

An automated pipeline that collects YouTube video URLs from configured channels into per-channel `videos.json`, with optional scripts to pull captions and frame OCR text.

## Project Structure

```
ContentMiner AI/
├── .env                        # API credentials (not committed to git)
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── config.py                   # Centralized configuration and paths
├── main.py                     # Pipeline entry point (Step 1 + Step 3)
├── pipeline/
│   ├── step1_collector.py      # Collects videos into data/raw/<channel_id>/videos.json
│   ├── step3_cleaner.py        # Cleans video_transcript_file & video_images_content in videos.json
│   ├── fetch_transcripts.py    # Fills video_transcript_file via yt-dlp audio + faster-whisper
│   └── fetch_video_images_ocr.py  # Fills video_images_content via yt-dlp + ffmpeg + Tesseract
└── data/
    ├── input/
    └── raw/
```

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API key:**
   - The `.env` file should define `YOUTUBE_API_KEY` for Step 1 (YouTube Data API)
   - Keep `.env` private and never commit it to git

3. **Add YouTube channels:**
   - Edit `data/input/channels.txt` — one channel URL per line

## Running

**Pipeline (`main.py`)** — Step 1 (collect) then Step 3 (clean transcript + OCR text fields in `videos.json`):
```bash
python main.py
```

**Optional — transcripts / OCR** (see script docstrings; need extra system tools for OCR):
```bash
python pipeline/fetch_transcripts.py
python pipeline/fetch_video_images_ocr.py
```

Run **`fetch_transcripts.py`** / **`fetch_video_images_ocr.py`** before **`main.py`** Step 3 if you want those fields cleaned; Step 3 only updates string fields that exist (it skips `null` values).

## Output

- **`data/raw/<channel_id>/videos.json`** — Step 1 fills rows; optional fetch scripts fill transcript/OCR; Step 3 rewrites `video_transcript_file` / `video_images_content` in place when they change after cleaning

## Configuration

Paths and env loading are in `config.py`.

## Notes

- Processed URLs are tracked in `data/raw/processed_urls.txt`
- Data directories are created on first run
