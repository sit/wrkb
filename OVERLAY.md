# Overlay Text Extraction

## Problem

Some Wild Rift content creators (e.g. BrokenSupport) communicate entirely
through text overlays on gameplay footage — no speech, no YouTube captions.
The existing `ingest-yt.py` pipeline relies on YouTube transcripts and cannot
process these videos. We need a way to extract the overlay text with timestamps
so it can feed into the same knowledge base workflow.

## Approach

`ingest-overlay.py` implements a pipeline:

1. **Download** video via yt-dlp using HLS (m3u8) format — CDN-delivered
   segments, no re-encoding, section downloads are fast
2. **Sample** frames at 5s intervals (sufficient for BrokenSupport's pacing)
3. **OCR** the bottom strip of each frame where overlays always appear
4. **Deduplicate** consecutive similar frames into single captioned spans
5. **Export** intermediate formats: JSON (full data), SRT (subtitles), plain text
6. **LLM cleanup** (optional) via Gemini — fixes OCR errors, corrects Wild Rift
   terminology, organizes into markdown with YouTube timestamp links

The script uses uv inline dependencies (PEP 723) and requires system-level
`tesseract-ocr`.

## Overlay Region

BrokenSupport consistently places text overlays in a dark banner near the
bottom of the frame. Measured via OCR bounding boxes across champion select,
loading screen, and preparation phase frames from `Jf-YmgkUXs8`:

- Frame resolution: 854×394
- Overlay text line 1: `y=323–343` (82–87%)
- Overlay text line 2: `y=349–369` (88–94%)
- Side HUD (champion portraits, rune icons) extends into the banner edges

The `--text-region overlay` preset crops to:
- **y: 80–95%** — captures both text lines with margin, excludes champion
  name labels and skin titles that sit above the banner
- **x: 18–82%** — excludes champion select side panels and rune icons

This eliminated nearly all OCR noise from HUD elements. The remaining
artifacts (thumbnail edges on loading screen frames) are minor enough for
LLM cleanup to handle.

## Confidence Threshold

From the first real-video test on `Jf-YmgkUXs8` (first 5 minutes, 5s sample):

- HUD noise: 39–47% confidence — pure garbage
- Real overlays: 55–72% confidence — clean readable text

The default `--min-confidence 30` is far too low. Set to `55` as the new
default. This eliminates all observed HUD noise without dropping real content.

## Open Problems

- **OCR on gameplay backgrounds.** During gameplay (post-champion-select) the
  overlay text appears over moving game content rather than the black bar.
  Preprocessing (CLAHE + threshold) may need tuning for this case.

- **Multi-line overlays.** Some overlays span two lines (confirmed in test).
  Current approach captures them as a single block — acceptable for now.

- **Long video efficiency.** Could add frame differencing to skip static
  segments, but 5s sampling is already tractable for typical video lengths.

- **Deduplication threshold.** The 0.8 similarity ratio is untested at the
  tighter region crop. May need adjustment.

## Testing

First real-video test completed: `Jf-YmgkUXs8`, first 5 minutes, 5s sample
interval, HLS download format. Results:

- 60 frames sampled, 49 unique captions after dedup
- Real overlay content correctly captured from ~1:15 onwards
- First ~75 seconds: no overlay text (champion select only), all output was HUD noise
- Fix needed: raise `--min-confidence` to 55 and crop to bottom 25%

Second test with tight overlay crop (y=80-95%, x=18-82%) and min-confidence 55:

- 60 frames sampled, 23 with text, 13 unique captions after dedup
- Near-zero HUD noise — one garbage entry at 66% confidence (`- ' - . - - Py`)
- Overlay text reads cleanly: full sentences with minor OCR artifacts
  (e.g. `tormrazor` for Stormrazor, `™|` from thumbnail edge pixels)
- Champion select labels, skin names, rune icons all excluded by crop
- Default sample interval changed from 0.5s to 5s (sufficient for tuning)

## Next Steps

- [x] Implement `--text-region overlay` preset (tight y=80-95%, x=18-82%)
- [x] Raise default `--min-confidence` to 55
- [x] Change default `--sample-interval` from 0.5 to 5
- [x] Test updated parameters on `Jf-YmgkUXs8` — clean output, near-zero HUD noise
- [ ] Test on gameplay segment (post-champion-select) to verify OCR holds on moving backgrounds
- [ ] Run LLM cleanup on clean extraction
- [ ] Test on a full video
- [ ] Integrate output format with existing kb/ structure
