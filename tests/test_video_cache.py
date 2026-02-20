"""
Tests for VideoManager cache read/write behaviour.

Fixture: tests/fixtures/Y2odSb2rtjw_data.json
  10-segment trimmed transcript of https://www.youtube.com/watch?v=Y2odSb2rtjw
  Committed once; never regenerated automatically.
"""

import json
from pathlib import Path

from lib.transcript import Segment
from lib.video import Video, VideoManager

FIXTURE = Path(__file__).parent / "fixtures" / "Y2odSb2rtjw_data.json"
FIXTURE_VIDEO_ID = "Y2odSb2rtjw"
FIXTURE_URL = f"https://www.youtube.com/watch?v={FIXTURE_VIDEO_ID}"


def load_fixture(fixture) -> dict:
    return json.loads(fixture.read_text())


def video_from_fixture(fixture) -> Video:
    raw = load_fixture(fixture)
    return Video(
        video_id=raw["video_id"],
        metadata=raw["metadata"],
        transcript=[Segment(**s) for s in raw["transcript"]],
    )


class TestCacheRoundTrip:
    def test_round_trip_fidelity(self, tmp_path):
        """save_to_cache → load_from_cache produces an identical Video."""
        original = video_from_fixture(FIXTURE)
        manager = VideoManager(cache_dir=tmp_path)

        manager.save_to_cache(original)
        loaded = manager.load_from_cache(FIXTURE_VIDEO_ID)

        assert loaded is not None
        assert loaded.video_id == original.video_id
        assert loaded.metadata == original.metadata
        assert len(loaded.transcript) == len(original.transcript)

        # Every element must be a Segment instance, not a plain dict.
        # This was a real regression (see git log: cc22c34).
        for seg in loaded.transcript:
            assert isinstance(seg, Segment), f"Expected Segment, got {type(seg)}"

        # Spot-check first and last segment values.
        assert loaded.transcript[0].text == original.transcript[0].text
        assert loaded.transcript[0].start == original.transcript[0].start
        assert loaded.transcript[0].duration == original.transcript[0].duration

        assert loaded.transcript[-1].text == original.transcript[-1].text
        assert loaded.transcript[-1].start == original.transcript[-1].start
        assert loaded.transcript[-1].duration == original.transcript[-1].duration

    def test_cache_miss_returns_none(self, tmp_path):
        """load_from_cache returns None when no cache file exists."""
        manager = VideoManager(cache_dir=tmp_path)
        result = manager.load_from_cache("nonexistent_id")
        assert result is None

    def test_load_prefers_cache_over_network(self, tmp_path, monkeypatch):
        """load() returns cached Video without hitting the network.

        Verifies that:
        - extract_video_id correctly parses the full URL
        - load_from_yt is never called when the cache is warm
        """
        # Pre-populate cache with fixture data.
        fixture_path = tmp_path / f"{FIXTURE_VIDEO_ID}_data.json"
        fixture_path.write_text(FIXTURE.read_text())

        manager = VideoManager(cache_dir=tmp_path)

        def must_not_be_called(video_id):
            raise AssertionError("load_from_yt called — cache was not used")

        monkeypatch.setattr(manager, "load_from_yt", must_not_be_called)

        video = manager.load(FIXTURE_URL)

        assert video is not None
        assert video.video_id == FIXTURE_VIDEO_ID
