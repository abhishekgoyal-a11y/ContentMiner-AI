# ContentMiner AI

An automated pipeline that collects YouTube video URLs from configured channels into per-channel `videos.json`, with optional scripts to pull captions and frame OCR text.

## Project Structure

```
ContentMiner AI/
├── .env                        # API credentials (not committed to git)
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── config.py                   # Centralized configuration and paths
├── main.py                     # Pipeline entry point (Step 1)
├── pipeline/
│   ├── step1_collector.py      # Collects videos into data/raw/<channel_id>/videos.json
│   ├── step3_cleaner.py        # Legacy: cleans video_data.txt → video_data_cleaned.txt (if you create that input)
│   ├── fetch_transcripts.py    # Fills video_transcript_file from YouTube captions
│   └── fetch_video_images_ocr.py  # Fills video_images_content via yt-dlp + ffmpeg + Tesseract
└── data/
    ├── input/
    ├── raw/
    └── output/
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

**Step 1 (collect):**
```bash
python main.py
```

**Optional — transcripts / OCR** (see script docstrings; need extra system tools for OCR):
```bash
python pipeline/fetch_transcripts.py
python pipeline/fetch_video_images_ocr.py
```

## Output

- **`data/raw/<channel_id>/videos.json`** — video URL, title, placeholders / filled transcript and OCR fields
- **`data/output/video_data_cleaned.txt`** — only if you run `step3_cleaner.py` with a suitable `data/raw/video_data.txt` input

## Configuration

Paths and env loading are in `config.py`.

## Notes

- Processed URLs are tracked in `data/raw/processed_urls.txt`
- Data directories are created on first run
