import requests
from config import API_KEY, EXTRACTED_URLS_FILE, VIDEO_DATA_FILE


class VideoMetadataExtractor:

    def __init__(self, api_key, input_file):
        self.api_key = api_key
        self.input_file = input_file

        self.base_url = "https://www.googleapis.com/youtube/v3/videos"
        self.output_file = str(VIDEO_DATA_FILE)

    # ---------------- MAIN ----------------
    def run(self):
        urls = self._load_urls()
        video_ids = self._extract_video_ids(urls)

        all_videos = []

        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            batch_data = self._fetch_metadata(batch)
            all_videos.extend(batch_data)

        self._save(all_videos)

        print(f"Saved metadata for {len(all_videos)} videos → {self.output_file}")
        return all_videos

    # ---------------- FETCH FROM API ----------------
    def _fetch_metadata(self, video_ids):
        params = {
            "key": self.api_key,
            "id": ",".join(video_ids),
            "part": "snippet"
        }

        res = requests.get(self.base_url, params=params)
        data = res.json()

        results = []

        for item in data.get("items", []):
            snippet = item.get("snippet", {})

            title = snippet.get("title", "").strip()
            description = snippet.get("description", "").strip()

            # simple cleanup
            title = self._clean_text(title)
            description = self._clean_text(description)

            results.append({
                "title": title,
                "description": description
            })

        return results

    # ---------------- CLEANING ----------------
    def _clean_text(self, text):
        if not text:
            return ""

        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        text = " ".join(text.split())
        return text

    # ---------------- INPUT FILE ----------------
    def _load_urls(self):
        with open(self.input_file, "r") as f:
            return [line.strip() for line in f if line.strip()]

    def _extract_video_ids(self, urls):
        video_ids = []

        for url in urls:
            if "v=" in url:
                vid = url.split("v=")[1]

                # remove extra params like &t=123
                vid = vid.split("&")[0]

                video_ids.append(vid)

        return video_ids

    # ---------------- OUTPUT ----------------
    def _save(self, videos):
        with open(self.output_file, "w") as f:

            for i, v in enumerate(videos, 1):

                f.write(f"VIDEO {i}:\n")
                f.write(f"title: {v['title']}\n")
                f.write(f"description: {v['description']}\n\n")
