import json
from datetime import datetime, timedelta
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yt_dlp
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from youtube_transcript_api.formatters import JSONFormatter

from lib.transcript import Segment


@dataclass
class Video:
    """Class to represent a YouTube video transcript with metadata."""

    video_id: str
    metadata: dict[str, Any]
    transcript: list[Segment]

    @property
    def title(self) -> str:
        """Return the video title."""
        return self.metadata.get("title", "")

    @property
    def channel(self) -> str:
        """Return the channel name."""
        return self.metadata.get("channel", "")

    @property
    def upload_date(self) -> str:
        """Return the upload date."""
        return self.metadata.get("upload_date", "")

    @property
    def formatted_upload_date(self) -> str:
        """Return the upload date formatted as YYYY-MM-DD."""
        if not self.metadata.get("timestamp"):
            return ""
        try:
            upload_date = datetime.fromtimestamp(self.metadata["timestamp"])
            return upload_date.strftime("%Y-%m-%d")
        except Exception:
            return ""

    @property
    def duration(self) -> int:
        """Return the video duration in seconds."""
        return self.metadata.get("duration", 0)

    @property
    def formatted_duration(self) -> str:
        """Return the video duration formatted as HH:MM:SS."""
        if not self.duration:
            return ""
        return str(timedelta(seconds=self.duration))

    @property
    def description(self) -> str:
        """Return the video description."""
        return self.metadata.get("description", "")

    def to_text(self) -> str:
        """Convert transcript segments to a continuous text."""
        return " ".join(segment.text for segment in self.transcript)

    def to_dict(self) -> dict[str, Any]:
        """Convert transcript to a dictionary for serialization."""
        return {
            "video_id": self.video_id,
            "metadata": self.metadata,
            "transcript": [asdict(s) for s in self.transcript],
        }


class VideoManager:
    """Class to handle fetching and caching YouTube video transcripts."""

    def __init__(self, cache_dir: str | Path = "kb"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def extract_video_id(self, video_url: str) -> str:
        if "youtube.com/watch?v=" in video_url:
            return video_url.split("youtube.com/watch?v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            return video_url.split("youtu.be/")[1].split("?")[0]
        else:
            # If it's already an ID format
            return video_url

    def get_video_metadata(self, video_id: str) -> dict[str, Any] | None:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
        }

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

    def get_transcript(self, video_id: str) -> list[dict[str, Any]] | None:
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Prefer English; fall back to first available with translation
            try:
                transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
            except Exception:
                transcript = next(iter(transcript_list)).translate("en")

            raw_transcript = transcript.fetch()

            # Format the transcript as JSON
            formatter = JSONFormatter()
            formatted_transcript = formatter.format_transcript(raw_transcript)
            return json.loads(formatted_transcript)

        except (TranscriptsDisabled, NoTranscriptFound) as e:
            raise RuntimeError("No transcript available") from e
        except Exception as e:
            raise RuntimeError("Error fetching transcript") from e

    def get_cache_path(self, video_id: str) -> Path:
        return self.cache_dir / f"{video_id}_data.json"

    def load_from_cache(self, video_id: str) -> Video | None:
        cache_path = self.get_cache_path(video_id)

        if cache_path.exists():
            raw = json.loads(cache_path.read_text())
            return Video(
                video_id=raw["video_id"],
                metadata=raw["metadata"],
                transcript=[Segment(**s) for s in raw["transcript"]],
            )
        return None

    def save_to_cache(self, video: Video) -> Path:
        cache_path = self.get_cache_path(video.video_id)

        cache_path.write_text(json.dumps(video.to_dict(), indent=4))
        return cache_path

    def load_from_yt(self, video_id: str) -> Video:
        # Get video metadata
        metadata = self.get_video_metadata(video_id)
        if not metadata:
            raise RuntimeError("Failed to fetch video metadata.")

        # Get video transcript
        transcript_data = self.get_transcript(video_id)
        if not transcript_data:
            raise RuntimeError("Failed to fetch transcript.")

        video = Video(video_id=video_id, metadata=metadata, transcript=transcript_data)

        return video

    def load(self, video_url: str) -> Video | None:
        video_id = self.extract_video_id(video_url)

        # Try to load from cache
        video = self.load_from_cache(video_id)
        if not video:
            # If not in cache, fetch it
            video = self.load_from_yt(video_id)
            self.save_to_cache(video)
        return video
