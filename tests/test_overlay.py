"""
Tests for lib/overlay.py pure-logic functions.

No cv2 or pytesseract — only dataclasses, deduplication, and normalization.
"""

import json

from lib.overlay import (
    OverlayCaption,
    OverlayExtraction,
    _deduplicate_captions,
    _normalize_for_comparison,
    extract_video_id,
)


class TestOverlayCaption:
    def test_start_timestamp_format(self):
        cap = OverlayCaption(
            text="hello",
            start_time=75.0,
            end_time=80.0,
            confidence=0.9,
        )
        assert cap.start_timestamp == "0:01:15"

    def test_end_timestamp_format(self):
        cap = OverlayCaption(
            text="hello",
            start_time=0.0,
            end_time=3661.0,
            confidence=0.9,
        )
        assert cap.end_timestamp == "1:01:01"


class TestOverlayExtraction:
    def _make_extraction(self):
        captions = [
            OverlayCaption(
                text="First caption",
                start_time=0.0,
                end_time=5.0,
                confidence=0.95,
                frame_count=2,
            ),
            OverlayCaption(
                text="Second caption",
                start_time=10.0,
                end_time=15.0,
                confidence=0.88,
                frame_count=1,
            ),
        ]
        return OverlayExtraction(
            video_id="abc123",
            metadata={"title": "Test Video", "duration": 60},
            captions=captions,
            extraction_params={"sample_interval": 5.0, "min_confidence": 55.0},
        )

    def test_to_dict_round_trip(self):
        original = self._make_extraction()
        data = original.to_dict()

        reconstructed = OverlayExtraction(
            video_id=data["video_id"],
            metadata=data["metadata"],
            captions=[OverlayCaption(**c) for c in data["captions"]],
            extraction_params=data["extraction_params"],
        )

        assert reconstructed.video_id == original.video_id
        assert reconstructed.metadata == original.metadata
        assert len(reconstructed.captions) == len(original.captions)
        for orig, recon in zip(original.captions, reconstructed.captions):
            assert recon.text == orig.text
            assert recon.start_time == orig.start_time
            assert recon.end_time == orig.end_time
            assert recon.confidence == orig.confidence
            assert recon.frame_count == orig.frame_count

    def test_to_transcript_text(self):
        extraction = self._make_extraction()
        text = extraction.to_transcript_text()
        lines = text.split("\n")
        assert len(lines) == 2
        assert lines[0] == "[0:00:00] First caption"
        assert lines[1] == "[0:00:10] Second caption"


class TestDeduplication:
    def test_empty_list(self):
        assert _deduplicate_captions([]) == []

    def test_identical_consecutive(self):
        caps = [
            OverlayCaption(
                text="Hello world",
                start_time=0.0,
                end_time=5.0,
                confidence=0.9,
            ),
            OverlayCaption(
                text="Hello world",
                start_time=5.0,
                end_time=10.0,
                confidence=0.85,
            ),
        ]
        result = _deduplicate_captions(caps)
        assert len(result) == 1
        assert result[0].end_time == 10.0
        assert result[0].frame_count == 2

    def test_similar_consecutive(self):
        """OCR produces slightly different text across frames — should merge."""
        caps = [
            OverlayCaption(
                text="Hello world",
                start_time=0.0,
                end_time=5.0,
                confidence=0.85,
            ),
            OverlayCaption(
                text="Hello worl",
                start_time=5.0,
                end_time=10.0,
                confidence=0.90,
            ),
        ]
        result = _deduplicate_captions(caps)
        assert len(result) == 1
        # Higher-confidence version's text wins
        assert result[0].text == "Hello worl"
        assert result[0].confidence == 0.90

    def test_different_not_merged(self):
        caps = [
            OverlayCaption(
                text="Hello world",
                start_time=0.0,
                end_time=5.0,
                confidence=0.9,
            ),
            OverlayCaption(
                text="Completely different text here",
                start_time=5.0,
                end_time=10.0,
                confidence=0.9,
            ),
        ]
        result = _deduplicate_captions(caps)
        assert len(result) == 2

    def test_merge_keeps_best_confidence(self):
        caps = [
            OverlayCaption(
                text="Hello world",
                start_time=0.0,
                end_time=5.0,
                confidence=0.70,
            ),
            OverlayCaption(
                text="Hello world!",
                start_time=5.0,
                end_time=10.0,
                confidence=0.95,
            ),
        ]
        result = _deduplicate_captions(caps)
        assert len(result) == 1
        assert result[0].text == "Hello world!"
        assert result[0].confidence == 0.95


class TestNormalize:
    def test_lowercase_and_collapse(self):
        assert _normalize_for_comparison("Hello   WORLD  ") == "hello world"


class TestExtractVideoId:
    def test_full_url(self):
        result = extract_video_id("https://www.youtube.com/watch?v=Jf-YmgkUXs8&t=120")
        assert result == "Jf-YmgkUXs8"

    def test_short_url(self):
        result = extract_video_id("https://youtu.be/Jf-YmgkUXs8?si=abc")
        assert result == "Jf-YmgkUXs8"

    def test_bare_id(self):
        result = extract_video_id("Jf-YmgkUXs8")
        assert result == "Jf-YmgkUXs8"


class TestCacheRoundTrip:
    def test_json_round_trip(self, tmp_path):
        """Write OverlayExtraction as JSON, read back, verify captions match."""
        captions = [
            OverlayCaption(
                text="Test caption",
                start_time=5.0,
                end_time=10.0,
                confidence=0.92,
                frame_count=3,
            ),
        ]
        original = OverlayExtraction(
            video_id="test123",
            metadata={"title": "Round Trip Test"},
            captions=captions,
            extraction_params={"sample_interval": 5.0},
        )

        cache_file = tmp_path / "test123_overlay.json"
        cache_file.write_text(json.dumps(original.to_dict(), indent=2))

        data = json.loads(cache_file.read_text())
        loaded = OverlayExtraction(
            video_id=data["video_id"],
            metadata=data["metadata"],
            captions=[OverlayCaption(**c) for c in data["captions"]],
            extraction_params=data["extraction_params"],
        )

        assert loaded.video_id == original.video_id
        assert len(loaded.captions) == 1
        cap = loaded.captions[0]
        assert isinstance(cap, OverlayCaption)
        assert cap.text == "Test caption"
        assert cap.start_time == 5.0
        assert cap.end_time == 10.0
        assert cap.confidence == 0.92
        assert cap.frame_count == 3
