# Ingest WildriftFire

One of the core aspects of our knowledge-base will be data
about champions, items, and runes.

## Usage

Connect to WildRiftFire and ingest the data.

### Basic Usage

To ingest all data (champions, runes, and items):

```bash
uv run ingest.py --kb ../../kb
```

### Specific Data Types

You can specify what type of data to ingest:

```bash
# Ingest only champions
uv run ingest.py --kb ../../kb --type champions

# Ingest only runes
uv run ingest.py --kb ../../kb --type runes

# Ingest only items
uv run ingest.py --kb ../../kb --type items
```

### Individual Items

You can also ingest a specific champion, rune, or item:

```bash
# Ingest a specific champion
uv run ingest.py --kb ../../kb --champion "Ahri"

# Ingest a specific rune
uv run ingest.py --kb ../../kb --rune "Electrocute"

# Ingest a specific item
uv run ingest.py --kb ../../kb --item "Infinity Edge"
```

### Command Line Options

- `--kb`, `-k`: Knowledge base directory path (default: kb)
- `--type`, `-t`: Type of data to ingest (champions, runes, items, or all)
- `--champion`, `-c`: Specific champion to update
- `--rune`, `-r`: Specific rune to update
- `--item`, `-i`: Specific item to update

## Data Structure

The tool creates markdown files with YAML frontmatter containing the data.

### Champions

Champion files include:
- Base stats and their growth values
- Abilities with descriptions
- Cooldowns and costs for abilities
- Champion roles

### Runes

Rune files include:
- Type (Keystone or Minor)
- Family (Domination, Resolve, Inspiration, Precision)
- Description and effects
- Cooldown information when available

### Items

Item files include:
- Type (Physical, Magic, Defense, Boots, Enchant)
- Cost in gold
- Item stats (e.g., +40 Attack Damage)
- Passive and active effects
- Description of unique abilities