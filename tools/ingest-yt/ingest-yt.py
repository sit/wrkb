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
from youtube_transcript_api.formatters import PrettyPrintFormatter
import llm
from timeit import default_timer as timer
from datetime import timedelta


def extract_video_id(video_url):
    """Extract the video ID from a YouTube URL."""
    if "youtube.com/watch?v=" in video_url:
        return video_url.split("youtube.com/watch?v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        return video_url.split("youtu.be/")[1].split("?")[0]
    else:
        # If it's already an ID format
        return video_url


def get_video_metadata(video_id):
    """Get video metadata using yt-dlp."""
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
                "duration": info.get("duration", 0),
                "description": info.get("description", ""),
            }
        except Exception as e:
            click.echo(f"Error fetching video metadata: {e}", err=True)
            return None


def get_transcript(video_id):
    """Get the transcript from a YouTube video ID."""
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

        return transcript.fetch()
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        click.echo(f"No transcript available: {e}", err=True)
        return None
    except Exception as e:
        click.echo(f"Error fetching transcript: {e}", err=True)
        return None


def transcript_to_text(transcript):
    """Convert transcript segments to a continuous text."""
    if not transcript:
        return ""

    # Join all transcript segments into a single text
    full_text = " ".join(
        [
            segment.get("text", "")
            if isinstance(segment, dict)
            else getattr(segment, "text", "")
            for segment in transcript
        ]
    )
    return full_text


def process_transcript(transcript_text, model_name):
    """
    Process the transcript using the specified LLM model.
    Uses a conversation to generate both summary and organized content in sequence.

    Returns:
        tuple: (summary, organized_transcript)
    """
    try:
        model = llm.get_model(model_name)

        # Start a conversation with the model
        conversation = model.conversation()

        # First prompt - get the summary
        summary_prompt = f"""
You are an expert summarizer for Wild Rift content.
Summarize the following YouTube transcript, encoded in a TRANSCRIPT tag.

<TRANSCRIPT>
{transcript_text}
</TRANSCRIPT>

Provide a concise summary that captures the main points.
Highlight any key gameplay concepts, champion strategies, or game mechanics mentioned.
"""

        click.echo(f"Summarizing transcript using {model_name}...")
        summary_start = timer()

        # Execute the summary prompt
        summary_response = conversation.prompt(summary_prompt)

        # Get the summary text - this is blocking until the full response is generated
        summary = summary_response.text()

        # Set end time after text is fully extracted
        summary_end = timer()
        click.echo(
            f"Summary generated in {timedelta(seconds=summary_end - summary_start)} seconds"
        )

        # Second prompt - organize the transcript
        organize_prompt = """
Now as an experienced copy-writer, with expertise in Wild Rift,
format the same transcript into an engaging article format, using Markdown.
The result should use the author's tone and exact words. Only add headers to separate sections.
You should eliminate any promotional language (e.g., sponsor advertisements, requests to
like/subscribe, participate in contests, etc.)
"""

        click.echo(f"Organizing transcript using {model_name}...")
        organize_start = timer()

        # Execute the organize prompt
        organize_response = conversation.prompt(organize_prompt)

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

    # Extract video ID if a URL was provided
    video_id = extract_video_id(video_id)
    click.echo(f"Extracted video ID: {video_id}")

    # Get video metadata
    metadata = get_video_metadata(video_id)
    if not metadata:
        click.echo("Failed to fetch video metadata. Exiting.", err=True)
        sys.exit(1)

    click.echo(f"Retrieved metadata for: {metadata['title']}")

    # Get video transcript
    transcript = get_transcript(video_id)
    if not transcript:
        click.echo("Failed to fetch transcript. Exiting.", err=True)
        sys.exit(1)

    click.echo(f"Retrieved transcript with {len(transcript)} segments")

    # Create knowledge base directory if it doesn't exist
    os.makedirs(kb, exist_ok=True)

    # For now, just output basic info to verify everything works
    click.echo("Setup complete! Dependencies loaded successfully.")
    click.echo(f"Video: {metadata['title']}")
    click.echo(f"Channel: {metadata['channel']}")

    formatter = PrettyPrintFormatter()
    formatted_transcript = formatter.format_transcript(transcript)

    transcript_filename = f"{kb}/{video_id}_transcript.txt"
    with open(transcript_filename, "w", encoding="utf-8") as f:
        f.write(formatted_transcript)

    click.echo(f"Transcript saved to {transcript_filename}")

    full_text = transcript_to_text(transcript)
    click.echo(f"Full transcript length: {len(full_text)} characters")

    summary, organized = process_transcript(full_text, model)

    click.echo("\n--- TRANSCRIPT SUMMARY ---")
    click.echo(summary)
    click.echo("--- END SUMMARY ---\n")

    summary_filename = f"{kb}/{video_id}.md"
    with open(summary_filename, "w") as f:
        f.write(f"# {metadata['title']}\n\n")
        f.write(f"Video: https://www.youtube.com/watch?v={video_id}\n")
        f.write(f"Channel: {metadata['channel']}\n\n")
        f.write(summary)
        f.write("\n\n")
        f.write(organized)

    click.echo(f"Saved to {summary_filename}")


if __name__ == "__main__":
    main()
