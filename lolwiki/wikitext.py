"""Render League of Legends Wiki wikitext as plain text.

The wiki's data modules hold descriptions written with the wiki's own
templates ({{as|...}}, {{pp|...}}, {{WRtip|...}}, ...). We expand the ones
the Wild Rift data uses into readable text and drop the rest.
"""

import re
from collections.abc import Callable

# Innermost template: no braces inside, so nested templates expand inside-out.
_TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")
_NAMED_PARAM = re.compile(r"^\s*([\w ]+?)\s*=(.*)$", re.DOTALL)
_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_PP_RANGE = re.compile(r"^\s*(\S+)\s+to\s+(\S+)(?:\s+for\s+\d+)?\s*$")


def _split_params(body: str) -> tuple[str, list[str], dict[str, str]]:
    parts = body.split("|")
    name = parts[0].strip()
    positional: list[str] = []
    named: dict[str, str] = {}
    for part in parts[1:]:
        match = _NAMED_PARAM.match(part)
        if match:
            named[match.group(1).strip()] = match.group(2).strip()
        else:
            positional.append(part.strip())
    return name, positional, named


def _first(positional: list[str], named: dict[str, str]) -> str:
    return positional[0] if positional else ""


def _last(positional: list[str], named: dict[str, str]) -> str:
    return positional[-1] if positional else ""


def _tip(positional: list[str], named: dict[str, str]) -> str:
    if named.get("icononly", "").lower() == "true":
        return ""
    return _last(positional[:2], named)


def _scaling(positional: list[str], named: dict[str, str]) -> str:
    """{{pp|A to B for N|...}}: a value that scales with level or another input."""
    if not positional:
        return ""
    match = _PP_RANGE.match(positional[0])
    if not match:
        return positional[0]
    key = named.get("key", "")
    low, high = match.group(1) + key, match.group(2) + key
    basis = named.get("type") or "level"
    return f"{low} - {high} (based on {basis})"


def _gold(positional: list[str], named: dict[str, str]) -> str:
    return f"{_first(positional, named)} gold"


_HANDLERS: dict[str, Callable[[list[str], dict[str, str]], str]] = {
    "as": _first,
    "ccib": _last,
    "fd": _first,
    "g": _gold,
    "pp": _scaling,
    "sbc": _first,
    "sti": lambda p, n: _last(p[:2], n),
    "tt": _first,
    "WRs": _first,
    "WRtip": _tip,
}


def _expand(match: re.Match[str]) -> str:
    name, positional, named = _split_params(match.group(1))
    handler = _HANDLERS.get(name)
    return handler(positional, named) if handler else ""


def to_plain_text(wikitext: str) -> str:
    """Convert wiki markup to plain text, keeping list items as ``- `` lines.

    Unknown templates expand to nothing, since they usually pull content from
    elsewhere on the wiki that we can't resolve here.
    """
    text = wikitext
    while True:
        expanded = _TEMPLATE.sub(_expand, text)
        if expanded == text:
            break
        text = expanded

    text = _LINK.sub(r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li>", "\n- ", text)
    text = re.sub(r"</?ul>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)
