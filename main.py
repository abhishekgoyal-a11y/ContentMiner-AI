from pipeline.step1_collector import VideoCollector
from pipeline.step2_metadata_extractor import VideoMetadataExtractor
from pipeline.step3_cleaner import VideoDataCleaner
from config import API_KEY, CHANNELS_FILE, RAW_DIR, VIDEO_DATA_FILE, VIDEO_DATA_CLEANED_FILE


def run_pipeline():

    # ---------------- STEP 1 ----------------
    print("\n🚀 Running Step 1: Collect URLs")
    collector = VideoCollector(
        api_key=API_KEY,
        channel_file=str(CHANNELS_FILE)
    )

    collector.collect_urls()

    # # ---------------- STEP 2 ----------------
    # print("\n🚀 Running Step 2: Fetch Metadata")
    # extractor = VideoMetadataExtractor(
    #     api_key=API_KEY,
    #     collections_root=str(RAW_DIR),
    # )

    # extractor.run()

    # # ---------------- STEP 3 ----------------
    # print("\n🚀 Running Step 3: Clean Data")
    # cleaner = VideoDataCleaner(
    #     input_file=VIDEO_DATA_FILE,
    #     output_file=VIDEO_DATA_CLEANED_FILE
    # )

    # cleaner.run()


if __name__ == "__main__":
    run_pipeline()
