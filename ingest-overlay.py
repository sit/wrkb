#!/usr/bin/env python
"""
Ingest text overlays from YouTube videos that use on-screen text instead of speech.

Designed for creators like BrokenSupport who communicate through text overlays
on gameplay footage rather than voice. Pipeline:

1. Downloads the video at low resolution (text-readable, bandwidth-efficient)
2. Samples frames at configurable intervals
3. OCRs the overlay region of each frame (bottom strip, tuned for BrokenSupport)
4. Deduplicates consecutive identical/similar captions
5. Outputs JSON (cache) + plain text (LLM input)
6. Optionally uses Gemini to clean up and produce a final markdown article

Usage:
    # Extract overlays from first 5 minutes
    uv run ingest-overlay.py --video-id "https://youtu.be/Jf-YmgkUXs8" --end-time 300

    # Full video with custom sample rate
    uv run ingest-overlay.py --video-id "Jf-YmgkUXs8" --sample-interval 1.0

    # Just extract (skip LLM processing)
    uv run ingest-overlay.py --video-id "Jf-YmgkUXs8" --extract-only

    # Process from cached extraction
    uv run ingest-overlay.py --video-id "Jf-YmgkUXs8" --from-cache
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import click

from lib.overlay import (
    OverlayCaption,
    OverlayExtraction,
    download_video,
    extract_overlays,
    extract_video_id,
    get_video_metadata,
)


# ---------------------------------------------------------------------------
# LLM Processing (optional, uses Gemini like ingest-yt.py)
# ---------------------------------------------------------------------------


def process_with_llm(
    extraction: OverlayExtraction,
    client,
    model_name: str,
) -> tuple[str, str]:
    """
    Process extracted overlays with Gemini to produce clean markdown.

    Cleans OCR artifacts, fixes Wild Rift terminology, organizes into
    sections with YouTube timestamp links, and generates a summary.
    """
    chat = client.chats.create(model=model_name)
    video_id = extraction.video_id

    transcript_text = extraction.to_transcript_text()

    organize_prompt = f"""
You are an experienced writer and editor working with text extracted via OCR from
a YouTube gameplay video. The video is from the channel "{extraction.metadata.get("channel", "Unknown")}"
and is titled "{extraction.metadata.get("title", "Unknown")}".

This creator communicates entirely through text overlays on gameplay footage (no speech).
The text below was extracted via OCR, so there may be errors. Each line starts with a
timestamp [HH:MM:SS] indicating when the text appeared on screen.

<EXTRACTED_TEXT>
{transcript_text}
</EXTRACTED_TEXT>

Your job is to:
1. Fix OCR errors and typos (garbled characters, wrong letters, etc.)
2. Correct any Wild Rift terminology mistakes (champion names, item names, abilities, runes).
   Make sure to use names from Wild Rift (not PC League of Legends).
3. Organize the text into a well-formatted article with:
   - Second-level headings `##` for major parts/concepts
   - Third-level headings `###` for sub-sections
   - Each heading should be a YouTube timestamp link: `### [Section Title](https://www.youtube.com/watch?v={video_id}&t=XXs)`
   - Link specific references to gameplay moments using the same format
4. Preserve the creator's communication style - they use text overlays intentionally,
   often with emphasis and personality.
5. Eliminate any promotional overlay text (subscribe reminders, etc.)

Provide the article only, no additional commentary.
"""

    start = time.monotonic()
    response = chat.send_message(organize_prompt)
    organized = response.text
    organize_time = timedelta(seconds=time.monotonic() - start)
    click.echo(f"Organized in {organize_time}")

    summary_prompt = """
Provide a concise summary of no more than 300 words that captures the main points of the video.
- Start with 2-3 sentences overview.
- Use bullets for sections and key points.
- Each top-level section gets one bullet with at most 3 sub-bullets.
- Do not embellish beyond what was in the text.

Return the summary only, no additional commentary.
"""
    start = time.monotonic()
    summary_response = chat.send_message(summary_prompt)
    summary = summary_response.text
    summary_time = timedelta(seconds=time.monotonic() - start)
    click.echo(f"Summary generated in {summary_time}")

    return summary, organized


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def save_extraction(extraction: OverlayExtraction, output_dir: Path):
    """Save extraction as JSON (cache) and plain text (LLM input)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    video_id = extraction.video_id

    json_path = output_dir / f"{video_id}-overlays.json"
    json_path.write_text(json.dumps(extraction.to_dict(), indent=2))
    click.echo(f"Saved JSON: {json_path}")

    txt_path = output_dir / f"{video_id}-overlays.txt"
    txt_path.write_text(extraction.to_transcript_text())
    click.echo(f"Saved TXT: {txt_path}")


