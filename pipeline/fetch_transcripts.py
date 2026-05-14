#!/usr/bin/env python3
"""
Walk data/raw/**/*.json for lists of video rows (must include video_url), find rows
with video_transcript_file == null,
fetch captions via youtube-transcript-api (same approach as YoutubeScraper/transcript_cli.py),
store the full transcript text in the video_transcript_file field, and rewrite that JSON
file to disk after each successful video (so progress survives crashes). After each success:
random sleep 5–10s; after every 10 successes, an extra 60s (1 min) pause (to ease rate limits / IP blocks).

If you hit **IpBlocked** / **RequestBlocked**, see the library README on working around IP bans:
https://github.com/jdepoix/youtube-transcript-api#working-around-ip-bans-requestblocked-or-ipblocked-exception

Transcript HTTP uses TLS with certificate verification disabled (same as the former --insecure),
because many environments fail verification against YouTube while still needing captions.

Run from project root:
  python pipeline/fetch_transcripts.py
  python pipeline/fetch_transcripts.py --lang hi --lang en
  python pipeline/fetch_transcripts.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from youtube_transcript_api import (
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

# Project imports when run as `python pipeline/fetch_transcripts.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RAW_DIR  # noqa: E402

MIN_DELAY_SEC = 5.0
MAX_DELAY_SEC = 10.0
BATCH_SIZE = 10
BATCH_PAUSE_SEC = 60.0


def build_http_session() -> requests.Session:
    """Session for YouTube transcript HTTP: verify=False (avoids common CA/TLS failures)."""
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = requests.Session()
    session.verify = False
    return session


def make_transcript_api(session: requests.Session) -> YouTubeTranscriptApi:
    return YouTubeTranscriptApi(http_client=session)


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


def fetch_transcript_text(
    api: YouTubeTranscriptApi,
    video_id: str,
    languages: list[str] | None,
) -> str:
    if languages:
        fetched = api.fetch(video_id, languages=languages)
    else:
        try:
            fetched = api.fetch(video_id, languages=["en"])
        except NoTranscriptFound:
            transcript_list = api.list(video_id)
            first = next(iter(transcript_list))
            fetched = first.fetch()

    lines: list[str] = []
    for snippet in fetched:
        text = (snippet.text or "").replace("\n", " ").strip()
        if text:
            lines.append(text)
    return " ".join(lines)


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set video_transcript_file to caption text for rows under data/raw/"
    )
    parser.add_argument(
        "--lang",
        action="append",
        dest="languages",
        metavar="CODE",
        help="Caption language priority (repeatable), e.g. en, hi",
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

    session = build_http_session()
    api = make_transcript_api(session)

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

            try:
                text = fetch_transcript_text(api, video_id, args.languages)
            except requests.exceptions.SSLError:
                print(
                    f"  TLS error for {video_id} (unexpected with verify disabled).",
                    file=sys.stderr,
                )
                failed += 1
                continue
            except TranscriptsDisabled:
                print(f"  Transcripts disabled: {video_id}", file=sys.stderr)
                failed += 1
                continue
            except VideoUnavailable:
                print(f"  Video unavailable: {video_id}", file=sys.stderr)
                failed += 1
                continue
            except NoTranscriptFound:
                print(
                    f"  No transcript: {video_id} (try --lang)",
                    file=sys.stderr,
                )
                failed += 1
                continue
            except PoTokenRequired:
                print(
                    f"  PoTokenRequired for {video_id} (YouTube); skip. "
                    "See youtube-transcript-api docs for cookies/po_token.",
                    file=sys.stderr,
                )
                failed += 1
                continue
            except (IpBlocked, RequestBlocked) as e:
                print(
                    f"  Blocked for {video_id} ({type(e).__name__}). "
                    "See youtube-transcript-api README: Working around IP bans.",
                    file=sys.stderr,
                )
                failed += 1
                continue

            row["video_transcript_file"] = text.strip()
            done += 1
            n = len(row["video_transcript_file"])
            json_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"OK {video_id} → stored transcript ({n} chars), saved {json_path}")

            gap = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
            time.sleep(gap)
            print(f"  waited {gap:.1f}s (random {MIN_DELAY_SEC:.0f}–{MAX_DELAY_SEC:.0f}s)", flush=True)

            if done % BATCH_SIZE == 0:
                print(
                    f"  batch pause {BATCH_PAUSE_SEC:.0f}s (1 min) after {done} successful transcript(s)",
                    flush=True,
                )
                time.sleep(BATCH_PAUSE_SEC)

    print(f"\nTranscripts written: {done}, failures: {failed}")


if __name__ == "__main__":
    main()
