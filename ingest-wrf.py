import argparse
from pathlib import Path
import re
from wildriftfire.champion import get_champions, parse_champion_details, write_champion_data
from wildriftfire.runes import get_runes, parse_rune_details, write_rune_data
from wildriftfire.items import get_items, parse_item_details, write_item_data


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


def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Ingest Wild Rift data")
    parser.add_argument(
        "--champion",
        "-c",
        help="Specific champion to update (default: all champions)",
        required=False,
    )
    parser.add_argument(
        "--rune",
        "-r",
        help="Specific rune to update (default: all runes)",
        required=False,
    )
    parser.add_argument(
        "--item",
        "-i",
        help="Specific item to update (default: all items)",
        required=False,
    )
    parser.add_argument(
        "--type",
        "-t",
        help="Type of data to ingest (champions, runes, items, or all)",
        choices=["champions", "runes", "items", "all"],
        default="all",
    )
    parser.add_argument(
        "--kb",
        "-k",
        help="Knowledge base directory path (default: kb)",
        default="kb",
        type=Path,
    )
    args = parser.parse_args()

    # Process champions if requested
    if args.type in ["champions", "all"]:
        process_champions(args)

    # Process runes if requested
    if args.type in ["runes", "all"]:
        process_runes(args)

    # Process items if requested
    if args.type in ["items", "all"]:
        process_items(args)


def process_champions(args):
    """Process champion data based on command line arguments."""
    # Create champions directory
    champions_dir = args.kb / "champions"
    champions_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== Processing Champions ===")
    champions = get_champions()
    if not champions:
        print("No champions found")
        return

    # Filter champions if a specific one is requested
    if args.champion:
        champions = [
            champion
            for champion in champions
            if champion["name"].lower() == args.champion.lower()
        ]
        if not champions:
            print(f"Champion '{args.champion}' not found")
            return

    # Process each champion
    for champion in champions:
        print(f"Processing {champion['name']}...")
        try:
            champion_data = parse_champion_details(champion["url"], champion["name"])

            # Construct output file path and write data
            output_file = champions_dir / f"{sanitize_filename(champion['name'])}.md"
            with open(output_file, "w") as f:
                write_champion_data(champion_data, f)

            print(f"Successfully processed {champion['name']}")
        except Exception as e:
            print(f"Error processing {champion['name']}: {str(e)}")


def process_runes(args):
    """Process rune data based on command line arguments."""
    # Create runes directory
    runes_dir = args.kb / "runes"
    runes_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== Processing Runes ===")
    runes = get_runes()
    if not runes:
        print("No runes found")
        return

    # Filter runes if a specific one is requested
    if args.rune:
        runes = [rune for rune in runes if rune["name"].lower() == args.rune.lower()]
        if not runes:
            print(f"Rune '{args.rune}' not found")
            return

    # Process each rune
    for i, rune in enumerate(runes):
        print(f"Processing {i + 1}/{len(runes)}: {rune['name']} (ID: {rune['id']})")
        try:
            # Get detailed information
            rune_data = parse_rune_details(rune["id"], rune["name"])

            # Add additional data from the list
            rune_data["type"] = rune["type"]
            rune_data["family"] = rune["family"]
            if not rune_data["image_url"] and rune.get("image_url"):
                rune_data["image_url"] = rune["image_url"]

            # Construct output file path and write data
            output_file = runes_dir / f"{sanitize_filename(rune['name'])}.md"
            with open(output_file, "w") as f:
                write_rune_data(rune_data, f)

            print(f"Successfully processed {rune['name']}")
        except Exception as e:
            print(f"Error processing {rune['name']}: {str(e)}")


def process_items(args):
    """Process item data based on command line arguments."""
    # Create items directory
    items_dir = args.kb / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== Processing Items ===")
    items = get_items()
    if not items:
        print("No items found")
        return

    # Filter items if a specific one is requested
    if args.item:
        items = [item for item in items if item["name"].lower() == args.item.lower()]
        if not items:
            print(f"Item '{args.item}' not found")
            return

    # Process each item
    for i, item in enumerate(items):
        print(f"Processing {i + 1}/{len(items)}: {item['name']} (ID: {item['id']})")
        try:
            # Get detailed information
            item_data = parse_item_details(item["id"], item["name"])

            # Add additional data from the list
            item_data["type"] = item["type"]
            if not item_data["image_url"] and item.get("image_url"):
                item_data["image_url"] = item["image_url"]

            # Construct output file path and write data
            output_file = items_dir / f"{sanitize_filename(item['name'])}.md"
            with open(output_file, "w") as f:
                write_item_data(item_data, f)

            print(f"Successfully processed {item['name']}")
        except Exception as e:
            print(f"Error processing {item['name']}: {str(e)}")


if __name__ == "__main__":
    main()
