#!/usr/bin/env python
# /// script
# requires-python = "~=3.12"
# dependencies = [
#     "click",
#     "yt-dlp",
#     "youtube-transcript-api",
#     "google-genai",
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
from timeit import default_timer as timer
from datetime import timedelta, datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from google import genai


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
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def extract_video_id(self, video_url: str) -> str:
        if "youtube.com/watch?v=" in video_url:
            return video_url.split("youtube.com/watch?v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            return video_url.split("youtu.be/")[1].split("?")[0]
        else:
            # If it's already an ID format
            return video_url

    def get_video_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
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
        return f"{self.cache_dir}/{video_id}_data.json"

    def load_from_cache(self, video_id: str) -> Optional[Video]:
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
        cache_filename = self.get_cache_filename(transcript.video_id)

        try:
            with open(cache_filename, "w") as f:
                json.dump(transcript.to_dict(), f, indent=4)
            click.echo(f"Saved video data to cache: {cache_filename}")
            return True
        except Exception as e:
            click.echo(f"Error saving to cache: {e}", err=True)
            return False

    def load_from_yt(self, video_id: str) -> Optional[Video]:
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

        video = Video(
            video_id=video_id, metadata=metadata, transcript=transcript_data
        )

        return video

    def load(self, video_url: str) -> Optional[Video]:
        video_id = self.extract_video_id(video_url)
        click.echo(f"Loading video ID: {video_id}")

        # Try to load from cache
        video = self.load_from_cache(video_id)
        if not video:
            # If not in cache, fetch it
            video = self.load_from_yt(video_id)
            if not video:
                click.echo("Failed to fetch video data.", err=True)
                return None
            self.save_to_cache(video)
        return video


def process_transcript(
    transcript: Video, client: genai.Client, model_name: str
) -> tuple:
    """
    Process the transcript using the Google Genai SDK.
    Uses a conversation to generate both summary and organized content in sequence.

    Args:
        transcript: Transcript object containing video data.
        model_name: The Gemini model to use.
        client: Google Genai client.

    Returns:
        tuple: (summary, organized_transcript)
    """
    try:
        click.echo(f"Summarizing transcript using {model_name}...")
        summary_start = timer()

        # Create a chat for sequential prompts
        chat = client.chats.create(model=model_name)

        # First prompt - get the summary
        full_text = transcript.to_text()
        video_id = transcript.video_id
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

        # Execute the summary prompt
        summary_response = chat.send_message(summary_prompt)

        # Get the summary text
        summary = summary_response.text

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
- Group the paragraphs into sections for each main ideas. Use a third-level heading `###` for each section.
- Group the sections into larger parts or concepts. Use a second-level heading `##` for each part. This will
  typically include an introduction, a few main sections, and a conclusion.
- Add YouTube timestamp links for all major sections and moments using this format:
   - For section headings: Use `### [Section Title](https://www.youtube.com/watch?v={video_id}&t=XXs)` where XXs is the timestamp in seconds
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

        # Execute the organize prompt using the same chat
        organize_response = chat.send_message(organize_prompt)

        # Get the organized text
        organized = organize_response.text

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
    "--kb", "-k", default="videos", help="Knowledge base directory to save the output file"
)
@click.option(
    "--model",
    "-m",
    default="gemini-2.5-pro-exp-03-25",
    help="Gemini model to use for summarization (e.g., gemini-2.0-flash-001, gemini-1.5-pro-001)",
)
@click.option(
    "--api-key",
    envvar="GEMINI_API_KEY",
    help="Google API key for Gemini. If not provided, uses GEMINI_API_KEY environment variable.",
)
def main(video_id, kb, model, api_key):
    """Ingest a YouTube video and convert it to a structured Markdown file."""
    click.echo(f"Processing video: {video_id}")

    # Initialize the Gemini client
    client = genai.Client(api_key=api_key)

    # Initialize the TranscriptManager with the specified cache directory
    manager = VideoManager(cache_dir=os.path.join(kb, "cache"))

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
    summary, organized = process_transcript(video, client, model)

    click.echo("\n--- TRANSCRIPT SUMMARY ---")
    click.echo(summary)
    click.echo("--- END SUMMARY ---\n")

    # Format upload date nicely if available
    formatted_date = video.formatted_upload_date
    formatted_duration = video.formatted_duration

    summary_filename = f"{kb}/{video.video_id}.md"
    with open(summary_filename, "w") as f:
        # Write YAML front-matter
        f.write("---\n")
        f.write(f'title: "{video.title.replace('"', '\\"')}"\n')
        f.write(f'video_id: "{video.video_id}"\n')
        f.write(f'video_url: "https://www.youtube.com/watch?v={video.video_id}"\n')
        f.write(f'channel: "{video.channel.replace('"', '\\"')}"\n')
        if formatted_date:
            f.write(f'upload_date: "{formatted_date}"\n')
        if formatted_duration:
            f.write(f'duration: "{formatted_duration}"\n')
        f.write(f'date_processed: "{datetime.now().strftime("%Y-%m-%d")}"\n')
        f.write('type: "video"\n')
        f.write("---\n\n")

        # Write content
        f.write(f"# {video.title}\n\n")
        f.write(summary)
        f.write("\n\n")
        f.write(organized)

    click.echo(f"Saved to {summary_filename}")


if __name__ == "__main__":
    main()
