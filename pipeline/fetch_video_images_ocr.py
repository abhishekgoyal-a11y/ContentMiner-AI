#!/usr/bin/env python3
"""
For each row in data/raw/**/*.json (video lists) where video_images_content is null,
run the same pipeline as YoutubeScraper/video_images_ocr.py:
  yt-dlp download → ffmpeg 1 fps frames → Tesseract OCR → combined text.

Stores the OCR text in video_images_content and saves that JSON file after each success.

Post-success pacing (random 1–5s + 30s every 30 videos) is disabled for now; see commented
blocks near the end of main().

Requires on PATH: yt-dlp, ffmpeg, tesseract (e.g. brew install tesseract).
Python deps: pillow, pytesseract, tqdm (see requirements.txt).

yt-dlp is always invoked with --no-check-certificates (matches relaxed TLS elsewhere).

Run from project root:
  python pipeline/fetch_video_images_ocr.py
  python pipeline/fetch_video_images_ocr.py --limit 1 --fps 0.5 --ocr-lang eng+hin
"""

from __future__ import annotations

import argparse
import json
# import random  # post-success pacing (disabled)
import re
import shutil
import subprocess
import sys
import tempfile
# import time  # post-success pacing (disabled)
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Project imports when run as `python pipeline/fetch_video_images_ocr.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RAW_DIR  # noqa: E402

# Post-success pacing (disabled for now)
# MIN_DELAY_SEC = 1.0
# MAX_DELAY_SEC = 5.0
# BATCH_SIZE = 30
# BATCH_PAUSE_SEC = 30.0


def extract_video_id(url_or_id: str) -> str:
    s = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s

    parsed = urlparse(s)
    host = (parsed.hostname or "").lower()

    if host in ("youtu.be", "www.youtu.be"):
        path = parsed.path.strip("/")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", path):
            return path

    if host.endswith("youtube.com") or host == "youtube-nocookie.com":
        if parsed.path == "/watch":
            v = parse_qs(parsed.query).get("v", [None])[0]
            if v and re.fullmatch(r"[A-Za-z0-9_-]{11}", v):
                return v
        m = re.match(r"^/embed/([A-Za-z0-9_-]{11})", parsed.path)
        if m:
            return m.group(1)
        m = re.match(r"^/shorts/([A-Za-z0-9_-]{11})", parsed.path)
        if m:
            return m.group(1)

    raise ValueError(f"Could not parse YouTube video id from: {url_or_id!r}")


def require_cmd(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Missing `{name}` on PATH. Install it and retry.")
    return path


def download_video(url: str, out_dir: Path) -> Path:
    """Download best merged video as _source.* (yt-dlp TLS check disabled)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / "_source.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-check-certificates",
        "--no-playlist",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        template,
        url,
    ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed with exit code {r.returncode}")

    for ext in (".mp4", ".webm", ".mkv", ".mov", ".m4v"):
        p = out_dir / f"_source{ext}"
        if p.is_file():
            return p

    matches = sorted(out_dir.glob("_source.*"))
    for p in matches:
        if p.suffix.lower() not in (".part", ".ytdl"):
            return p

    raise RuntimeError("yt-dlp finished but no _source video file was found.")


def extract_frames_per_second(video_path: Path, frames_dir: Path, *, fps: float) -> None:
    for old in frames_dir.glob("frame_*.jpg"):
        try:
            old.unlink()
        except OSError:
            pass
    pattern = str(frames_dir / "frame_%05d.jpg")
    vf = f"fps={fps},scale=min(iw\\,1920):-2"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        vf,
        "-q:v",
        "3",
        pattern,
    ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {r.returncode}")


def ocr_image(path: Path, *, lang: str) -> str:
    from PIL import Image
    import pytesseract

    img = Image.open(path)
    text = pytesseract.image_to_string(
        img,
        lang=lang,
        config="--psm 6",
    )
    return " ".join(text.split()).strip()


def run_ocr_on_frames(frames_dir: Path, *, lang: str) -> str:
    import pytesseract
    from tqdm import tqdm

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError("No frame_*.jpg files found after ffmpeg.")

    lines: list[str] = []
    for frame in tqdm(frames, desc="OCR", unit="frame", file=sys.stderr):
        try:
            txt = ocr_image(frame, lang=lang)
        except pytesseract.TesseractNotFoundError as e:
            raise RuntimeError(
                "Tesseract is not installed or not on PATH. macOS: brew install tesseract"
            ) from e
        except Exception as e:
            txt = f"<OCR error: {e}>"

        txt = txt.strip()
        if txt:
            lines.append(txt)

    return "\n".join(lines) + ("\n" if lines else "")


def discover_videos_json_files() -> list[Path]:
    out: list[Path] = []
    for p in sorted(RAW_DIR.rglob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, list):
            continue
        if any(isinstance(x, dict) and x.get("video_url") for x in data):
            out.append(p)
    return out


def needs_images_content(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    if not row.get("video_url"):
        return False
    return row.get("video_images_content") is None


def run_ocr_pipeline(url: str, *, fps: float, ocr_lang: str) -> str:
    """Download, frame, OCR in a temp directory; returns combined OCR text."""
    with tempfile.TemporaryDirectory(prefix="ytocr_") as tmp:
        work = Path(tmp)
        video_path = download_video(url.strip(), work)
        extract_frames_per_second(video_path, work, fps=fps)
        return run_ocr_on_frames(work, lang=ocr_lang)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill video_images_content via yt-dlp + ffmpeg + Tesseract (see YoutubeScraper/video_images_ocr.py)"
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=1.0,
        metavar="N",
        help="Frames per second to extract with ffmpeg (default: 1)",
    )
    parser.add_argument(
        "--ocr-lang",
        default="eng",
        metavar="LANG",
        help="Tesseract language(s), e.g. eng or eng+hin (default: eng)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Process at most N rows still missing video_images_content (attempts, 0 = no limit)",
    )
    args = parser.parse_args()

    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        import tqdm  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "Install OCR dependencies: pip install pillow pytesseract tqdm"
        ) from e

    require_cmd("yt-dlp")
    require_cmd("ffmpeg")

    paths = discover_videos_json_files()
    if not paths:
        print(f"No usable video-list JSON files under {RAW_DIR}", file=sys.stderr)
        raise SystemExit(1)

    done = 0
    failed = 0
    stop = False
    attempted = 0

    for json_path in paths:
        if stop:
            break
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"Skip unreadable JSON {json_path}: {e}", file=sys.stderr)
            continue

        if not isinstance(data, list):
            print(f"Skip {json_path}: root JSON is not a list", file=sys.stderr)
            continue

        for row in data:
            if not needs_images_content(row):
                continue
            if args.limit and attempted >= args.limit:
                stop = True
                break
            attempted += 1

            url = row["video_url"]
            try:
                video_id = extract_video_id(url)
            except ValueError as e:
                print(f"  Bad URL {url!r}: {e}", file=sys.stderr)
                failed += 1
                continue

            print(f"OCR pipeline: {video_id} ← {url}", flush=True)
            try:
                combined = run_ocr_pipeline(
                    url, fps=args.fps, ocr_lang=args.ocr_lang
                )
            except RuntimeError as e:
                print(f"  {video_id}: {e}", file=sys.stderr)
                failed += 1
                continue
            except Exception as e:
                print(f"  {video_id}: {type(e).__name__}: {e}", file=sys.stderr)
                failed += 1
                continue

            ocr_text = combined.strip()
            images_ocr_dir = json_path.parent / "images_ocr"
            images_ocr_dir.mkdir(parents=True, exist_ok=True)
            ocr_path = images_ocr_dir / f"{video_id}.txt"
            ocr_path.write_text(ocr_text, encoding="utf-8")

            row["video_images_content"] = f"images_ocr/{video_id}.txt"
            done += 1
            n = len(ocr_text)
            json_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"OK {video_id} → wrote {ocr_path} ({n} chars), saved {json_path}")

            # --- post-success pacing (disabled for now) ---
            # gap = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
            # time.sleep(gap)
            # print(f"  waited {gap:.1f}s (random {MIN_DELAY_SEC:.0f}–{MAX_DELAY_SEC:.0f}s)", flush=True)
            #
            # if done % BATCH_SIZE == 0:
            #     print(
            #         f"  batch pause {BATCH_PAUSE_SEC:.0f}s after {done} successful OCR run(s)",
            #         flush=True,
            #     )
            #     time.sleep(BATCH_PAUSE_SEC)

    print(f"\nvideo_images_content filled: {done}, failures: {failed}")


if __name__ == "__main__":
    main()
