#!/usr/bin/env python
# /// script
# requires-python = "~=3.12"
# dependencies = [
#     "click",
#     "yt-dlp",
#     "youtube-transcript-api",
#     "llm",
#     "llm-gemini",
# ]
# ///

"""
Ingest YouTube videos about WildRift and turn them into structured Markdown files.

This tool downloads YouTube transcripts, cleans them up using Wild Rift terminology,
and creates a well-structured Markdown file with proper sections and timestamp links.
"""

import os
import sys
import click
import yt_dlp
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from youtube_transcript_api.formatters import JSONFormatter
import json
import llm
from timeit import default_timer as timer
from datetime import timedelta, datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


@dataclass
class Video:
    """Class to represent a YouTube video transcript with metadata."""

    video_id: str
    metadata: Dict[str, Any]
    transcript: List[Dict[str, Any]]

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
    def duration(self) -> int:
        """Return the video duration in seconds."""
        return self.metadata.get("duration", 0)

    @property
    def description(self) -> str:
        """Return the video description."""
        return self.metadata.get("description", "")

    def to_text(self) -> str:
        """Convert transcript segments to a continuous text."""
        if not self.transcript:
            return ""

        # Join all transcript segments into a single text
        full_text = " ".join(
            [
                segment.get("text", "")
                if isinstance(segment, dict)
                else getattr(segment, "text", "")
                for segment in self.transcript
            ]
        )
        return full_text

    def to_dict(self) -> Dict[str, Any]:
        """Convert transcript to a dictionary for serialization."""
        return {
            "video_id": self.video_id,
            "metadata": self.metadata,
            "transcript": self.transcript,
        }


