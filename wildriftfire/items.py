import httpx
from bs4 import BeautifulSoup
import re
import yaml
from typing import Dict, Any, TextIO

# Constants
BASE_URL = "https://www.wildriftfire.com"
ITEM_LIST_URL = f"{BASE_URL}/item-list"


def get_items():
    """Extract basic item information from the item list page.

    This function scrapes the Wild Rift Fire item tier list page to extract
    basic information about all available items including their names, IDs,
    and types (Physical, Magic, Defense, Boots, Enchant).

    Returns:
        List[Dict[str, Any]]: List of dictionaries, each containing basic information
                             about an item (id, name, type, image_url)
    """
    with httpx.Client() as client:
        response = client.get(ITEM_LIST_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        items = []

        # Find the tier blocks within the tier list section
        tier_blocks = soup.select("div.wf-tier-list__tiers__block")

        for block in tier_blocks:
            # Each block contains a tier class (s, a, b, c, d)
            tier_divs = block.select("div.tier")

            for tier_div in tier_divs:
                # Find all items in this tier (we don't care about the tier now)
                item_elements = tier_div.select("div.ico-holder")

                for item in item_elements:
                    # Extract ID from data attribute or class
                    item_id = None
                    if item.has_attr("data-id"):
                        item_id = int(item["data-id"])
                    else:
                        # Try to extract from the tooltip class
                        for cls in item.get("class", []):
                            if "ajax-tooltip" in cls:
                                match = re.search(r"i:(\d+)", cls)
                                if match:
                                    item_id = int(match.group(1))
                                    break

                    if not item_id:
                        continue

                    # Extract type
                    item_type = "Unknown"
                    if item.has_attr("data-sort"):
                        item_type = item["data-sort"]
                    else:
                        # Try to infer from the item-holder class
                        holder_div = item.select_one("div.item-holder")
                        if holder_div:
                            holder_class = holder_div.get("class", [])
                            if holder_class and len(holder_class) > 0:
                                potential_type = holder_class[0]
                                if potential_type in [
                                    "Physical",
                                    "Magic",
                                    "Defense",
                                    "Boots",
                                    "Enchantment",
                                ]:
                                    item_type = potential_type

                    # Extract name
                    name_span = item.select_one("span")
                    name = (
                        name_span.get_text(strip=True)
                        if name_span
                        else f"Unknown Item {item_id}"
                    )

                    # Extract image URL
                    img = item.select_one("img")
                    image_url = None
                    if img and img.has_attr("src"):
                        image_url = BASE_URL + img["src"]

                    items.append(
                        {
                            "id": item_id,
                            "name": name,
                            "type": item_type,
                            "image_url": image_url,
                        }
                    )

        return items


def parse_item_details(item_id: int, item_name: str) -> Dict[str, Any]:
    """Fetch detailed information for a specific item via the AJAX tooltip endpoint.

    This function fetches the detailed description and other metadata for a specific item
    by accessing the AJAX tooltip endpoint at Wild Rift Fire. It parses the HTML response
    to extract relevant information like stats, passive effects, and active abilities.

    Args:
        item_id (int): The ID of the item to fetch details for
        item_name (str): The name of the item (for verification)

    Returns:
        Dict[str, Any]: Dictionary containing detailed item data including description,
                       stats, effects, and cost
    """
    url = f"{BASE_URL}/ajax/tooltip?relation_type=Item&relation_id={item_id}"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Initialize the item data structure
        item_data = {
            "id": item_id,
            "name": item_name,
            "description": None,
            "stats": [],
            "effects": [],
            "cost": None,
            "type": None,
            "image_url": None,
        }

        # Extract name from tooltip for verification
        title_element = soup.select_one("div.tt__info__title span")
        tooltip_name = title_element.get_text(strip=True) if title_element else None

        # Verify names match
        if tooltip_name and tooltip_name != item_name:
            print(
                f"  Warning: Name mismatch between list ({item_name}) and tooltip ({tooltip_name})"
            )

        # Extract cost using the correct element
        cost_element = soup.select_one("div.tt__info__cost span")
        if cost_element:
            cost_text = cost_element.get_text(strip=True)
            try:
                item_data["cost"] = int(cost_text)
            except ValueError:
                # Try to extract digits only
                cost_match = re.search(r"(\d+)", cost_text)
                if cost_match:
                    item_data["cost"] = int(cost_match.group(1))

        # Extract stats - handle parent span elements
        stats_parent_elements = soup.select("div.tt__info__stats > span")
        for parent_span in stats_parent_elements:
            # Get the text with all children
            full_text = parent_span.get_text()
            if full_text:
                item_data["stats"].append(full_text)

        # Extract effects
        effects_elements = soup.select("div.tt__info__uniques span")
        for element in effects_elements:
            text = element.get_text()
            if text:
                item_data["effects"].append(text)

        # If there are effects, join them into a description
        if item_data["effects"]:
            item_data["description"] = "\n\n".join(item_data["effects"])

        # Extract image URL
        img_element = soup.find("img")
        if img_element and img_element.has_attr("src"):
            item_data["image_url"] = BASE_URL + img_element["src"]

        return item_data


def write_item_data(item_data: Dict[str, Any], file: TextIO) -> None:
    """Write item data to a markdown file with YAML frontmatter.

    This function formats the item data as a markdown file with YAML frontmatter
    containing all the structured data. The markdown body provides a human-readable
    version of the same information.

    Args:
        item_data (Dict[str, Any]): Item data to write to the file
        file (TextIO): File handle to write the formatted data to
    """
    # Create frontmatter
    frontmatter = {
        "id": item_data["id"],
        "name": item_data["name"],
        "type": item_data.get("type", "Unknown"),
        "cost": item_data.get("cost"),
        "stats": item_data.get("stats", []),
        "effects": item_data.get("effects", []),
        "image_url": item_data.get("image_url", ""),
    }

    # Create markdown content
    markdown_content = f"""---
{yaml.dump(frontmatter, default_flow_style=False)}---

# {item_data["name"]}

**Type:** {item_data.get("type", "Unknown")}  
"""

    if item_data.get("cost"):
        markdown_content += f"**Cost:** {item_data['cost']} gold\n\n"

    if item_data.get("stats"):
        markdown_content += "## Stats\n\n"
        for stat in item_data["stats"]:
            markdown_content += f"- {stat}\n"
        markdown_content += "\n"

    if item_data.get("description"):
        markdown_content += "## Effects\n\n"
        markdown_content += f"{item_data['description']}\n\n"

    # Write to file
    file.write(markdown_content)
