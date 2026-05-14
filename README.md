# ContentMiner AI

An automated pipeline that collects YouTube video URLs from configured channels, fetches metadata, and produces cleaned text for downstream use.

## Project Structure

```
ContentMiner AI/
├── .env                        # API credentials (not committed to git)
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── config.py                   # Centralized configuration and paths
├── main.py                     # Pipeline entry point
├── pipeline/                   # Core pipeline steps
│   ├── step1_collector.py      # Collects URLs from YouTube channels
│   ├── step2_metadata_extractor.py  # Fetches video metadata
│   └── step3_cleaner.py        # Cleans and normalizes data
└── data/                       # Data files (ignored by git)
    ├── input/                  # Input data (YouTube channels)
    ├── raw/                    # Intermediate processing files
    └── output/                 # Final outputs
```

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API key:**
   - The `.env` file is already set up with your YouTube API key
   - Keep `.env` private and never commit it to git

3. **Add YouTube channels:**
   - Edit `data/input/channels.txt` to add YouTube channel URLs
   - Format: one URL per line (e.g., `https://www.youtube.com/@ChannelName`)

## Running the Pipeline

```bash
python main.py
```

The pipeline will:
1. **Step 1**: Collect long-form videos (≥2min) from specified channels
2. **Step 2**: Extract video metadata (title, description)
3. **Step 3**: Clean and normalize the data

## Output

Results are saved under `data/raw/` and `data/output/` as configured in `config.py`. The cleaned dataset is written to `data/output/video_data_cleaned.txt`.

## Configuration

All file paths and settings are centralized in `config.py`. You can modify:
- File paths (data directories)
- API credentials (via `.env`)

## Notes

- The pipeline creates data directories automatically on first run
