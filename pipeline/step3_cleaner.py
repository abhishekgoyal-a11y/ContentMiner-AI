import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RAW_DIR  # noqa: E402


class VideoDataCleaner:
    """
    Walk data/raw/**/*.json (video lists). Cleans string fields in place:

    - video_transcript_file: normalize Unicode, strip controls, remove URLs / loose
      hashtags, collapse whitespace to a single flowing line.
    - video_images_content: OCR-oriented — segment long symbol blobs (pipes, long
      spaces), drop low-signal chunks, keep word-like lines, dedupe repeats.

    Saves each JSON file when any field in that file changes.
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

    def _strip_format_and_controls(self, text: str, *, keep_newlines: bool) -> str:
        """Remove Cf (format) and most Cc; keep newlines/tabs when keep_newlines."""
        out: list[str] = []
        for c in text:
            cat = unicodedata.category(c)
            if cat == "Cf":
                continue
            if cat == "Cc":
                if keep_newlines and c in "\n\r\t":
                    out.append("\n" if c == "\r" else c)
                elif not keep_newlines and c in "\n\r\t":
                    out.append(" ")
                continue
            out.append(c)
        return "".join(out)

    def _clean_transcript(self, text: str) -> str:
        if not text:
            return ""

        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\ufeff", "")
        text = self._strip_format_and_controls(text, keep_newlines=False)
        text = re.sub(r"https?://[^\s\])}>\"']+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"(?<![\w#])#(?:[\w_]\w*)", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _ocr_line_keeps_signal(self, line: str) -> bool:
        """Keep OCR segments that look like real words, not symbol soup."""
        line = line.strip()
        if len(line) < 4:
            return False

        letters = sum(1 for c in line if c.isalpha())
        if letters < 4:
            return False

        n = len(line)
        ratio = letters / n

        # Punctuation / symbols / odd marks (not alnum, not whitespace, not '-')
        non_body = sum(
            1 for c in line if not (c.isalnum() or c.isspace() or c in "'-")
        )
        noise_ratio = non_body / max(n, 1)

        latin_runs = re.findall(r"[A-Za-z]{4,}", line)
        run_letters = sum(len(w) for w in latin_runs)
        run_cov = run_letters / max(n, 1)

        # Long lines that are mostly decoration / OCR artefacts
        if n >= 120 and noise_ratio > 0.42:
            return False
        if n >= 80 and noise_ratio > 0.48 and run_cov < 0.26:
            return False

        # Substantive Latin tokens with tolerable noise
        if latin_runs and ratio >= 0.14 and noise_ratio <= 0.45:
            if run_cov >= 0.14 or len(latin_runs) >= 2 or run_letters >= 16:
                return True

        # Non-Latin script (e.g. Hindi) with reasonable body vs noise
        if re.search(r"[^\W\d_]{4,}", line) and noise_ratio <= 0.5:
            if ratio >= 0.18 or (letters >= 12 and ratio >= 0.14):
                return True

        # Cleaner long lines (titles) without many isolated symbols
        if letters >= 14 and ratio >= 0.28 and noise_ratio <= 0.38:
            return True

        return False

    def _segment_ocr_lines(self, text: str) -> list[str]:
        """
        OCR often returns one huge line of symbols. Break on |, long spaces, and
        newlines so per-line filters can drop garbage.
        """
        t = text.replace("\r\n", "\n").replace("\r", "\n")
        t = re.sub(r"\s*\|\s*", "\n", t)
        t = re.sub(r"\s{4,}", "\n", t)
        t = re.sub(r"\s*\.\s*\.\s*\.\s*", "\n", t)
        lines: list[str] = []
        for block in t.split("\n"):
            b = block.strip()
            if not b:
                continue
            if len(b) > 500:
                for i in range(0, len(b), 400):
                    chunk = b[i : i + 400].strip()
                    if chunk:
                        lines.append(chunk)
            else:
                lines.append(b)
        return lines

    def _shrink_ocr_line(self, line: str) -> str:
        """
        Long OCR rows are often one slide bitmap read as letters + symbols. Keep
        stable word-like tokens to shrink noise while preserving searchable text.
        """
        if len(line) <= 64:
            return line
        latin = re.findall(r"[A-Za-z]{4,}", line)
        deva = re.findall(r"[\u0900-\u097F]{2,}", line)
        toks = latin + deva
        if not toks:
            return line
        seen: set[str] = set()
        uniq: list[str] = []
        for t in toks:
            key = t.casefold()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(t)
        compact = " ".join(uniq)
        return compact if len(compact) >= 10 else line

    def _ocr_line_signature(self, line: str) -> str:
        """Rough fingerprint to drop near-duplicate slide OCR repeats."""
        s = re.sub(r"[^a-z0-9\u0900-\u097F]+", "", line.casefold())
        return s[:56]

    def _clean_ocr_text(self, text: str) -> str:
        if not text:
            return ""

        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\ufeff", "")
        text = self._strip_format_and_controls(text, keep_newlines=True)
        text = re.sub(r"https?://[^\s\])}>\"']+", "", text, flags=re.IGNORECASE)

        kept: list[str] = []
        prev_sig = ""
        for raw_line in self._segment_ocr_lines(text):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            line = re.sub(r"([.°*•])\1{3,}", r"\1\1", line)
            if not self._ocr_line_keeps_signal(line):
                continue
            line = self._shrink_ocr_line(line)
            if not line:
                continue
            sig = self._ocr_line_signature(line)
            if sig and sig == prev_sig:
                continue
            if kept and kept[-1] == line:
                continue
            kept.append(line)
            prev_sig = sig

        return "\n".join(kept).strip()

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
                cleaned_t = self._clean_transcript(raw_t)
                if cleaned_t != raw_t:
                    row["video_transcript_file"] = cleaned_t
                    changed = True
                    rows_updated += 1

            raw_i = row.get("video_images_content")
            if isinstance(raw_i, str):
                cleaned_i = self._clean_ocr_text(raw_i)
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
