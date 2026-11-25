"""Ingest Wild Rift data from the League of Legends Wiki into the knowledge base."""

import argparse
from pathlib import Path

from lib.kb import sanitize_filename
from lolwiki.summoner_spells import (
    fetch_spell_module,
    parse_summoner_spells,
    write_summoner_spell,
)

SUMMONER_SPELLS_DIR = "summoner-spells"


def ingest_summoner_spells(kb: Path, module_text: str, only: str | None = None) -> None:
    """Write one page per summoner spell under ``kb/summoner-spells``.

    A full run also removes pages for spells the wiki no longer lists; a run
    limited to one spell touches only that spell's page.
    """
    out_dir = kb / SUMMONER_SPELLS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    spells = parse_summoner_spells(module_text)
    if only:
        spells = [s for s in spells if s["name"].lower() == only.lower()]
        if not spells:
            print(f"Summoner spell '{only}' not found")
            return

    print(f"\n=== Processing Summoner Spells ({len(spells)}) ===")
    expected = set()
    for spell in spells:
        filename = f"{sanitize_filename(spell['name'])}.md"
        expected.add(filename)
        with open(out_dir / filename, "w") as f:
            write_summoner_spell(spell, f)
        print(f"Wrote {spell['name']}")

    if only:
        return
    for stale in sorted({p.name for p in out_dir.glob("*.md")} - expected):
        (out_dir / stale).unlink()
        print(f"Removed stale summoner spell: {stale}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Wild Rift data from the League of Legends Wiki"
    )
    parser.add_argument(
        "--kb",
        "-k",
        help="Knowledge base directory path (default: kb)",
        default="kb",
        type=Path,
    )
    parser.add_argument(
        "--spell",
        "-s",
        help="Specific summoner spell to update (default: all summoner spells)",
    )
    parser.add_argument(
        "--module-file",
        help="Read Module:SpellDataWR/data from this file instead of the wiki",
        type=Path,
    )
    args = parser.parse_args()

    if args.module_file:
        module_text = args.module_file.read_text()
    else:
        module_text = fetch_spell_module()
    ingest_summoner_spells(args.kb, module_text, args.spell)


if __name__ == "__main__":
    main()
