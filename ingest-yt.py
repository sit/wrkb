#!/usr/bin/env python

"""
Ingest YouTube videos about WildRift and turn them into structured Markdown files.

This tool downloads YouTube transcripts, cleans them up using Wild Rift terminology,
and creates a well-structured Markdown file with proper sections and timestamp links.
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from typing import Optional

import click
from google import genai

from lib.transcript import Sentence
from lib.video import Video, VideoManager


def sentence_transcript(video: Video, chat: genai.chats.Chat) -> tuple:
    start = time.monotonic()
    sentences_prompt = f"""
You are an experienced writer and editor. Your task today is to work with a raw transcript from
a YouTube video. The transcript is provided below as a JSON dictionary with following keys:
- video_id: The YouTube video ID
- metadata: Dictionary containing video metadata such as title, channel, upload_date, duration, etc.
- transcript: List of segments dicts, each with 'text', 'start', and 'duration' fields

<VIDEO>
{video.to_dict()}
</VIDEO>

Your job is to take the segments in the transcript and turn them into sentences.
Each sentence should be properly capitalized and punctuated. Because the transcript is spoken language,
you may need to take some small liberties with the text to make it more readable. For example,
filler words such as "um", "like", "you know" should be removed. Places where the speaker may have
corrected themselves they said should also be removed.

The output should be a list of Sentence objects, each with a text property and a segments property.
The segments property is a list of Segment objects that are taken directly from the input transcript.
The output should cover the entire transcript. Every segment from the input transcript should be included,
even if it was cleaned up to remove filler or thinking words.
"""

    sentences_response = chat.send_message(
        sentences_prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list[Sentence],
        },
    )
    sentences = sentences_response.text
    end = time.monotonic()

    return sentences, timedelta(seconds=end - start)


def organize_transcript(
    video: Video, chat: genai.chats.Chat, continuation: Optional[str] = ""
) -> tuple:
    video_id = video.video_id
    organize_prompt = f"""{continuation}
Now as an experienced copy-writer, with expertise in Wild Rift,
transform the sentences into an well-formatted article.

Important requirements:
- Correct any mistakes in the transcription. There are often errors where the transcription
software misinterprets the names of champions, items, abilities, and runes. Make
sure to check for names that are in Wild Rift (e.g. not in PC League of Legends)
and correct them. Sometimes an ungrammatical sentence may indicate a mistake;
correct names can often be inferred from context. Don't introduce any names
that are not in the transcript.
- Eliminate any promotional language (e.g., sponsor advertisements, requests to like/subscribe, participate in contests, etc.)
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

The timestamps in the transcript are in the format [MM:SS.MMM --> MM:SS.MMM] and represent start and end times in minutes:seconds.milliseconds.
Convert these to seconds for the YouTube links (e.g., 2:30 would be 150s in the link).

Provide the article only, do not add any other explanation or commentary
before or after the result. Do not add any wrapping tags or other markup
outside of the article.
"""

    organize_start = time.monotonic()
    organize_response = chat.send_message(organize_prompt)
    organized = organize_response.text
    organize_end = time.monotonic()

    return organized, timedelta(seconds=organize_end - organize_start)


def summarize_transcript(video: Video, chat: genai.chats.Chat) -> tuple:
    summary_start = time.monotonic()
    summary_prompt = """
Provide a concise summary of no more than 300 words that captures the main points of the video, using the same
organizational structure as the organized article you just wrote. The summary should be output in Markdown format.
- Start with 2-3 sentences that provide an overview of the video.
- Use bullets to create nested lists representing the sections and sub-sections of the organized article.
- Each top-level non-intro/conclusion section should have one bullet.
- There should be at most 3 sub-bullets, one-level deep to describe each section. It will be necessary to
  summarize in order to highlight the value.
- Make sure the bullets are concise.
- Do not embellish the content with anything not directly stated in the transcript.

Return the summary only, do not add any other explanation or commentary before or after the result.
"""
    # Execute the summary prompt
    summary_response = chat.send_message(summary_prompt)

    summary = summary_response.text

    summary_end = time.monotonic()
    return summary, timedelta(seconds=summary_end - summary_start)


def process_video(
    video: Video, client: genai.Client, model_name: str, sentences: Optional[str] = None
) -> tuple:
    """
    Process the transcript using the Google Genai SDK.

    Returns a summary of the transcript, and an organized article.
    """
    click.echo(f"Summarizing transcript using {model_name}...")

    # Create a chat for sequential prompts
    chat = client.chats.create(model=model_name)

    continuation = ""
    if not sentences:
        sentences, sentence_time = sentence_transcript(video, chat)
        click.echo(f"Sentences generated in {sentence_time}")
    else:
        continuation = f"""
Take the following JSON list of sentences that have been assembled from a YouTube video transcript organized
as segments. This is a list of Sentence objects, each with a text property and a segments list.
The segments property is a list of Segment objects that are taken directly from the input transcript.

<SENTENCES>
{sentences}
</SENTENCES>
"""
        click.echo("Using previously loaded sentences")
    organized, organize_time = organize_transcript(video, chat, continuation)
    click.echo(f"Organized in {organize_time}")
    summary, summary_time = summarize_transcript(video, chat)
    click.echo(f"Summary generated in {summary_time}")

    return sentences, summary, organized


@click.command()
@click.option("--video-id", required=True, help="YouTube video ID or URL")
@click.option(
    "--kb",
    "-k",
    default="videos",
    help="Knowledge base directory to save the output file",
)
@click.option(
    "--model",
    "-m",
    default="gemini-2.5-flash-lite-preview-06-17",
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
    click.echo("Metadata:")
    for key, value in video.metadata.items():
        click.echo(f"  {key}: {value}")

    # Where sentences are stored
    sentences_filename = f"{kb}/{video.video_id}-sentences.md"
    # If we have sentences cached, read them instead of computing them
    sentences = None
    if os.path.exists(sentences_filename):
        with open(sentences_filename, "r") as f:
            sentences = f.read()

    # Process the video transcript
    sentences, summary, organized = process_video(
        video, client, model, sentences=sentences
    )

    click.echo("\n--- TRANSCRIPT SUMMARY ---")
    click.echo(summary)
    click.echo("--- END SUMMARY ---\n")

    # Format upload date nicely if available
    formatted_date = video.formatted_upload_date
    formatted_duration = video.formatted_duration

    # Write sentences to file
    sentences_filename = f"{kb}/{video.video_id}-sentences.md"
    with open(sentences_filename, "w") as f:
        f.write(sentences)

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
