import subprocess
from pathlib import Path
import re
from config import VIDEO_DATA_CLEANED_FILE, TOPICS_RAW_FILE, TOPICS_RANKED_FILE, PROMPT_TOPIC_FILE, PROMPT_RANK_FILE

CLAUDE_CMD = ["claude", "--model", "sonnet"]


# ---------------- DEDUPLICATION ----------------
def deduplicate_topics(input_file):
    content = Path(input_file).read_text(encoding="utf-8")
    topics = [t.strip() for t in content.splitlines() if t.strip()]

    unique_topics = []
    seen = set()

    for topic in topics:
        topic_lower = topic.lower()
        if topic_lower not in seen:
            seen.add(topic_lower)
            unique_topics.append(topic)

    deduplicated = "\n".join(unique_topics)
    Path(input_file).write_text(deduplicated, encoding="utf-8")

    removed_count = len(topics) - len(unique_topics)
    print(f"🔄 Deduplication: {removed_count} duplicates removed")
    print(f"✨ Unique topics: {len(unique_topics)}")
    return len(unique_topics)

# ---------------- CLEAN VIDEO DATA FOR STEP 4 (STREAM FORMAT) ----------------
def clean_claude_output(input_text: str) -> str:
    videos = input_text.split("VIDEO ")
    output_lines = []

    for block in videos:
        if not block.strip():
            continue

        title = ""
        entities = []
        use_case = ""

        for line in block.splitlines():
            line = line.strip()

            if line.startswith("title:"):
                title = line.replace("title:", "").strip()

            elif line.startswith("ai_entities:"):
                raw = line.replace("ai_entities:", "").strip()
                entities = [e.strip() for e in raw.split(",") if e.strip()]

            elif line.startswith("use_case:"):
                use_case = line.replace("use_case:", "").strip()

        # skip invalid entries
        if not title:
            continue

        # append in strict line stream format
        output_lines.append(title)

        for e in entities:
            output_lines.append(e)

        if use_case:
            output_lines.append(use_case)

    # IMPORTANT: NO blank lines
    return "\n".join(output_lines)


# ---------------- STEP 4 ----------------
def step4_generate_topics():
    video_data = Path(VIDEO_DATA_CLEANED_FILE).read_text(encoding="utf-8")
    prompt = Path(PROMPT_TOPIC_FILE).read_text(encoding="utf-8")

    full_prompt = f"""
{prompt}

========================
YOUTUBE DATA:
========================
{video_data}
"""

    result = subprocess.run(
        CLAUDE_CMD,
        input=full_prompt,
        text=True,
        capture_output=True
    )

    raw_output = result.stdout

    # 🔥 CLEAN IMMEDIATELY AFTER CLAUDE OUTPUT
    cleaned_output = clean_claude_output(raw_output)

    Path(TOPICS_RAW_FILE).write_text(cleaned_output, encoding="utf-8")

    print(f"✅ Step 4 completed → {TOPICS_RAW_FILE}")

    # Deduplicate topics
    deduplicate_topics(TOPICS_RAW_FILE)