class VideoManager:
    """Class to handle fetching and caching YouTube video transcripts."""

    def __init__(self, cache_dir: str = "kb"):
        """
        Initialize the VideoManager.

        Args:
            cache_dir: Directory to store cached video data.
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def extract_video_id(self, video_url: str) -> str:
        """
        Extract the video ID from a YouTube URL.

        Args:
            video_url: YouTube URL or video ID.

        Returns:
            The extracted video ID.
        """
        if "youtube.com/watch?v=" in video_url:
            return video_url.split("youtube.com/watch?v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            return video_url.split("youtu.be/")[1].split("?")[0]
        else:
            # If it's already an ID format
            return video_url

    def get_video_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get video metadata using yt-dlp.

        Args:
            video_id: YouTube video ID.

        Returns:
            Dictionary containing video metadata or None if fetching fails.
        """
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
                click.echo(f"Error fetching video metadata: {e}", err=True)
                return None

    def get_transcript(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get the transcript from a YouTube video ID.

        Args:
            video_id: YouTube video ID.

        Returns:
            List of transcript segments or None if fetching fails.
        """
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Try to get English transcript first
            try:
                transcript = transcript_list.find_transcript(["en"])
            except Exception:
                # If no English transcript, get the first available and translate it
                transcript = transcript_list.find_transcript(["en-US", "en-GB"])
                if not transcript:
                    transcript = transcript_list[0]
                    transcript = transcript.translate("en")

            raw_transcript = transcript.fetch()

            # Format the transcript as JSON
            formatter = JSONFormatter()
            formatted_transcript = formatter.format_transcript(raw_transcript)
            return json.loads(formatted_transcript)

        except (TranscriptsDisabled, NoTranscriptFound) as e:
            click.echo(f"No transcript available: {e}", err=True)
            return None
        except Exception as e:
            click.echo(f"Error fetching transcript: {e}", err=True)
            return None

    def get_cache_filename(self, video_id: str) -> str:
        """
        Get the cache filename for a video ID.

        Args:
            video_id: YouTube video ID.

        Returns:
            Path to the cache file.
        """
        return f"{self.cache_dir}/{video_id}_data.json"

    def load_from_cache(self, video_id: str) -> Optional[Video]:
        """
        Load transcript data from cache.

        Args:
            video_id: YouTube video ID.

        Returns:
            Transcript object if cache exists, None otherwise.
        """
        cache_filename = self.get_cache_filename(video_id)

        if os.path.exists(cache_filename):
            click.echo(f"Loading data from cache: {cache_filename}")
            try:
                with open(cache_filename, "r") as f:
                    data = json.load(f)
                    return Video(
                        video_id=data["video_id"],
                        metadata=data["metadata"],
                        transcript=data["transcript"],
                    )
            except Exception as e:
                click.echo(f"Error loading cache: {e}", err=True)
                return None
        return None

    def save_to_cache(self, transcript: Video) -> bool:
        """
        Save transcript data to cache.

        Args:
            transcript: Transcript object to save.

        Returns:
            True if saving succeeded, False otherwise.
        """
        cache_filename = self.get_cache_filename(transcript.video_id)

        try:
            with open(cache_filename, "w") as f:
                json.dump(transcript.to_dict(), f, indent=4)
            click.echo(f"Saved video data to cache: {cache_filename}")
            return True
        except Exception as e:
            click.echo(f"Error saving to cache: {e}", err=True)
            return False

    def fetch_transcript(self, video_id: str) -> Optional[Video]:
        """
        Fetch video metadata and transcript.

        Args:
            video_id: YouTube video ID.

        Returns:
            Transcript object if fetching succeeds, None otherwise.
        """
        click.echo(f"Fetching data for video: {video_id}")

        # Get video metadata
        metadata = self.get_video_metadata(video_id)
        if not metadata:
            click.echo("Failed to fetch video metadata.", err=True)
            return None

        # Get video transcript
        transcript_data = self.get_transcript(video_id)
        if not transcript_data:
            click.echo("Failed to fetch transcript.", err=True)
            return None

        transcript = Video(
            video_id=video_id, metadata=metadata, transcript=transcript_data
        )

        # Save to cache
        self.save_to_cache(transcript)

        return transcript

    def load(self, video_url: str) -> Optional[Video]:
        """
        Get transcript data, either from cache or by fetching it.

        Args:
            video_url: YouTube URL or video ID.

        Returns:
            Transcript object if available, None otherwise.
        """
        video_id = self.extract_video_id(video_url)
        click.echo(f"Processing video ID: {video_id}")

        # Try to load from cache
        transcript = self.load_from_cache(video_id)
        if transcript:
            return transcript

        # If not in cache, fetch it
        return self.fetch_transcript(video_id)


def process_transcript(transcript: Video, model_name: str) -> tuple:
    """
    Process the transcript using the specified LLM model.
    Uses a conversation to generate both summary and organized content in sequence.

    Args:
        transcript: Transcript object containing video data.
        model_name: The LLM model to use.

    Returns:
        tuple: (summary, organized_transcript)
    """
    try:
        full_text = transcript.to_text()
        video_id = transcript.video_id

        model = llm.get_model(model_name)

        # Start a conversation with the model
        conversation = model.conversation()

        # First prompt - get the summary
        summary_prompt = f"""
You are an expert summarizer for Wild Rift content.

Summarize the following transcript text of a YouTube video, encoded in a TRANSCRIPT tag.

<TRANSCRIPT>
{full_text}
</TRANSCRIPT>

Provide a concise summary that captures the main points of the transcript.
- Use bullets and lists to organize the content, taking note of any key gameplay concepts, game mechanics and champion specifics mentioned.
- Limit to 500 words, with no more than 3 top-level bullets and no more than 5 sub-bullets per top-level bullet.
- Make sure the bullets are concise.
- Format the summary so that it will render as Markdown.
- Do not include any promotional language (e.g., sponsor advertisements, requests to like/subscribe, participate in contests, etc.)
- Do not embellish the content with anything not directly stated in the transcript.
- Return the summary only, do not add any other explanation or commentary before or after the result.
"""

        click.echo(f"Summarizing transcript using {model_name}...")
        summary_start = timer()

        # Execute the summary prompt
        summary_response = conversation.prompt(summary_prompt, temperature=0.7)

        # Get the summary text - this is blocking until the full response is generated
        summary = summary_response.text()

        # Set end time after text is fully extracted
        summary_end = timer()
        click.echo(
            f"Summary generated in {timedelta(seconds=summary_end - summary_start)} seconds"
        )

        # Second prompt - organize the transcript
        organize_prompt = f"""
Now as an experienced copy-writer, with expertise in Wild Rift,
transform the transcript into an engaging article.

Important requirements:
- Correct any mistakes in the transcription. This could be improper spelling,
  captilization and punctuation. There are often errors where the transcription
  software misinterprets the names of champions, items, abilities, and runes. Make
  sure to check for names that are in Wild Rift (e.g. not in PC League of Legends)
  and correct them. Sometimes an ungrammatical sentence may indicate a mistake;
  correct names can often be inferred from context. Don't introduce any names
  that are not in the transcript.
- Eliminate any promotional language (e.g., sponsor advertisements, requests to like/subscribe, participate in contests, etc.)
- Eliminate any filler words and phrases.
- Use the author's tone, exact words and sequencing of ideas, while making it less conversational and more appropriate for written format.
  Do not skip details or important information.
- Break the transcript into paragraphs.
- Add headers to separate sections.
- Add YouTube timestamp links for all major sections and moments using this format:
   - For section headings: Use `## [Section Title](https://www.youtube.com/watch?v={video_id}&t=XXs)` where XXs is the timestamp in seconds
   - For specific gameplay demonstrations: When the speaker references something visually shown on screen, link a relevant phrase
     using the same format: [relevant text](https://www.youtube.com/watch?v={video_id}&t=XXs)
- Use the timestamps provided in the transcript to create these links.
- If a section covers a range of time, you can link to the start time.

Here is a full transcript with timestamps represented as a JSON array of segments:
<TRANSCRIPT_WITH_TIMESTAMPS>
{json.dumps(transcript.transcript)}
</TRANSCRIPT_WITH_TIMESTAMPS>

The timestamps in the transcript are in the format [MM:SS.MMM --> MM:SS.MMM] and represent start and end times in minutes:seconds.milliseconds.
Convert these to seconds for the YouTube links (e.g., 2:30 would be 150s in the link).

Provide the article only, do not add any other explanation or commentary
before or after the result. Do not add any wrapping tags or other markup
outside of the article.
"""

        click.echo(f"Organizing transcript using {model_name}...")
        organize_start = timer()

        # Execute the organize prompt
        organize_response = conversation.prompt(organize_prompt, temperature=0.7)

        # Get the organized text - this is blocking until the full response is generated
        organized = organize_response.text()

        # Set end time after text is fully extracted
        organize_end = timer()
        click.echo(
            f"Organization completed in {timedelta(seconds=organize_end - organize_start)} seconds"
        )

        return summary, organized

    except Exception as e:
        click.echo(f"Error processing transcript: {e}", err=True)
        raise e


@click.command()
@click.option("--video-id", required=True, help="YouTube video ID or URL")
@click.option(
    "--kb", "-k", default="kb", help="Knowledge base directory to save the output file"
)
@click.option(
    "--model",
    "-m",
    default="gemini-2.0-flash",  # "gemma-3-27b-it" is a great option but slow
    help="LLM model to use for summarization",
)
def main(video_id, kb, model):
    """Ingest a YouTube video and convert it to a structured Markdown file."""
    click.echo(f"Processing video: {video_id}")

    # Initialize the TranscriptManager with the specified cache directory
    manager = VideoManager(cache_dir=kb)

    # Get the transcript, either from cache or by fetching it
    video = manager.load(video_id)

    if not video:
        click.echo("Failed to get video. Exiting.", err=True)
        sys.exit(1)

    # Output basic info to verify everything works
    click.echo("Video loaded successfully.")
    click.echo(f"Video: {video.title}")
    click.echo(f"Channel: {video.channel}")

    # Process the transcript
    summary, organized = process_transcript(video, model)

    click.echo("\n--- TRANSCRIPT SUMMARY ---")
    click.echo(summary)
    click.echo("--- END SUMMARY ---\n")

    # Format upload date nicely if available
    formatted_date = ""
    metadata = video.metadata
    if metadata.get("timestamp"):
        try:
            # Convert unix timestamp to YYYY-MM-DD
            upload_date = datetime.fromtimestamp(metadata["timestamp"])
            formatted_date = upload_date.strftime("%Y-%m-%d")
        except Exception:
            formatted_date = ""

    # Format duration as HH:MM:SS
    formatted_duration = ""
    if video.duration:
        formatted_duration = str(timedelta(seconds=video.duration))

    summary_filename = f"{kb}/{video.video_id}.md"
    with open(summary_filename, "w") as f:
        # Write YAML front-matter
        f.write("---\n")
        f.write(f'title: "{metadata["title"].replace('"', '\\"')}"\n')
        f.write(f'video_id: "{video.video_id}"\n')
        f.write(f'video_url: "https://www.youtube.com/watch?v={video.video_id}"\n')
        f.write(f'channel: "{metadata["channel"].replace('"', '\\"')}"\n')
        if formatted_date:
            f.write(f'upload_date: "{formatted_date}"\n')
        if formatted_duration:
            f.write(f'duration: "{formatted_duration}"\n')
        f.write(f'date_processed: "{datetime.now().strftime("%Y-%m-%d")}"\n')
        f.write('type: "video"\n')
        f.write("---\n\n")

        # Write content
        f.write(f"# {metadata['title']}\n\n")
        f.write(summary)
        f.write("\n\n")
        f.write(organized)

    click.echo(f"Saved to {summary_filename}")


if __name__ == "__main__":
    main()
