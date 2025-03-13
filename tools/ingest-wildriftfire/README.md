# Ingest WildriftFire

One of the core aspects of our knowledge-base will be data
about champions, items, and runes.

## Usage

Connect to WildRiftFire and ingest the data.

### Basic Usage

To ingest all data (champions and runes):

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
```

### Individual Items

You can also ingest a specific champion or rune:

```bash
# Ingest a specific champion
uv run ingest.py --kb ../../kb --champion "Ahri"

# Ingest a specific rune
uv run ingest.py --kb ../../kb --rune "Electrocute"
```

### Command Line Options

- `--kb`, `-k`: Knowledge base directory path (default: kb)
- `--type`, `-t`: Type of data to ingest (champions, runes, or all)
- `--champion`, `-c`: Specific champion to update
- `--rune`, `-r`: Specific rune to update

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