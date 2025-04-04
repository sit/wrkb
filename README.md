# Wild Rift Knowledge Base

Wild Rift is an multiplayer online game with strategic and tactical elements.
Players need knowledge of game mechanics, macro and micro decision making skills.

This repository maintains a [knowledge base of information](kb/) that players need
to be successful at the game. It is intended to then also power systems that
can make this knowledge available to players.

- Discord Bot: Similar to what is offered by kapa.ai where people can ask questions
  and have an LLM answer.
- Skill ladder training website: Similar to gomagic.org/go-problems where players
  solve interactive problems to improve their decision-making, skill and knowledge.

## Tools

### Ingest WildRiftFire

ItzStu4rt's https://www.wildriftfire.com/ site is a great
resource for all information about champions and items.

```bash
# Ingest everything
uv run ingest-wrf.py --kb ../../kb

# Ingest only champions
uv run ingest.py --kb ../../kb --type champions

# Ingest only runes
uv run ingest.py --kb ../../kb --type runes

# Ingest only items
uv run ingest.py --kb ../../kb --type items

# Ingest a specific champion
uv run ingest.py --kb ../../kb --champion "Ahri"

# Ingest a specific rune
uv run ingest.py --kb ../../kb --rune "Electrocute"

# Ingest a specific item
uv run ingest.py --kb ../../kb --item "Infinity Edge"
```

Command line options:

- `--kb`, `-k`: Knowledge base directory path (default: kb)
- `--type`, `-t`: Type of data to ingest (champions, runes, items, or all)
- `--champion`, `-c`: Specific champion to update
- `--rune`, `-r`: Specific rune to update
- `--item`, `-i`: Specific item to update

### Ingest YouTube

There are many great YouTube videos that explain different aspects
of game play.

To run the script, use the following command:
```bash
uv run ingest-yt.py --video-id "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```
