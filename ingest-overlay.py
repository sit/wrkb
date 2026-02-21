#!/usr/bin/env python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "click>=8.1.8",
#     "opencv-python-headless>=4.10.0",
#     "pytesseract>=0.3.13",
#     "Pillow>=11.0.0",
#     "yt-dlp>=2025.3.31",
#     "google-genai>=1.13.0",
# ]
# ///

"""
Ingest text overlays from YouTube videos that use on-screen text instead of speech.

This tool is designed for creators like BrokenSupport who communicate through
text overlays on gameplay footage rather than voice. It:

1. Downloads the video at low resolution (text-readable, bandwidth-efficient)
2. Samples frames at configurable intervals
3. Uses OCR to extract text from each frame
4. Deduplicates consecutive identical/similar captions
5. Outputs a structured intermediate format (JSON + SRT)
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

import os
import json
import time
import re
import subprocess
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from difflib import SequenceMatcher

import click

# Optional imports - graceful degradation
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class OverlayCaption:
    """A single text overlay extracted from a video frame."""
    text: str
    start_time: float        # seconds into video
    end_time: float          # seconds into video (last frame seen)
    confidence: float        # OCR confidence (0-1)
    frame_count: int = 1     # number of frames this text appeared in
    region: str = "center"   # where on screen: top, center, bottom

    @property
    def start_timestamp(self) -> str:
        """Format as HH:MM:SS"""
        return str(timedelta(seconds=int(self.start_time)))

    @property
    def end_timestamp(self) -> str:
        return str(timedelta(seconds=int(self.end_time)))

    @property
    def youtube_seconds(self) -> int:
        return int(self.start_time)


@dataclass
class OverlayExtraction:
    """Complete extraction result from a video."""
    video_id: str
    metadata: Dict[str, Any]
    captions: List[OverlayCaption]
    extraction_params: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "metadata": self.metadata,
            "captions": [asdict(c) for c in self.captions],
            "extraction_params": self.extraction_params,
        }

    def to_srt(self) -> str:
        """Export as SRT subtitle format."""
        lines = []
        for i, cap in enumerate(self.captions, 1):
            start = _format_srt_time(cap.start_time)
            end = _format_srt_time(cap.end_time)
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(cap.text)
            lines.append("")
        return "\n".join(lines)

    def to_transcript_text(self) -> str:
        """Export as plain timestamped text."""
        lines = []
        for cap in self.captions:
            lines.append(f"[{cap.start_timestamp}] {cap.text}")
        return "\n".join(lines)


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------------------------------------------------------------------------
# Video download
# ---------------------------------------------------------------------------

def download_video(video_id: str, output_dir: str,
                   start_time: Optional[float] = None,
                   end_time: Optional[float] = None,
                   resolution: str = "480") -> str:
    """
    Download video at low resolution for OCR processing.

    We use 480p because:
    - Text overlays are typically large enough to read at 480p
    - Massively reduces download time for multi-hour videos
    - Reduces frame processing time

    For very long videos (3-6 hours), consider using start_time/end_time
    to process in chunks.
    """
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{video_id}.mp4")

    if os.path.exists(output_path):
        click.echo(f"Video already downloaded: {output_path}")
        return output_path

    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        "yt-dlp",
        "-f", f"best[height<={resolution}][protocol=m3u8_native]",
        "-o", output_path,
        "--no-playlist",
    ]

    if start_time is not None or end_time is not None:
        section = "*"
        if start_time is not None:
            section += f"{start_time}"
        section += "-"
        if end_time is not None:
            section += f"{end_time}"
        cmd.extend(["--download-sections", section])

    cmd.append(url)

    click.echo(f"Downloading video (resolution: {resolution}p)...")
    click.echo(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Download failed: {result.stderr}", err=True)
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    click.echo(f"Downloaded to {output_path}")
    return output_path


def get_video_metadata(video_id: str) -> Dict[str, Any]:
    """Get video metadata via yt-dlp."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--skip-download",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Metadata fetch failed: {result.stderr}", err=True)
        return {"title": "", "channel": "", "duration": 0}

    info = json.loads(result.stdout)
    return {
        "title": info.get("title", ""),
        "channel": info.get("uploader", ""),
        "upload_date": info.get("upload_date", ""),
        "timestamp": info.get("timestamp", None),
        "duration": info.get("duration", 0),
        "description": info.get("description", ""),
    }


