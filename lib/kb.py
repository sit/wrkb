"""Helpers shared by the scripts that write into the knowledge base."""

import re


def sanitize_filename(name: str) -> str:
    """Convert a name into a safe filename stem: lowercase, dashes for spaces."""
    name = name.lower().replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-_]", "", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")
