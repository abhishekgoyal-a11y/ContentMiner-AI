import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

BASE_DIR = Path(__file__).parent

DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = DATA_DIR / "output"

for dir_path in [INPUT_DIR, RAW_DIR, OUTPUT_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

CHANNELS_FILE = INPUT_DIR / "channels.txt"
PROCESSED_URLS_FILE = RAW_DIR / "processed_urls.txt"
EXTRACTED_URLS_FILE = RAW_DIR / "youtube_extracted_videos_urls.txt"
VIDEO_DATA_FILE = RAW_DIR / "video_data.txt"
VIDEO_DATA_CLEANED_FILE = OUTPUT_DIR / "video_data_cleaned.txt"
TOPICS_RAW_FILE = OUTPUT_DIR / "topics_raw.txt"
TOPICS_RANKED_FILE = OUTPUT_DIR / "topics_ranked.txt"

PROMPT_TOPIC_FILE = BASE_DIR / "prompts" / "step4_topic_generator.txt"
PROMPT_RANK_FILE = BASE_DIR / "prompts" / "step5_rank_topics.txt"