def save_markdown(
    extraction: OverlayExtraction,
    summary: str,
    organized: str,
    output_dir: Path,
) -> Path:
    """Save final markdown output, matching ingest-yt.py format."""
    video_id = extraction.video_id
    metadata = extraction.metadata

    formatted_date = ""
    if metadata.get("timestamp"):
        try:
            formatted_date = datetime.fromtimestamp(metadata["timestamp"]).strftime(
                "%Y-%m-%d"
            )
        except Exception:
            pass

    formatted_duration = ""
    if metadata.get("duration"):
        formatted_duration = str(timedelta(seconds=metadata["duration"]))

    filename = output_dir / f"{video_id}.md"
    with open(filename, "w") as f:
        # YAML front-matter
        f.write("---\n")
        f.write(
            f'title: "{metadata.get("title", "").replace(chr(34), chr(92) + chr(34))}"\n'
        )
        f.write(f'video_id: "{video_id}"\n')
        f.write(f'video_url: "https://www.youtube.com/watch?v={video_id}"\n')
        f.write(
            f'channel: "{metadata.get("channel", "").replace(chr(34), chr(92) + chr(34))}"\n'
        )
        if formatted_date:
            f.write(f'upload_date: "{formatted_date}"\n')
        if formatted_duration:
            f.write(f'duration: "{formatted_duration}"\n')
        f.write(f'date_processed: "{datetime.now().strftime("%Y-%m-%d")}"\n')
        f.write('type: "video"\n')
        f.write('source_type: "overlay_ocr"\n')
        f.write("---\n\n")

        # Content
        title = metadata.get("title", video_id)
        f.write(f"# {title}\n\n")
        f.write(summary)
        f.write("\n\n")
        f.write(organized)

    click.echo(f"Saved markdown: {filename}")
    return filename


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--video-id", required=True, help="YouTube video ID or URL")
@click.option("--kb", "-k", default="videos", help="Output directory")
@click.option(
    "--sample-interval",
    "-s",
    default=5.0,
    type=float,
    help="Seconds between frame samples (default: 5)",
)
@click.option(
    "--start-time",
    default=0,
    type=float,
    help="Start processing at this time in seconds",
)
@click.option(
    "--end-time",
    default=None,
    type=float,
    help="Stop processing at this time in seconds (default: full video)",
)
@click.option("--resolution", default="480", help="Download resolution (default: 480)")
@click.option(
    "--min-confidence",
    default=55.0,
    type=float,
    help="Minimum OCR confidence 0-100 (default: 55)",
)
@click.option(
    "--extract-only", is_flag=True, help="Only extract overlays, skip LLM processing"
)
@click.option(
    "--from-cache",
    is_flag=True,
    help="Use cached extraction JSON, skip video processing",
)
@click.option(
    "--model",
    "-m",
    default="gemini-2.5-flash",
    help="Gemini model for LLM processing",
)
@click.option(
    "--api-key",
    envvar="GEMINI_API_KEY",
    help="Google API key for Gemini (or set GEMINI_API_KEY)",
)
def main(
    video_id,
    kb,
    sample_interval,
    start_time,
    end_time,
    resolution,
    min_confidence,
    extract_only,
    from_cache,
    model,
    api_key,
):
    """Extract text overlays from gameplay videos and convert to markdown."""

    video_id = extract_video_id(video_id)
    kb_dir = Path(kb)
    cache_dir = kb_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Processing video: {video_id}")

    json_cache = kb_dir / f"{video_id}-overlays.json"

    if from_cache and json_cache.exists():
        click.echo(f"Loading from cache: {json_cache}")
        data = json.loads(json_cache.read_text())
        extraction = OverlayExtraction(
            video_id=data["video_id"],
            metadata=data["metadata"],
            captions=[OverlayCaption(**c) for c in data["captions"]],
            extraction_params=data["extraction_params"],
        )
    else:
        # Step 1: Get metadata
        click.echo("Fetching video metadata...")
        metadata = get_video_metadata(video_id)
        click.echo(f"Title: {metadata.get('title', 'Unknown')}")
        click.echo(f"Channel: {metadata.get('channel', 'Unknown')}")
        click.echo(f"Duration: {metadata.get('duration', 0)}s")

        # Step 2: Download video
        video_path = download_video(
            video_id,
            cache_dir,
            start_time=start_time if start_time > 0 else None,
            end_time=end_time,
            resolution=resolution,
            on_progress=click.echo,
        )

        # Step 3: Extract overlays via OCR
        click.echo("\nExtracting text overlays...")
        captions = extract_overlays(
            video_path,
            sample_interval=sample_interval,
            min_confidence=min_confidence,
            on_progress=click.echo,
        )

        extraction = OverlayExtraction(
            video_id=video_id,
            metadata=metadata,
            captions=captions,
            extraction_params={
                "sample_interval": sample_interval,
                "min_confidence": min_confidence,
                "resolution": resolution,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        # Save intermediate formats
        save_extraction(extraction, kb_dir)

    # Show what we found
    click.echo(f"\n--- EXTRACTED CAPTIONS ({len(extraction.captions)}) ---")
    for cap in extraction.captions[:20]:
        click.echo(
            f"  [{cap.start_timestamp} - {cap.end_timestamp}] "
            f"(conf: {cap.confidence:.0%}) {cap.text}"
        )
    if len(extraction.captions) > 20:
        click.echo(f"  ... and {len(extraction.captions) - 20} more")
    click.echo("--- END CAPTIONS ---\n")

    if extract_only:
        click.echo("Extract-only mode. Skipping LLM processing.")
        return

    # Step 4: LLM processing
    try:
        from google import genai
    except ImportError:
        click.echo("google-genai not installed. Skipping LLM processing.", err=True)
        return

    if not api_key:
        click.echo("No API key provided. Skipping LLM processing.", err=True)
        click.echo("Set GEMINI_API_KEY or use --api-key", err=True)
        return

    client = genai.Client(api_key=api_key)
    summary, organized = process_with_llm(extraction, client, model)

    click.echo("\n--- SUMMARY ---")
    click.echo(summary)
    click.echo("--- END SUMMARY ---\n")

    save_markdown(extraction, summary, organized, kb_dir)


if __name__ == "__main__":
    main()
