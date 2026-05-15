import json
import sys
import requests
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (  # noqa: E402
    API_KEY,
    CHANNELS_FILE,
    CHANNEL_VIDEOS_JSON_NAME,
    RAW_DIR,
)


class VideoCollector:

    def __init__(self, api_key, channel_file):
        self.api_key = api_key
        self.channel_file = channel_file

        self.base_channel_url = "https://www.googleapis.com/youtube/v3/channels"
        self.base_playlist_url = "https://www.googleapis.com/youtube/v3/playlistItems"
        self.base_video_url = "https://www.googleapis.com/youtube/v3/videos"

    # ---------------- PUBLIC METHOD ----------------
    def collect_urls(self):
        channel_ids = self._get_channel_ids()

        all_new_urls = []
        total_appended = 0

        for channel_id in channel_ids:

            channel_dir = Path(RAW_DIR) / channel_id
            channel_dir.mkdir(parents=True, exist_ok=True)

            videos_path = channel_dir / CHANNEL_VIDEOS_JSON_NAME
            if not videos_path.exists():
                videos_path.write_text("[]", encoding="utf-8")

            uploads_playlist = self._get_uploads_playlist(channel_id)
            video_ids = self._get_video_ids_from_playlist(uploads_playlist)

            long_videos = self._long_videos_with_titles(video_ids)

            new_entries = []

            for vid, title in long_videos:
                url = f"https://www.youtube.com/watch?v={vid}"

                new_entries.append({
                    "video_url": url,
                    "video_title": title,
                    "video_transcript_file": None,
                    "video_images_content": None,
                    "article_written": None,
                })

            print(f"{channel_id}: {len(new_entries)} videos (>=2min)")

            if new_entries:
                total_appended += self._append_new_entries_to_videos_json(
                    channel_id, new_entries
                )

            all_new_urls.extend(e["video_url"] for e in new_entries)

        print(
            f"\nAppended {total_appended} new video records "
            f"({len(all_new_urls)} long videos scanned) under {RAW_DIR}"
        )
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

    # ---------------- DURATION FILTER + TITLES ----------------
    def _long_videos_with_titles(self, video_ids):
        results = []

        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]

            params = {
                "key": self.api_key,
                "id": ",".join(batch),
                "part": "snippet,contentDetails"
            }

            res = requests.get(self.base_video_url, params=params)
            data = res.json()

            for item in data.get("items", []):
                vid = item["id"]
                duration = item["contentDetails"]["duration"]

                seconds = self._parse_duration(duration)

                if seconds >= 120:
                    title = item.get("snippet", {}).get("title", "").strip()
                    results.append((vid, title))

        return results

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
    def _append_new_entries_to_videos_json(self, channel_id, new_entries):
        """
        RAW_DIR/<channel_id>/ exists before this is called.
        If videos.json is missing, create it. If it exists, load current
        array and append only rows with new video_url; never remove or
        rewrite existing objects.
        """
        channel_dir = Path(RAW_DIR) / channel_id
        out_path = channel_dir / CHANNEL_VIDEOS_JSON_NAME

        existing = []
        if out_path.exists():
            try:
                raw = json.loads(out_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    existing = [row for row in raw if isinstance(row, dict)]
            except json.JSONDecodeError:
                existing = []

        seen = {
            row["video_url"]
            for row in existing
            if row.get("video_url")
        }

        appended = 0
        for row in new_entries:
            url = row["video_url"]
            if url not in seen:
                seen.add(url)
                existing.append(row)
                appended += 1

        out_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"  → {out_path}")
        return appended


if __name__ == "__main__":
    VideoCollector(API_KEY, CHANNELS_FILE).collect_urls()
