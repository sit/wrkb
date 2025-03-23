# Ingest YT

This tool ingests YouTube videos about WildRift and turns it into a structured
Markdown file. 

## Usage

Make sure you have installed some relevant models for running the script locally.
```
uvx llm mlx download-model mlx-community/Qwen2.5-0.5B-Instruct-4bit1234    # small
uvx llm mlx download-model mlx-community/DeepSeek-R1-Distill-Qwen-32B-4bit # large
```

To run the script, use the following command:
```bash
uv run ingest-yt.py --video-id "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

You can also specify a custom knowledge base directory:

```bash
uv run ingest-yt.py --video-id "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --kb "/path/to/kb"
```

Or use the shorthand `-k`:

```bash
uv run ingest-yt.py --video-id "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -k "/path/to/kb"
```

## Requirements

This should be a single script file that can be run from the command line.

It's goal is to turn a YouTube transcript into a structured Markdown file that
can be part of our knowledge base.

The transcript text should be cleaned up to make sure any transcription errors
are corrected: since automatic transcriptions often don't know Wild Rift terms,
we use our KB of champions, items and runes to help correct transcriptions.

The transcript should then be analyzed to identify the logical structure of
the video. The speaker's exact text should then be formatted into paragraphs
and sections. Each section should include a embed link to the video timestamps. 

The tool can make use of the https://llm.datasette.io/en/stable/ library to access
other LLMs if needed to process text. We can also use the MLX extensions to
access models such as mlx-community/DeepSeek-R1-Distill-Qwen-32B-4bit. 

## Implementation Progress

### 1. Set up script with dependencies
- [x] Create script with `uv` dependencies
  - [x] Add `click` for CLI
  - [x] Add `yt-dlp` for video metadata
  - [x] Add `youtube-transcript-api` for transcripts
  - [x] Add `llm` for text processing
- [ ] Add MLX dependencies if using local models
  - [x] Test: Verify script runs with all dependencies

The script successfully:
- Parses YouTube URLs or direct video IDs
- Retrieves video metadata (title, channel, upload date, etc.)
- Downloads video transcripts with proper error handling
- Supports different output locations with the `-k/--kb` parameter

### 2. Download video transcript
- [x] Implement transcript download
  - [x] Use youtube-transcript-api
  - [x] Store transcript with timestamps
  - [x] Handle errors (video not found, no transcript)
  - [ ] Test: Mock API calls and verify error handling
  - [ ] Test: Verify timestamp format

### 3. Clean up transcript text
- [ ] Load KB data
  - [ ] Load champions list
  - [ ] Load items list 
  - [ ] Load runes list
- [ ] Implement text cleanup
  - [ ] Pattern matching for game terms
  - [ ] Fix transcription errors
  - [ ] Add proper punctuation
  - [ ] Format paragraphs
  - [ ] Test: Verify game term corrections
  - [ ] Test: Check punctuation fixes
  - [ ] Test: Validate paragraph formatting

### 4. Analyze video structure
- [ ] Implement LLM analysis
  - [ ] Identify sections and topics
  - [ ] Find timestamp boundaries
  - [ ] Classify video type
  - [ ] Extract key concepts
  - [ ] Test: Verify section detection
  - [ ] Test: Check video classification
  - [ ] Test: Validate concept extraction

### 5. Generate structured Markdown
- [ ] Create markdown generator
  - [ ] Add frontmatter metadata
  - [ ] Format sections with headings
  - [ ] Include timestamp links
  - [ ] Add concept tags
  - [ ] Save in KB format
  - [ ] Test: Validate markdown structure
  - [ ] Test: Check frontmatter schema
  - [ ] Test: Verify timestamp link format

### 6. Testing and validation
- [ ] Manual verification of output