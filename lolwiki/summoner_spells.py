"""Wild Rift summoner spells from the League of Legends Wiki.

All Wild Rift summoner spell data lives in one Lua data module on the wiki,
Module:SpellDataWR/data. We fetch its raw source, parse the table, and keep
the spells that can be picked on Summoner's Rift today.
"""

import re
from typing import Any, TextIO

import httpx
import yaml

from lolwiki.lua_table import parse_lua_table
from lolwiki.wikitext import to_plain_text

WIKI_BASE_URL = "https://wiki.leagueoflegends.com/en-us"
SPELL_MODULE_PAGE = "Module:SpellDataWR/data"
SPELL_MODULE_RAW_URL = f"{WIKI_BASE_URL}/{SPELL_MODULE_PAGE}?action=raw"
USER_AGENT = "wrkb-ingest/0.1"

# The module's map keys: "wr" is the 5v5 map, "ha" is ARAM.
MAP_NAMES = {"wr": "Summoner's Rift", "ha": "Howling Abyss"}

# Entries the module tracks alongside summoner spells that don't occupy a
# summoner spell slot.
NOT_SUMMONER_SPELLS = {"Recall", "Empowered Recall"}

_EFFECT_KEY = re.compile(r"^effect(\d*)$")


def fetch_spell_module() -> str:
    """Download the raw Lua source of Module:SpellDataWR/data."""
    response = httpx.get(
        SPELL_MODULE_RAW_URL,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def wiki_url(link: str) -> str:
    """Build a wiki URL from a module ``link`` value such as ``WR:Smite#Chilling_``."""
    return f"{WIKI_BASE_URL}/{link.replace(' ', '_')}"


def _number(value: str) -> int | float | str:
    if re.fullmatch(r"\d+", value):
        return int(value)
    if re.fullmatch(r"\d+\.\d+", value):
        return float(value)
    return value


def _effects(entry: dict[str, Any]) -> list[str]:
    numbered = []
    for key, value in entry.items():
        match = _EFFECT_KEY.match(str(key))
        if match and isinstance(value, str):
            numbered.append((int(match.group(1) or 1), value))
    return [to_plain_text(value) for _, value in sorted(numbered)]


def _spell_from_entry(key: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    paragraphs = [p for p in _effects(entry) if p]
    if not paragraphs:
        return None

    spell: dict[str, Any] = {
        "name": entry.get("disp_name") or key,
        "description": "\n\n".join(paragraphs),
        "maps": [
            MAP_NAMES[m] for m in MAP_NAMES if entry.get("maps", {}).get(m) is True
        ],
    }
    for field in ("cooldown", "recharge", "charges", "range"):
        if field in entry:
            value = to_plain_text(str(entry[field]))
            if value:
                spell[field] = value if field == "range" else _number(value)
    if entry.get("link"):
        spell["source_url"] = wiki_url(entry["link"])
    return spell


def parse_summoner_spells(module_text: str) -> list[dict[str, Any]]:
    """Extract current Wild Rift summoner spells from the module source.

    Skips spells the wiki marks as removed, spells not available on the
    Summoner's Rift map (ARAM-only event spells), non-slot entries such as
    Recall, and entries whose text is pulled from another template (Hexflash
    reads its text from the rune data, which this module doesn't carry).

    Args:
        module_text: Raw Lua source of Module:SpellDataWR/data.

    Returns:
        Spells sorted by name. Each has name, description, maps and, where
        the wiki gives them, cooldown, recharge, charges, range and source_url.
    """
    data = parse_lua_table(module_text)
    spells = []
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("removed") or key in NOT_SUMMONER_SPELLS:
            continue
        if entry.get("maps", {}).get("wr") is not True:
            continue
        spell = _spell_from_entry(key, entry)
        if spell is None:
            print(f"  Skipping {key}: no description in the data module")
            continue
        spells.append(spell)
    return sorted(spells, key=lambda s: s["name"])


def _seconds(value: float | str) -> str:
    return f"{value} seconds" if isinstance(value, (int, float)) else str(value)


def write_summoner_spell(spell: dict[str, Any], file: TextIO) -> None:
    """Write a summoner spell as Markdown with YAML frontmatter.

    Mirrors the layout of the WildRiftFire rune and item pages: structured
    data in the frontmatter, a readable summary and description in the body.
    """
    frontmatter = {
        key: spell[key]
        for key in (
            "name",
            "cooldown",
            "charges",
            "recharge",
            "range",
            "maps",
            "description",
            "source_url",
        )
        if key in spell
    }

    summary = []
    if "cooldown" in spell:
        summary.append(f"**Cooldown:** {_seconds(spell['cooldown'])}")
    if "charges" in spell:
        charges = f"**Charges:** {spell['charges']}"
        if "recharge" in spell:
            charges += f" ({spell['recharge']} second recharge)"
        summary.append(charges)
    if "range" in spell:
        summary.append(f"**Range:** {spell['range']}")
    if spell.get("maps"):
        summary.append(f"**Maps:** {', '.join(spell['maps'])}")

    body = f"\n# {spell['name']}\n\n"
    if summary:
        body += "  \n".join(summary) + "\n\n"
    # A lone line break in Markdown joins lines; keep the wiki's breaks
    # visible by making them paragraph breaks, except before list items.
    description = re.sub(r"(?<!\n)\n(?!\n|- )", "\n\n", spell["description"])
    body += f"## Description\n\n{description}\n"
    if "source_url" in spell:
        body += f"\nSource: [League of Legends Wiki]({spell['source_url']})\n"

    file.write(
        f"---\n{yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)}---\n"
        + body
    )
