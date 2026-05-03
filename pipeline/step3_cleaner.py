import re
import os
from config import VIDEO_DATA_FILE, VIDEO_DATA_CLEANED_FILE


class VideoDataCleaner:

    def __init__(self, input_file, output_file):
        self.input_file = str(input_file)
        self.output_file = str(output_file)

    # ---------------- MAIN ----------------
    def run(self):
        videos = self._load_and_parse()

        cleaned_videos = []

        for v in videos:
            title = self._clean_text(v.get("title", ""))
            description = self._clean_text(v.get("description", ""))

            if title and description:
                cleaned_videos.append({
                    "title": title,
                    "description": description
                })

        self._write_output(cleaned_videos)

        print(f"\n✅ Cleaned {len(cleaned_videos)} videos → {self.output_file}")

        # ---------------- DELETE INPUT FILE ----------------
        if os.path.exists(self.input_file):
            os.remove(self.input_file)
            print(f"🗑️ Deleted original file: {self.input_file}")
        else:
            print(f"⚠️ Input file not found: {self.input_file}")

    # ---------------- LOAD FILE ----------------
    def _load_and_parse(self):
        with open(self.input_file, "r", encoding="utf-8") as f:
            content = f.read()

        videos = []

        blocks = content.split("VIDEO ")

        for block in blocks:
            if not block.strip():
                continue

            title = self._extract(block, "title")
            description = self._extract(block, "description")

            if title or description:
                videos.append({
                    "title": title,
                    "description": description
                })

        return videos

    # ---------------- EXTRACT FIELD ----------------
    def _extract(self, text, field):
        match = re.search(rf"{field}:\s*(.*?)(\n|$)", text)
        return match.group(1).strip() if match else ""

    # ---------------- CLEAN TEXT ----------------
    def _clean_text(self, text):
        if not text:
            return ""

        text = re.sub(r"http\S+", "", text)   # remove URLs
        text = re.sub(r"#\w+", "", text)      # remove hashtags
        text = re.sub(r"\s+", " ", text)      # normalize spaces
        return text.strip()

    # ---------------- WRITE OUTPUT ----------------
    def _write_output(self, videos):
        with open(self.output_file, "w", encoding="utf-8") as f:
            for i, v in enumerate(videos, 1):
                f.write(f"VIDEO {i}:\n")
                f.write(f"title: {v['title']}\n")
                f.write(f"description: {v['description']}\n\n")
