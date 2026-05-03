import requests
import re
from config import API_KEY, CHANNELS_FILE, PROCESSED_URLS_FILE, EXTRACTED_URLS_FILE


class VideoCollector:

    def __init__(self, api_key, channel_file):
        self.api_key = api_key
        self.channel_file = channel_file

        self.base_channel_url = "https://www.googleapis.com/youtube/v3/channels"
        self.base_playlist_url = "https://www.googleapis.com/youtube/v3/playlistItems"
        self.base_video_url = "https://www.googleapis.com/youtube/v3/videos"

        self.output_file = str(EXTRACTED_URLS_FILE)
        self.processed_file = str(PROCESSED_URLS_FILE)

    # ---------------- PUBLIC METHOD ----------------
    def collect_urls(self):
        channel_ids = self._get_channel_ids()
        processed_urls = self._load_processed_urls()

        all_new_urls = []

        for channel_id in channel_ids:

            uploads_playlist = self._get_uploads_playlist(channel_id)
            video_ids = self._get_video_ids_from_playlist(uploads_playlist)

            long_videos = self._filter_by_duration(video_ids)

            final_videos = []

            for vid in long_videos:
                url = f"https://www.youtube.com/watch?v={vid}"

                if url in processed_urls:
                    continue

                final_videos.append(url)

                if len(final_videos) >= 30:
                    break

            print(f"{channel_id}: {len(final_videos)} videos (>=2min, new)")

            all_new_urls.extend(final_videos)

        self._save_urls(all_new_urls)
        self._save_processed_urls(all_new_urls)

        print(f"\nSaved {len(all_new_urls)} URLs to {self.output_file}")
        return all_new_urls

    # ---------------- CHANNEL HANDLING ----------------
    def _get_channel_ids(self):
        channel_ids = []

        with open(self.channel_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]

        for url in urls:

            if "/channel/" in url:
                channel_ids.append(url.split("/channel/")[1])

            elif "/@" in url:
                handle = url.split("/@")[1]
                channel_id = self._resolve_handle(handle)

                if channel_id:
                    channel_ids.append(channel_id)

        return channel_ids

    def _resolve_handle(self, handle):
        params = {
            "key": self.api_key,
            "forHandle": handle,
            "part": "id"
        }

        res = requests.get(self.base_channel_url, params=params)
        data = res.json()

        items = data.get("items", [])
        if items:
            return items[0]["id"]

        return None

    # ---------------- PLAYLIST ----------------
    def _get_uploads_playlist(self, channel_id):
        params = {
            "key": self.api_key,
            "id": channel_id,
            "part": "contentDetails"
        }

        res = requests.get(self.base_channel_url, params=params)
        data = res.json()

        return data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def _get_video_ids_from_playlist(self, playlist_id):
        video_ids = []
        page_token = None

        while True:

            params = {
                "key": self.api_key,
                "playlistId": playlist_id,
                "part": "snippet",
                "maxResults": 50,
                "pageToken": page_token
            }

            res = requests.get(self.base_playlist_url, params=params)
            data = res.json()

            for item in data.get("items", []):
                video_id = item["snippet"]["resourceId"]["videoId"]
                video_ids.append(video_id)

            page_token = data.get("nextPageToken")

            if not page_token:
                break

        return video_ids

    # ---------------- DURATION FILTER ----------------
    def _filter_by_duration(self, video_ids):
        valid_videos = []

        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]

            params = {
                "key": self.api_key,
                "id": ",".join(batch),
                "part": "contentDetails"
            }

            res = requests.get(self.base_video_url, params=params)
            data = res.json()

            for item in data.get("items", []):
                vid = item["id"]
                duration = item["contentDetails"]["duration"]

                seconds = self._parse_duration(duration)

                if seconds >= 120:
                    valid_videos.append(vid)

        return valid_videos

    # ---------------- DURATION PARSER ----------------
    def _parse_duration(self, duration):
        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(duration)

        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    # ---------------- FILE HANDLING ----------------
    def _load_processed_urls(self):
        try:
            with open(self.processed_file, "r") as f:
                return set(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            return set()

    def _save_urls(self, urls):
        with open(self.output_file, "w") as f:
            for url in urls:
                f.write(url + "\n")

    def _save_processed_urls(self, urls):
        with open(self.processed_file, "a") as f:
            for url in urls:
                f.write(url + "\n")
