import httpx
from bs4 import BeautifulSoup
import argparse
from urllib.parse import urljoin
import yaml
from pathlib import Path
import re

BASE_URL = "https://www.wildriftfire.com"


def sanitize_filename(name):
    """Convert a string into a safe filename by removing special characters and converting spaces to dashes."""
    # Convert to lowercase
    name = name.lower()
    # Replace spaces with dashes
    name = name.replace(" ", "-")
    # Remove any characters that aren't alphanumeric, dash, or underscore
    name = re.sub(r"[^a-z0-9\-_]", "", name)
    # Replace multiple dashes with single dash
    name = re.sub(r"-+", "-", name)
    # Remove leading/trailing dashes
    name = name.strip("-")
    return name


def get_champions(soup, target_champion=None):
    # Find the champion grid div using its specific class
    champion_section = soup.find("div", class_="wf-home__champions wm")
    if champion_section:
        champion_links = champion_section.find_all("a")
        champions = []
        for link in champion_links:
            champion_name = link.get_text(strip=True)
            champion_url = link.get("href")
            if champion_name and champion_url:  # Ensure we have both name and URL
                # If a target champion is specified, only include if it matches
                if (
                    not target_champion
                    or champion_name.lower() == target_champion.lower()
                ):
                    champions.append(
                        {"name": champion_name, "url": urljoin(BASE_URL, champion_url)}
                    )
        return champions
    else:
        print("Error: Could not find champion grid section on the page")
        return []


def parse_champion_details(url, champion_name):
    """Parse champion details from their specific page and return structured data."""
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Get champion roles
        roles = []
        desc_div = soup.find("div", class_="champion__desc")
        if desc_div:
            lane_images = desc_div.find_all("img", class_="lane")
            roles = [
                img.get("alt", "").strip() for img in lane_images if img.get("alt")
            ]

        # Get base stats
        stats_section = soup.find("div", class_="statsBlock champion")
        base_stats = {}
        if stats_section:
            stat_blocks = stats_section.find_all("div", class_="statsBlock__block")
            for block in stat_blocks:
                # Get the stat name from the first span
                stat_name = (
                    block.find("span").get_text(strip=True)
                    if block.find("span")
                    else None
                )
                # Get the stat value span which has data attributes
                stat_value_span = block.find("span", attrs={"data-base": True})
                if stat_name and stat_value_span:
                    base_value = stat_value_span.get("data-base")
                    growth_value = stat_value_span.get("data-increase")
                    base_stats[stat_name] = {"base": base_value, "growth": growth_value}

        # Get abilities
        abilities = []
        abilities_section = soup.find("div", class_="statsBlock abilities")
        if abilities_section:
            ability_blocks = abilities_section.find_all(
                "div", class_="statsBlock__block"
            )
            for block in ability_blocks:
                upper = block.find("div", class_="upper")
                lower = block.find("div", class_="lower")

                if not upper or not lower:
                    continue

                # Get ability slot and name
                name_div = upper.find("div", class_="name")
                if name_div:
                    slot_span = name_div.find("span")
                    slot = slot_span.get_text(strip=True) if slot_span else ""
                    # Get name by removing the slot text from the full text
                    full_text = name_div.get_text(strip=True)
                    name = full_text[len(slot) :].strip() if slot else full_text

                # Get cooldowns if they exist
                cooldown_div = upper.find("div", class_="cooldown")
                cooldowns = None
                if cooldown_div:
                    cooldown_spans = cooldown_div.find_all("span")
                    cooldowns = []
                    for span in cooldown_spans:
                        try:
                            value = span.get_text(strip=True)
                            cooldowns.append(float(value))
                        except (ValueError, TypeError):
                            continue
                    if not cooldowns:  # If we couldn't parse any values, set to None
                        cooldowns = None

                # Get costs if they exist
                cost_div = upper.find("div", class_="cost")
                costs = None
                if cost_div:
                    cost_spans = cost_div.find_all("span")
                    costs = []
                    for span in cost_spans:
                        try:
                            value = span.get_text(strip=True)
                            costs.append(float(value))
                        except (ValueError, TypeError):
                            continue
                    if not costs:  # If we couldn't parse any values, set to None
                        costs = None

                # Get description
                description = lower.get_text(" ", strip=True) if lower else ""

                ability_data = {
                    "slot": slot,
                    "name": name,
                    "description": description,
                }

                if cooldowns:
                    ability_data["cooldowns"] = cooldowns
                if costs:
                    ability_data["costs"] = costs

                abilities.append(ability_data)

        # Prepare frontmatter data
        champion_data = {
            "name": champion_name,
            "source_url": url,
            "roles": roles,
            "base_stats": base_stats,
            "abilities": abilities,
        }

        return champion_data


def write_champion_data(champion_data, kb_dir):
    """Write champion data to a markdown file with frontmatter.

    Args:
        champion_data (dict): Champion data to write
        kb_dir (Path): Directory path where champion data should be stored
    """
    champions_dir = kb_dir / "champions"
    champions_dir.mkdir(parents=True, exist_ok=True)

    filename = sanitize_filename(champion_data["name"]) + ".md"
    output_file = champions_dir / filename

    # Create markdown content with frontmatter
    frontmatter = yaml.dump(champion_data, default_flow_style=False)
    markdown_content = f"""---
{frontmatter}---

# {champion_data["name"]}

## Roles

{", ".join(champion_data["roles"])}

## Base Stats

"""
    # Add formatted base stats with both base and growth values
    for stat, values in champion_data["base_stats"].items():
        markdown_content += (
            f"- {stat}: {values['base']} (+{values['growth']} per level)\n"
        )

    markdown_content += "\n## Abilities\n\n"

    # Add formatted abilities with all details
    for ability in champion_data["abilities"]:
        # Format ability header with slot and name
        markdown_content += f"### [{ability['slot']}] {ability['name']}\n\n"

        # Add cooldowns if they exist
        if "cooldowns" in ability:
            cooldowns_str = " / ".join(str(cd) for cd in ability["cooldowns"])
            markdown_content += f"**Cooldown:** {cooldowns_str} seconds\n\n"

        # Add costs if they exist
        if "costs" in ability:
            costs_str = " / ".join(str(cost) for cost in ability["costs"])
            markdown_content += f"**Cost:** {costs_str}\n\n"

        # Add description
        markdown_content += f"{ability['description']}\n\n"

    # Write to file
    with open(output_file, "w") as f:
        f.write(markdown_content)


def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Ingest Wild Rift champion data")
    parser.add_argument(
        "--champion",
        "-c",
        help="Specific champion to update (default: all champions)",
        required=False,
    )
    parser.add_argument(
        "--kb",
        "-k",
        help="Knowledge base directory path (default: kb)",
        default="kb",
        type=Path,
    )
    args = parser.parse_args()

    url = "https://www.wildriftfire.com/"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        champions = get_champions(soup, args.champion)

    if not champions:
        print("No champions found")
        return
    if args.champion:
        champions = [
            champion
            for champion in champions
            if champion["name"].lower() == args.champion.lower()
        ]

    # Process each champion
    for champion in champions:
        print(f"Processing {champion['name']}...")
        try:
            champion_data = parse_champion_details(champion["url"], champion["name"])
            write_champion_data(champion_data, args.kb_dir)
            print(f"Successfully processed {champion['name']}")
        except Exception as e:
            print(f"Error processing {champion['name']}: {str(e)}")


if __name__ == "__main__":
    main()
