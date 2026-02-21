import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import pytesseract
import yt_dlp
from difflib import SequenceMatcher
from PIL import Image
from yt_dlp.utils import download_range_func


def extract_video_id(video_url: str) -> str:
    """Extract YouTube video ID from a URL, or return as-is if already an ID."""
    parsed = urlparse(video_url)
    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/")
    return video_url


def get_video_metadata(video_id: str) -> dict:
    """Fetch video metadata using yt-dlp Python API."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            return {
                "title": info.get("title", ""),
                "channel": info.get("uploader", ""),
                "upload_date": info.get("upload_date", ""),
                "timestamp": info.get("timestamp", None),
                "duration": info.get("duration", 0),
                "description": info.get("description", ""),
            }
        except Exception as e:
            raise RuntimeError("Error fetching video metadata") from e


def download_video(
    video_id: str,
    output_dir: Path,
    start_time: float | None = None,
    end_time: float | None = None,
    resolution: str = "480",
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """Download a YouTube video using yt-dlp Python API."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.mp4"

    if output_path.exists():
        if on_progress:
            on_progress(f"Video already downloaded: {output_path}")
        return output_path

    if on_progress:
        on_progress(f"Downloading video (resolution: {resolution}p)...")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": f"bestvideo[height<={resolution}]",
        "outtmpl": str(output_path),
        "no_playlist": True,
    }

    if start_time is not None or end_time is not None:
        ranges = [(start_time or 0, end_time or float("inf"))]
        ydl_opts["download_ranges"] = download_range_func(None, ranges)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as e:
        raise RuntimeError(f"Video download failed for {video_id}") from e

    if on_progress:
        on_progress(f"Downloaded to {output_path}")
    return output_path


@dataclass
class OverlayCaption:
    """A single text overlay extracted from a video frame."""

    text: str
    start_time: float  # seconds into video
    end_time: float  # seconds into video (last frame seen)
    confidence: float  # OCR confidence (0-1)
    frame_count: int = 1  # number of frames this text appeared in

    @property
    def start_timestamp(self) -> str:
        """Format as HH:MM:SS"""
        return str(timedelta(seconds=int(self.start_time)))

    @property
    def end_timestamp(self) -> str:
        return str(timedelta(seconds=int(self.end_time)))


@dataclass
class OverlayExtraction:
    """Complete extraction result from a video."""

    video_id: str
    metadata: dict
    captions: list[OverlayCaption]
    extraction_params: dict

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "metadata": self.metadata,
            "captions": [asdict(c) for c in self.captions],
            "extraction_params": self.extraction_params,
        }

    def to_transcript_text(self) -> str:
        """Export as plain timestamped text."""
        lines = []
        for cap in self.captions:
            lines.append(f"[{cap.start_timestamp}] {cap.text}")
        return "\n".join(lines)


