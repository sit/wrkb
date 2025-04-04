import httpx
from bs4 import BeautifulSoup
import re
import yaml
from typing import Dict, Any, TextIO

# Constants
BASE_URL = "https://www.wildriftfire.com"
RUNE_LIST_URL = f"{BASE_URL}/rune-list"


def get_runes():
    """Extract basic rune information from the rune list page.

    This function scrapes the Wild Rift Fire rune tier list page to extract
    basic information about all available runes including their names, IDs,
    types (Keystone or Minor), and families (Domination, Resolve, etc).

    Returns:
        List[Dict[str, Any]]: List of dictionaries, each containing basic information
                             about a rune (id, name, type, family, image_url)
    """
    with httpx.Client() as client:
        response = client.get(RUNE_LIST_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        runes = []
        rune_elements = soup.select("div.ico-holder")

        for rune in rune_elements:
            # Extract ID from data attribute or class
            rune_id = None
            if rune.has_attr("data-id"):
                rune_id = int(rune["data-id"])
            else:
                # Try to extract from the tooltip class
                for cls in rune.get("class", []):
                    if "ajax-tooltip" in cls:
                        match = re.search(r"i:(\d+)", cls)
                        if match:
                            rune_id = int(match.group(1))
                            break

            if not rune_id:
                continue

            # Extract type and family
            rune_type = "Unknown"
            family = "Unknown"
            if rune.has_attr("data-sort"):
                sort_data = rune["data-sort"]

                # Determine type (Keystone or Minor)
                if "Keystone" in sort_data:
                    rune_type = "Keystone"
                elif "Minor" in sort_data:
                    rune_type = "Minor"

                # Extract family
                for potential_family in [
                    "Domination",
                    "Resolve",
                    "Inspiration",
                    "Precision",
                ]:
                    if potential_family in sort_data:
                        family = potential_family
                        break

            # Extract name
            name_span = rune.select_one("span")
            name = (
                name_span.get_text(strip=True)
                if name_span
                else f"Unknown Rune {rune_id}"
            )

            # Extract image URL
            img = rune.select_one("img")
            image_url = None
            if img and img.has_attr("src"):
                image_url = BASE_URL + img["src"]

            runes.append(
                {
                    "id": rune_id,
                    "name": name,
                    "type": rune_type,
                    "family": family,
                    "image_url": image_url,
                }
            )

        return runes


def parse_rune_details(rune_id: int, rune_name: str) -> Dict[str, Any]:
    """Fetch detailed information for a specific rune via the AJAX tooltip endpoint.

    This function fetches the detailed description and other metadata for a specific rune
    by accessing the AJAX tooltip endpoint at Wild Rift Fire. It parses the HTML response
    to extract relevant information like the full description and cooldown.

    Args:
        rune_id (int): The ID of the rune to fetch details for
        rune_name (str): The name of the rune (for verification)

    Returns:
        Dict[str, Any]: Dictionary containing detailed rune data including description,
                       cooldown (if available), and image URL
    """
    url = f"{BASE_URL}/ajax/tooltip?relation_type=Rune&relation_id={rune_id}"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Initialize the rune data structure
        rune_data = {
            "id": rune_id,
            "name": rune_name,
            "description": None,
            "cooldown": None,
            "type": None,
            "family": None,
            "image_url": None,
        }

        # Extract name from tooltip for verification
        title_element = soup.select_one("div.tt__info__title span")
        tooltip_name = title_element.get_text(strip=True) if title_element else None

        # Verify names match
        if tooltip_name and tooltip_name != rune_name:
            print(
                f"  Warning: Name mismatch between list ({rune_name}) and tooltip ({tooltip_name})"
            )

        # Extract description and cooldown
        desc_element = soup.select_one("div.tt__info__uniques span")
        if desc_element:
            full_text = desc_element.get_text(strip=True)
            rune_data["description"] = full_text

            # Try to extract cooldown if it exists
            cooldown_match = re.search(r"Cooldown:\s*([\d\-\.\s]+)", full_text)
            if cooldown_match:
                rune_data["cooldown"] = cooldown_match.group(1).strip()

        # Extract image URL
        img_element = soup.find("img")
        if img_element and img_element.has_attr("src"):
            rune_data["image_url"] = BASE_URL + img_element["src"]

        return rune_data


def write_rune_data(rune_data: Dict[str, Any], file: TextIO) -> None:
    """Write rune data to a markdown file with YAML frontmatter.

    This function formats the rune data as a markdown file with YAML frontmatter
    containing all the structured data. The markdown body provides a human-readable
    version of the same information.

    Args:
        rune_data (Dict[str, Any]): Rune data to write to the file
        file (TextIO): File handle to write the formatted data to
    """
    # Create frontmatter
    frontmatter = {
        "id": rune_data["id"],
        "name": rune_data["name"],
        "type": rune_data.get("type", "Unknown"),
        "family": rune_data.get("family", "Unknown"),
        "description": rune_data.get("description", ""),
        "image_url": rune_data.get("image_url", ""),
    }

    if rune_data.get("cooldown"):
        frontmatter["cooldown"] = rune_data["cooldown"]

    # Create markdown content
    markdown_content = f"""---
{yaml.dump(frontmatter, default_flow_style=False)}---

# {rune_data["name"]}

**Type:** {rune_data.get("type", "Unknown")}
**Family:** {rune_data.get("family", "Unknown")}

## Description

{rune_data.get("description", "")}

"""
    if rune_data.get("cooldown"):
        markdown_content += f"\n**Cooldown:** {rune_data['cooldown']} seconds\n"

    # Write to file
    file.write(markdown_content)
