"""
Network integration tests for YouTube data fetching.

These tests make real network calls and are skipped by default.
Run with: uv run pytest -m network

They exist to catch upstream API breakage — the kind that caused:
  f397bf1 fix: update to youtube-transcript-api v1 (list_transcripts -> fetch)
  cc22c34 fix: deserialize cached transcript as Segment objects

Fixture video: https://www.youtube.com/watch?v=Y2odSb2rtjw (4m45s, public)
"""

import pytest

from lib.transcript import Segment
from lib.video import VideoManager

VIDEO_ID = "Y2odSb2rtjw"


@pytest.fixture(scope="module")
def manager(tmp_path_factory):
    return VideoManager(cache_dir=tmp_path_factory.mktemp("cache"))


@pytest.mark.network
def test_get_video_metadata_shape(manager):
    """yt-dlp returns the expected keys with the expected types.

    Catches: yt-dlp renaming keys (e.g. uploader -> channel) or changing
    the type of timestamp/duration between versions.
    """
    metadata = manager.get_video_metadata(VIDEO_ID)

    assert isinstance(metadata["title"], str) and metadata["title"]
    assert isinstance(metadata["channel"], str) and metadata["channel"]
    assert isinstance(metadata["duration"], int) and metadata["duration"] > 0
    assert isinstance(metadata["timestamp"], (int, float)) and metadata["timestamp"] > 0
    assert isinstance(metadata["upload_date"], str) and metadata["upload_date"]
    assert isinstance(metadata["description"], str)


@pytest.mark.network
def test_get_transcript_shape(manager):
    """youtube_transcript_api returns Segment objects with the expected fields.

    Catches: API version changes that rename fetch(), change the returned
    object's attributes (text/start/duration), or alter their types.
    """
    segments = manager.get_transcript(VIDEO_ID)

    assert len(segments) > 0
    for seg in segments:
        assert isinstance(seg, Segment), f"Expected Segment, got {type(seg)}"
        assert isinstance(seg.text, str) and seg.text
        assert isinstance(seg.start, float) and seg.start >= 0
        assert isinstance(seg.duration, float) and seg.duration > 0