# ---------------------------------------------------------------------------
# Frame extraction and OCR
# ---------------------------------------------------------------------------

def extract_video_id(video_url: str) -> str:
    """Extract video ID from URL or return as-is."""
    if "youtube.com/watch?v=" in video_url:
        return video_url.split("youtube.com/watch?v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        return video_url.split("youtu.be/")[1].split("?")[0]
    return video_url


def extract_overlays(
    video_path: str,
    sample_interval: float = 5.0,
    text_region: str = "auto",
    min_confidence: float = 30.0,
    start_time: float = 0,
    end_time: Optional[float] = None,
) -> List[OverlayCaption]:
    """
    Extract text overlays from video frames using OCR.

    Strategy:
    1. Sample frames at regular intervals (default 0.5s)
       - BrokenSupport's text stays on screen for several seconds,
         so 0.5s gives good temporal resolution without waste
    2. For each frame, crop to likely text regions
       - Text overlays are typically in center or lower-third
    3. Pre-process frame for OCR (threshold, contrast enhancement)
    4. Run Tesseract OCR
    5. Deduplicate consecutive identical captions

    Args:
        video_path: Path to downloaded video file
        sample_interval: Seconds between frame samples
        text_region: Where to look for text: "auto", "center", "bottom", "overlay", "full"
        min_confidence: Minimum OCR confidence to accept (0-100)
        start_time: Start processing at this time (seconds)
        end_time: Stop processing at this time (seconds), None for full video
    """
    if not HAS_CV2:
        raise RuntimeError("opencv-python-headless is required: pip install opencv-python-headless")
    if not HAS_TESSERACT:
        raise RuntimeError("pytesseract and Pillow are required: pip install pytesseract Pillow")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if end_time is None or end_time > duration:
        end_time = duration

    click.echo(f"Video: {width}x{height} @ {fps:.1f}fps, duration: {duration:.1f}s")
    click.echo(f"Processing: {start_time:.1f}s to {end_time:.1f}s")
    click.echo(f"Sample interval: {sample_interval}s")

    raw_captions = []
    current_time = start_time
    frames_processed = 0
    frames_with_text = 0

    while current_time < end_time:
        # Seek to the target frame
        frame_number = int(current_time * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()

        if not ret:
            break

        # Extract text from the frame
        text, confidence = _ocr_frame(frame, width, height, text_region)
        frames_processed += 1

        if text and confidence >= min_confidence:
            frames_with_text += 1
            raw_captions.append(OverlayCaption(
                text=text.strip(),
                start_time=current_time,
                end_time=current_time,
                confidence=confidence / 100.0,
                frame_count=1,
            ))

        # Progress indicator
        if frames_processed % 50 == 0:
            pct = (current_time - start_time) / (end_time - start_time) * 100
            click.echo(f"  {pct:.0f}% ({frames_processed} frames, {frames_with_text} with text)")

        current_time += sample_interval

    cap.release()
    click.echo(f"Processed {frames_processed} frames, found text in {frames_with_text}")

    # Deduplicate consecutive identical/similar captions
    captions = _deduplicate_captions(raw_captions)
    click.echo(f"After deduplication: {len(captions)} unique captions")

    return captions


def _ocr_frame(
    frame,
    width: int,
    height: int,
    text_region: str = "auto",
) -> tuple:
    """
    Run OCR on a single frame, with preprocessing for text overlay detection.

    BrokenSupport-style overlays are typically:
    - White or light-colored text
    - Often with a dark shadow or outline for readability
    - Positioned in the center or lower portion of the frame
    - Larger font size (readable even at low resolution)

    Returns (text, confidence) tuple.
    """
    # Crop to region of interest
    regions_to_check = _get_text_regions(frame, width, height, text_region)

    best_text = ""
    best_confidence = 0

    for region, region_name in regions_to_check:
        # Pre-process for OCR
        processed = _preprocess_for_ocr(region)

        # Run Tesseract with confidence data
        try:
            data = pytesseract.image_to_data(
                Image.fromarray(processed),
                output_type=pytesseract.Output.DICT,
                config="--psm 6 --oem 3",  # Assume uniform block of text
            )

            # Extract text and compute average confidence
            texts = []
            confidences = []
            for i, conf in enumerate(data["conf"]):
                conf = int(conf)
                if conf > 0 and data["text"][i].strip():
                    texts.append(data["text"][i])
                    confidences.append(conf)

            if texts:
                text = " ".join(texts)
                avg_conf = sum(confidences) / len(confidences)

                # Filter out obvious garbage (very short, all symbols, etc.)
                if len(text) >= 3 and avg_conf > best_confidence:
                    # Filter out OCR noise: strings that are mostly non-alphanumeric
                    alpha_ratio = sum(c.isalpha() or c.isspace() for c in text) / max(len(text), 1)
                    if alpha_ratio > 0.5:
                        best_text = text
                        best_confidence = avg_conf

        except Exception:
            continue

    return best_text, best_confidence


def _get_text_regions(frame, width: int, height: int, text_region: str):
    """
    Get regions of the frame likely to contain text overlays.

    For BrokenSupport-style videos, text is typically in the center
    of the screen. We check multiple regions and take the best result.
    """
    regions = []

    if text_region == "full":
        regions.append((frame, "full"))
    elif text_region == "bottom":
        # Bottom quarter
        y_start = int(height * 0.75)
        regions.append((frame[y_start:height, :], "bottom"))
    elif text_region == "overlay":
        # BrokenSupport overlay banner: text sits at y≈82-94% of frame,
        # centered horizontally.  Tight crop eliminates champion-select
        # labels above and HUD icons at the sides.
        y_start = int(height * 0.80)
        y_end = int(height * 0.95)
        x_start = int(width * 0.18)
        x_end = int(width * 0.82)
        regions.append((frame[y_start:y_end, x_start:x_end], "overlay"))
    elif text_region == "center":
        # Middle band
        y_start = int(height * 0.25)
        y_end = int(height * 0.75)
        regions.append((frame[y_start:y_end, :], "center"))
    else:  # "auto" - check multiple regions
        # Center band (most common for BrokenSupport)
        y_start = int(height * 0.20)
        y_end = int(height * 0.80)
        regions.append((frame[y_start:y_end, :], "center"))

        # Lower third (subtitle area)
        y_start = int(height * 0.75)
        regions.append((frame[y_start:height, :], "bottom"))

        # Upper area (sometimes used for titles/labels)
        y_end = int(height * 0.25)
        regions.append((frame[0:y_end, :], "top"))

    return regions


def _preprocess_for_ocr(frame):
    """
    Preprocess a frame region for better OCR results.

    Text overlays on gameplay typically have:
    - White/bright text on varied backgrounds
    - Often an outline or drop shadow

    We use multiple strategies and pick the one that gives best OCR:
    1. Grayscale + threshold (good for white text)
    2. Inverted threshold (good for dark text)
    3. Adaptive threshold (good for varied backgrounds)
    """
    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Strategy 1: Simple threshold for white text
    # Boost contrast first
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Threshold - white text becomes white, rest becomes black
    _, binary = cv2.threshold(enhanced, 200, 255, cv2.THRESH_BINARY)

    # Slight dilation to connect text components
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.dilate(binary, kernel, iterations=1)

    return binary


def _deduplicate_captions(captions: List[OverlayCaption],
                          similarity_threshold: float = 0.8) -> List[OverlayCaption]:
    """
    Merge consecutive captions that are identical or very similar.

    Text overlays persist across multiple frames, so we merge them
    into a single caption with the full time range.

    We use fuzzy matching because OCR might produce slightly different
    results across frames (a letter here or there).
    """
    if not captions:
        return []

    merged = []
    current = captions[0]

    for next_cap in captions[1:]:
        similarity = SequenceMatcher(
            None,
            _normalize_for_comparison(current.text),
            _normalize_for_comparison(next_cap.text),
        ).ratio()

        if similarity >= similarity_threshold:
            # Merge: extend time range, keep highest confidence version
            current.end_time = next_cap.end_time
            current.frame_count += 1
            if next_cap.confidence > current.confidence:
                current.text = next_cap.text
                current.confidence = next_cap.confidence
        else:
            merged.append(current)
            current = next_cap

    merged.append(current)
    return merged


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for comparison (lowercase, collapse whitespace)."""
    return re.sub(r'\s+', ' ', text.lower().strip())


# ---------------------------------------------------------------------------
# LLM Processing (optional, uses Gemini like ingest-yt.py)
# ---------------------------------------------------------------------------

def process_with_llm(
    extraction: OverlayExtraction,
    client,
    model_name: str,
) -> tuple:
    """
    Process extracted overlays with Gemini to produce clean markdown.

    Similar to ingest-yt.py's approach but adapted for overlay text:
    - Clean up OCR artifacts
    - Fix Wild Rift terminology
    - Organize into logical sections
    - Add YouTube timestamp links
    """
    chat = client.chats.create(model=model_name)
    video_id = extraction.video_id

    # Step 1: Clean and organize the raw overlay text
    transcript_text = extraction.to_transcript_text()

    organize_prompt = f"""
You are an experienced writer and editor working with text extracted via OCR from
a YouTube gameplay video. The video is from the channel "{extraction.metadata.get('channel', 'Unknown')}"
and is titled "{extraction.metadata.get('title', 'Unknown')}".

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

    # Step 2: Generate summary
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

def save_extraction(extraction: OverlayExtraction, output_dir: str) -> dict:
    """Save extraction in multiple formats."""
    os.makedirs(output_dir, exist_ok=True)
    video_id = extraction.video_id
    paths = {}

    # JSON (full data, machine-readable)
    json_path = os.path.join(output_dir, f"{video_id}-overlays.json")
    with open(json_path, "w") as f:
        json.dump(extraction.to_dict(), f, indent=2)
    paths["json"] = json_path
    click.echo(f"Saved JSON: {json_path}")

    # SRT (standard subtitle format)
    srt_path = os.path.join(output_dir, f"{video_id}-overlays.srt")
    with open(srt_path, "w") as f:
        f.write(extraction.to_srt())
    paths["srt"] = srt_path
    click.echo(f"Saved SRT: {srt_path}")

    # Plain text transcript
    txt_path = os.path.join(output_dir, f"{video_id}-overlays.txt")
    with open(txt_path, "w") as f:
        f.write(extraction.to_transcript_text())
    paths["txt"] = txt_path
    click.echo(f"Saved TXT: {txt_path}")

    return paths


def save_markdown(
    extraction: OverlayExtraction,
    summary: str,
    organized: str,
    output_dir: str,
) -> str:
    """Save final markdown output, matching ingest-yt.py format."""
    video_id = extraction.video_id
    metadata = extraction.metadata

    # Format dates
    formatted_date = ""
    if metadata.get("timestamp"):
        try:
            formatted_date = datetime.fromtimestamp(metadata["timestamp"]).strftime("%Y-%m-%d")
        except Exception:
            pass

    formatted_duration = ""
    if metadata.get("duration"):
        formatted_duration = str(timedelta(seconds=metadata["duration"]))

    filename = os.path.join(output_dir, f"{video_id}.md")
    with open(filename, "w") as f:
        # YAML front-matter
        f.write("---\n")
        f.write(f'title: "{metadata.get("title", "").replace(chr(34), chr(92)+chr(34))}"\n')
        f.write(f'video_id: "{video_id}"\n')
        f.write(f'video_url: "https://www.youtube.com/watch?v={video_id}"\n')
        f.write(f'channel: "{metadata.get("channel", "").replace(chr(34), chr(92)+chr(34))}"\n')
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
@click.option("--sample-interval", "-s", default=5.0, type=float,
              help="Seconds between frame samples (default: 5)")
@click.option("--start-time", default=0, type=float,
              help="Start processing at this time in seconds")
@click.option("--end-time", default=None, type=float,
              help="Stop processing at this time in seconds (default: full video)")
@click.option("--resolution", default="480",
              help="Download resolution (default: 480)")
@click.option("--text-region", default="auto",
              type=click.Choice(["auto", "center", "bottom", "overlay", "full"]),
              help="Where to look for text overlays (overlay = bottom 25%%)")
@click.option("--min-confidence", default=55.0, type=float,
              help="Minimum OCR confidence 0-100 (default: 55)")
@click.option("--extract-only", is_flag=True,
              help="Only extract overlays, skip LLM processing")
@click.option("--from-cache", is_flag=True,
              help="Use cached extraction JSON, skip video processing")
@click.option("--model", "-m", default="gemini-2.0-flash-001",
              help="Gemini model for LLM processing")
@click.option("--api-key", envvar="GEMINI_API_KEY",
              help="Google API key for Gemini (or set GEMINI_API_KEY)")
def main(video_id, kb, sample_interval, start_time, end_time, resolution,
         text_region, min_confidence, extract_only, from_cache, model, api_key):
    """Extract text overlays from gameplay videos and convert to markdown."""

    video_id = extract_video_id(video_id)
    click.echo(f"Processing video: {video_id}")

    cache_dir = os.path.join(kb, "cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Check if we have a cached extraction
    json_cache = os.path.join(kb, f"{video_id}-overlays.json")

    if from_cache and os.path.exists(json_cache):
        click.echo(f"Loading from cache: {json_cache}")
        with open(json_cache) as f:
            data = json.load(f)
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
            video_id, cache_dir,
            start_time=start_time if start_time > 0 else None,
            end_time=end_time,
            resolution=resolution,
        )

        # Step 3: Extract overlays via OCR
        click.echo("\nExtracting text overlays...")
        captions = extract_overlays(
            video_path,
            sample_interval=sample_interval,
            text_region=text_region,
            min_confidence=min_confidence,
            start_time=0,  # already trimmed by download
            end_time=None,
        )

        extraction = OverlayExtraction(
            video_id=video_id,
            metadata=metadata,
            captions=captions,
            extraction_params={
                "sample_interval": sample_interval,
                "text_region": text_region,
                "min_confidence": min_confidence,
                "resolution": resolution,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        # Save intermediate formats
        save_extraction(extraction, kb)

    # Show what we found
    click.echo(f"\n--- EXTRACTED CAPTIONS ({len(extraction.captions)}) ---")
    for cap in extraction.captions[:20]:  # Show first 20
        click.echo(f"  [{cap.start_timestamp} - {cap.end_timestamp}] "
                    f"(conf: {cap.confidence:.0%}) {cap.text}")
    if len(extraction.captions) > 20:
        click.echo(f"  ... and {len(extraction.captions) - 20} more")
    click.echo("--- END CAPTIONS ---\n")

    if extract_only:
        click.echo("Extract-only mode. Skipping LLM processing.")
        return

    # Step 4: LLM processing
    if not HAS_GENAI:
        click.echo("google-genai not installed. Skipping LLM processing.", err=True)
        click.echo("Install with: pip install google-genai", err=True)
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

    # Save final markdown
    save_markdown(extraction, summary, organized, kb)


if __name__ == "__main__":
    main()
