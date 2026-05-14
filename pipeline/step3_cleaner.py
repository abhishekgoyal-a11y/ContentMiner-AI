import json
import re
from pathlib import Path

from config import RAW_DIR


class VideoDataCleaner:
    """
    Walk data/raw/**/*.json (video lists). For each row, if video_transcript_file or
    video_images_content is a non-null string, normalize it (strip URLs/hashtags/extra
    whitespace). Cleaned values are written back as-is (including empty string).
    Saves the same JSON file in place when any row in that file changes.
    """

    def __init__(self, collections_root=None):
        self.collections_root = Path(collections_root or RAW_DIR)

    def run(self):
        paths = self._discover_videos_json_files()
        if not paths:
            print(f"No video-list JSON files under {self.collections_root}")
            return

        files_changed = 0
        rows_changed = 0

        for json_path in paths:
            n, changed = self._clean_file(json_path)
            rows_changed += n
            if changed:
                files_changed += 1

        print(
            f"\n✅ Cleaned transcript / images text on {rows_changed} field update(s) "
            f"across {files_changed} JSON file(s) under {self.collections_root}"
        )

    def _discover_videos_json_files(self) -> list[Path]:
        out: list[Path] = []
        for p in sorted(self.collections_root.rglob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, list):
                continue
            if any(isinstance(x, dict) and x.get("video_url") for x in data):
                out.append(p)
        return out

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace("\ufeff", "")
        text = re.sub(r"http\S+", "", text)
        text = re.sub(r"#\w+", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _clean_file(self, json_path: Path) -> tuple[int, bool]:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"Skip {json_path}: {e}")
            return 0, False

        if not isinstance(data, list):
            return 0, False

        changed = False
        rows_updated = 0

        for row in data:
            if not isinstance(row, dict):
                continue

            raw_t = row.get("video_transcript_file")
            if isinstance(raw_t, str):
                cleaned_t = self._clean_text(raw_t)
                if cleaned_t != raw_t:
                    row["video_transcript_file"] = cleaned_t
                    changed = True
                    rows_updated += 1

            raw_i = row.get("video_images_content")
            if isinstance(raw_i, str):
                cleaned_i = self._clean_text(raw_i)
                if cleaned_i != raw_i:
                    row["video_images_content"] = cleaned_i
                    changed = True
                    rows_updated += 1

        if changed:
            json_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"  wrote {json_path}")

        return rows_updated, changed


if __name__ == "__main__":
    VideoDataCleaner().run()
