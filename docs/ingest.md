# Wild Rift Knowledge Ingestion

This describes architecture of the set of tools needed to download and process
content from [content sources](sources.md) into our KB datastore.

## Core game data

This is information that is already captured in the WildRift Fandom wiki and
wildriftfire.com. We just need to grab it in a structured way and keep it up
to date as Riot evolves the game.

When we present this data, we should be able to provide links to the original
source content.

### Ingesting WildRiftFire 

We need to download information about all champions in a structured way. For
every champion listed on https://www.wildriftfire.com, we want to visit the
champion page (e.g., https://www.wildriftfire.com/guide/aatrox) and pull down
all the champion stats.

WildRiftFire uses a mixture of static HTML and jQuery to load HTML snippets
from the server for modals, where more information can be found (e.g., behind its "Show Champ Stats" button and level slider). We need to understand how that code
works so we can crawl it.

We must write data in a format so we can update this as the builds change.

## YouTube ingestion

We need to determine the type of video: is it a champion guide (with skill breakdown,
build breakdown, gameplay), a specific skill guide (where seeing the gameplay
associated with the voiceover is important), a general mindset and thinking guide
(where there is a gameplay shown but the content is really in the voiceover).

- We need to download subtitles (using yt-dlp or something similar).
- We need to clean and enhance the auto-generated subtitles to add proper
  punctuation, and correct any Wild Rift-specific terminology that was not
  properly transcribed. 
- We need to break down the video into concepts that can be tied into our
  KB. We want to be able to generate links to specific ranges of timestamps
  in the video.