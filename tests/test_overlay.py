"""
Tests for lib/overlay.py pure-logic functions.

No cv2 or pytesseract — only dataclasses, deduplication, normalization,
and box detection (with synthetic numpy arrays).
"""

import json
import numpy as np

from lib.overlay import (
    OverlayCaption,
    OverlayExtraction,
    _deduplicate_captions,
    _find_overlay_box,
    _longest_run,
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


class TestLongestRun:
    def test_single_run(self):
        indices = np.array([10, 11, 12, 13, 14])
        assert _longest_run(indices, max_gap=2) == (10, 14)

    def test_two_runs_picks_longest(self):
        indices = np.array([0, 1, 2, 20, 21, 22, 23, 24])
        assert _longest_run(indices, max_gap=5) == (20, 24)

    def test_gap_within_tolerance(self):
        # Gap of 3, max_gap=5 → treated as one run
        indices = np.array([10, 11, 14, 15, 16])
        assert _longest_run(indices, max_gap=5) == (10, 16)

    def test_gap_exceeds_tolerance(self):
        # Gap of 10, max_gap=5 → split into two runs
        indices = np.array([10, 11, 12, 22, 23])
        assert _longest_run(indices, max_gap=5) == (10, 12)


class TestFindOverlayBox:
    def _make_frame(self, h=394, w=854):
        """Create a synthetic grayscale frame with a dark box in the bottom."""
        # Background: medium gray (game content)
        frame = np.full((h, w), 120, dtype=np.uint8)
        # Dark box: y=80-94%, x=15-85%
        y0, y1 = int(h * 0.80), int(h * 0.94)
        x0, x1 = int(w * 0.15), int(w * 0.85)
        frame[y0:y1, x0:x1] = 0  # near-black box
        return frame, (y0, y1, x0, x1)

    def test_finds_box(self):
        frame, (ey0, ey1, ex0, ex1) = self._make_frame()
        result = _find_overlay_box(frame)
        assert result is not None
        y0, y1, x0, x1 = result
        # Allow small tolerance since percentile-based detection
        # may not hit exact pixel boundaries
        assert abs(y0 - ey0) <= 2
        assert abs(y1 - ey1) <= 2
        assert abs(x0 - ex0) <= 2
        assert abs(x1 - ex1) <= 2

    def test_no_box_returns_none(self):
        # Uniform gray frame — no dark box
        frame = np.full((394, 854), 120, dtype=np.uint8)
        assert _find_overlay_box(frame) is None

    def test_box_with_text_rows(self):
        """White text rows inside the box should not break detection."""
        frame, (ey0, ey1, ex0, ex1) = self._make_frame()
        # Simulate two rows of white text inside the box
        mid = (ey0 + ey1) // 2
        frame[mid - 2 : mid + 2, ex0 + 20 : ex1 - 20] = 220  # white text
        frame[mid + 8 : mid + 12, ex0 + 30 : ex1 - 30] = 220
        result = _find_overlay_box(frame)
        assert result is not None
        y0, y1, x0, x1 = result
        # Box should still span the full extent despite text gaps
        assert y0 <= ey0 + 2
        assert y1 >= ey1 - 2

    def test_ignores_small_dark_patches(self):
        """Small dark regions (HUD elements) should not be detected."""
        frame = np.full((394, 854), 120, dtype=np.uint8)
        # Small dark patch — too narrow
        frame[350:370, 400:450] = 0
        assert _find_overlay_box(frame) is None
