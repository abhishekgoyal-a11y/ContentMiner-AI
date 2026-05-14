from pipeline.step1_collector import VideoCollector
from config import API_KEY, CHANNELS_FILE


def run_pipeline():

    # ---------------- STEP 1 ----------------
    print("\n🚀 Running Step 1: Collect URLs")
    collector = VideoCollector(
        api_key=API_KEY,
        channel_file=str(CHANNELS_FILE)
    )

    collector.collect_urls()


if __name__ == "__main__":
    run_pipeline()
