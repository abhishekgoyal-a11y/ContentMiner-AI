#!/usr/bin/env python3
"""
Walk data/raw/**/*.json for lists of video rows (must include video_url), find rows
with video_transcript_file == null, download each video's audio with yt-dlp and
transcribe it locally with faster-whisper, store the full transcript text in the
video_transcript_file field, and rewrite that JSON file to disk after each
successful video (so progress survives crashes). After each success: random
sleep 5–10s; after every 10 successes, an extra 60s (1 min) pause (to ease
rate limits during audio downloads).

Works on videos with captions disabled and on auto-caption-poor languages.
Trade-off: slower than caption scraping, and needs a Whisper model downloaded
on first run (cached under ~/.cache/huggingface/).

Requires:
    pip install yt-dlp faster-whisper
    ffmpeg on PATH

Run from project root:
  python pipeline/fetch_transcripts.py
  python pipeline/fetch_transcripts.py --model small
  python pipeline/fetch_transcripts.py --lang en
  python pipeline/fetch_transcripts.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from faster_whisper import WhisperModel
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# Project imports when run as `python pipeline/fetch_transcripts.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RAW_DIR  # noqa: E402

MIN_DELAY_SEC = 5.0
MAX_DELAY_SEC = 10.0
BATCH_SIZE = 10
BATCH_PAUSE_SEC = 60.0


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


def download_audio(url: str, tmpdir: Path) -> Path:
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
        ],
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return tmpdir / f"{info['id']}.mp3"


def transcribe_audio(
    model: WhisperModel,
    audio_path: Path,
    language: str | None,
    progress_prefix: str = "",
    progress_every_sec: float = 15.0,
) -> str:
    segments, info = model.transcribe(str(audio_path), language=language, vad_filter=True)
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    parts: list[str] = []
    last_log = time.monotonic()
    for seg in segments:
        txt = (seg.text or "").strip()
        if txt:
            parts.append(txt)
        now = time.monotonic()
        if now - last_log >= progress_every_sec:
            pos = float(getattr(seg, "end", 0.0) or 0.0)
            pct = (pos / duration * 100) if duration > 0 else 0.0
            print(
                f"{progress_prefix}    ...transcribed {pos:.0f}/{duration:.0f}s ({pct:.0f}%)",
                flush=True,
            )
            last_log = now
    return " ".join(parts)


def discover_videos_json_files() -> list[Path]:
    """All *.json under RAW_DIR whose root is a list of dicts with video_url."""
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


def needs_transcript(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    if not row.get("video_url"):
        return False
    return row.get("video_transcript_file") is None


def count_pending(paths: list[Path]) -> int:
    n = 0
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list):
            n += sum(1 for r in data if needs_transcript(r))
    return n


def fmt_eta(seconds: float) -> str:
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set video_transcript_file to Whisper-transcribed text for rows under data/raw/"
    )
    parser.add_argument(
        "--model",
        default="base",
        help="faster-whisper model size (default: base). Options: tiny, base, small, medium, large-v3",
    )
    parser.add_argument(
        "--lang",
        dest="language",
        default=None,
        metavar="CODE",
        help="Force a language code for transcription, e.g. en, hi (default: auto-detect)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Process at most N rows that still need a transcript (counts attempts, default: 0 = no limit)",
    )
    args = parser.parse_args()

    paths = discover_videos_json_files()
    if not paths:
        print(f"No usable video-list JSON files under {RAW_DIR}", file=sys.stderr)
        raise SystemExit(1)

    total_pending = count_pending(paths)
    target = min(args.limit, total_pending) if args.limit else total_pending
    print(
        f"Found {total_pending} video(s) needing transcript across {len(paths)} JSON file(s)"
        + (f"; processing up to {target} (--limit)" if args.limit else ""),
        flush=True,
    )

    print(f"Loading faster-whisper model: {args.model} ...", file=sys.stderr)
    t_model = time.monotonic()
    model = WhisperModel(args.model, device="auto", compute_type="auto")
    print(f"Model loaded in {time.monotonic() - t_model:.1f}s", file=sys.stderr)

    run_start = time.monotonic()
    done = 0
    failed = 0
    stop = False

    attempted = 0

    for json_path in paths:
        if stop:
            break
        try:
            raw_text = json_path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Skip unreadable JSON {json_path}: {e}", file=sys.stderr)
            continue

        if not isinstance(data, list):
            print(f"Skip {json_path}: root JSON is not a list", file=sys.stderr)
            continue

        for row in data:
            if not needs_transcript(row):
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

            prefix = f"[{attempted}/{target}] {video_id}"
            t0 = time.monotonic()
            try:
                with tempfile.TemporaryDirectory() as td:
                    print(f"{prefix}  download...", flush=True)
                    audio = download_audio(url, Path(td))
                    t_dl = time.monotonic() - t0
                    print(f"{prefix}  transcribe ({args.model})... [audio {t_dl:.0f}s]", flush=True)
                    text = transcribe_audio(model, audio, args.language, progress_prefix=prefix)
            except DownloadError as e:
                print(f"{prefix}  yt-dlp failed: {e}", file=sys.stderr)
                failed += 1
                continue

            transcript_text = text.strip()
            transcripts_dir = json_path.parent / "transcripts"
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            transcript_path = transcripts_dir / f"{video_id}.txt"
            transcript_path.write_text(transcript_text, encoding="utf-8")

            row["video_transcript_file"] = f"transcripts/{video_id}.txt"
            done += 1
            n = len(transcript_text)
            json_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            elapsed = time.monotonic() - t0
            avg = (time.monotonic() - run_start) / done
            eta = fmt_eta(avg * (target - done))
            print(
                f"{prefix}  OK {n}ch in {elapsed:.0f}s | avg {avg:.0f}s | ETA {eta} | {json_path.name}",
                flush=True,
            )

            gap = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
            time.sleep(gap)

            if done % BATCH_SIZE == 0:
                print(
                    f"  batch pause {BATCH_PAUSE_SEC:.0f}s after {done} successful transcript(s)",
                    flush=True,
                )
                time.sleep(BATCH_PAUSE_SEC)

    total_elapsed = fmt_eta(time.monotonic() - run_start)
    print(f"\nTranscripts written: {done}, failures: {failed}, time: {total_elapsed}")


if __name__ == "__main__":
    main()