def extract_overlays(
    video_path: Path,
    sample_interval: float = 5.0,
    min_confidence: float = 55.0,
    on_progress: Callable[[str], None] | None = None,
) -> list[OverlayCaption]:
    """
    Extract text overlays from video frames using OCR.

    Samples frames at regular intervals, crops to the BrokenSupport overlay
    region (bottom strip, horizontally centered), preprocesses for OCR, and
    deduplicates consecutive similar captions.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if on_progress:
        on_progress(
            f"Video: {width}x{height} @ {fps:.1f}fps, duration: {duration:.1f}s"
        )
        on_progress(f"Sample interval: {sample_interval}s")

    raw_captions = []
    current_time = 0.0
    frames_processed = 0
    frames_with_text = 0

    while current_time < duration:
        frame_number = int(current_time * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()

        if not ret:
            break

        text, confidence = _ocr_frame(frame, width, height)
        frames_processed += 1

        if text and confidence >= min_confidence:
            frames_with_text += 1
            raw_captions.append(
                OverlayCaption(
                    text=text.strip(),
                    start_time=current_time,
                    end_time=current_time,
                    confidence=confidence / 100.0,
                    frame_count=1,
                )
            )

        if frames_processed % 50 == 0 and on_progress:
            pct = current_time / duration * 100
            on_progress(
                f"  {pct:.0f}% ({frames_processed} frames, {frames_with_text} with text)"
            )

        current_time += sample_interval

    cap.release()
    if on_progress:
        on_progress(
            f"Processed {frames_processed} frames, found text in {frames_with_text}"
        )

    captions = _deduplicate_captions(raw_captions)
    if on_progress:
        on_progress(f"After deduplication: {len(captions)} unique captions")

    return captions


def _find_overlay_box(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    """
    Detect the dark overlay text box in a video frame.

    BrokenSupport's overlays are white text on a near-black semi-transparent
    rectangle in the lower portion of the frame. This function finds the
    pixel-level bounding box of that rectangle.

    Uses the 25th percentile of brightness per row/column so that white text
    pixels inside the box don't break detection.

    Returns (y0, y1, x0, x1) pixel coordinates, or None if no box found.
    """
    h, w = gray.shape

    # Row-wise 25th percentile across center 50% of width
    center = gray[:, w // 4 : w * 3 // 4]
    row_p25 = np.percentile(center, 25, axis=1)

    # Search bottom 40% of frame for near-black rows (box interior)
    search_start = int(h * 0.60)
    is_box = row_p25[search_start:] < 5

    if not is_box.any():
        return None

    indices = np.where(is_box)[0]
    # Find the longest contiguous run, allowing gaps up to 5 rows
    # (text lines cause brief brightness spikes within the box)
    y0, y1 = _longest_run(indices, max_gap=5)
    y0 += search_start
    y1 += search_start

    if y1 - y0 < 20:
        return None

    # Column-wise 25th percentile across the detected row band
    col_p25 = np.percentile(gray[y0:y1, :], 25, axis=0)
    is_dark = col_p25 < 10

    if not is_dark.any():
        return None

    col_indices = np.where(is_dark)[0]
    x0, x1 = _longest_run(col_indices, max_gap=10)

    if x1 - x0 < w * 0.3:
        return None

    return (y0, y1, x0, x1)


def _longest_run(indices: np.ndarray, max_gap: int) -> tuple[int, int]:
    """Find the start and end values of the longest contiguous run in sorted indices."""
    diffs = np.diff(indices)
    breaks = np.where(diffs > max_gap)[0]

    runs = []
    start = 0
    for b in breaks:
        runs.append((indices[start], indices[b]))
        start = b + 1
    runs.append((indices[start], indices[-1]))

    return max(runs, key=lambda r: r[1] - r[0])


def _ocr_frame(frame, width: int, height: int) -> tuple[str, float]:
    """
    Run OCR on the overlay region of a single frame.

    Detects the dark overlay box dynamically, preprocesses for white-on-dark
    text, and returns (text, confidence). Returns ("", 0) if no box found.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    box = _find_overlay_box(gray)
    if box is None:
        return "", 0

    y0, y1, x0, x1 = box
    region = gray[y0:y1, x0:x1]

    # Preprocess: CLAHE contrast boost → binary threshold → dilate
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(region)
    _, binary = cv2.threshold(enhanced, 200, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.dilate(binary, kernel, iterations=1)

    # Run Tesseract
    try:
        data = pytesseract.image_to_data(
            Image.fromarray(binary),
            output_type=pytesseract.Output.DICT,
            config="--psm 6 --oem 3",  # Assume uniform block of text
        )
    except Exception:
        return "", 0

    texts = []
    confidences = []
    for i, conf in enumerate(data["conf"]):
        conf = int(conf)
        if conf > 0 and data["text"][i].strip():
            word = data["text"][i]
            # Tesseract misreads capital I as pipe — fix standalone occurrences
            if word.strip() == "|":
                word = "I"
            texts.append(word)
            confidences.append(conf)

    if not texts:
        return "", 0

    text = " ".join(texts)
    avg_conf = sum(confidences) / len(confidences)

    # Filter: too short or mostly non-alphanumeric = garbage
    if len(text) < 3:
        return "", 0
    alpha_ratio = sum(c.isalpha() or c.isspace() for c in text) / len(text)
    if alpha_ratio <= 0.5:
        return "", 0

    return text, avg_conf


def _deduplicate_captions(
    captions: list[OverlayCaption],
    similarity_threshold: float = 0.8,
) -> list[OverlayCaption]:
    """
    Merge consecutive captions that are identical or very similar.

    Text overlays persist across multiple frames, so we merge them into a
    single caption with the full time range.  Fuzzy matching accounts for
    OCR producing slightly different results across frames.
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
    return re.sub(r"\s+", " ", text.lower().strip())
