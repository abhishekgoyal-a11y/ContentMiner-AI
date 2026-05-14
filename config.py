import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = DATA_DIR / "output"

for dir_path in [INPUT_DIR, RAW_DIR, OUTPUT_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

CHANNELS_FILE = INPUT_DIR / "channels.txt"
CHANNEL_VIDEOS_JSON_NAME = "videos.json"
