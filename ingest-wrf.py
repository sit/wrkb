import argparse
from pathlib import Path
import re
from wildriftfire.champion import (
    get_champions,
    parse_champion_details,
    write_champion_data,
)
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


def _add_common_details(details, summary):
    """Adds common extra details from summary."""
    details["type"] = summary["type"]
    if not details.get("image_url") and summary.get("image_url"):
        details["image_url"] = summary["image_url"]


def _post_process_runes(rune_data, rune_summary):
    """Adds extra details to rune data from summary."""
    _add_common_details(rune_data, rune_summary)
    rune_data["family"] = rune_summary["family"]


def process_data(
    args,
    data_type_plural,
    data_type_singular,
    get_func,
    parse_func,
    write_func,
    post_process_hook=None,
    use_id=False,
):
    """Generic function to process data for champions, runes, or items."""
    # Create directory
    data_dir = args.kb / data_type_plural
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Processing {data_type_plural.capitalize()} ===")
    data_list = get_func()
    if not data_list:
        print(f"No {data_type_plural} found")
        return

    # Filter data if a specific one is requested
    specific_name = getattr(args, data_type_singular, None)
    if specific_name:
        data_list = [
            item for item in data_list if item["name"].lower() == specific_name.lower()
        ]
        if not data_list:
            print(f"{data_type_singular.capitalize()} '{specific_name}' not found")
            return

    # Process each item
    for i, item_summary in enumerate(data_list):
        name = item_summary["name"]

        if use_id:
            print(
                f"Processing {i + 1}/{len(data_list)}: {name} (ID: {item_summary['id']})"
            )
        else:
            print(f"Processing {name}...")

        try:
            # Get detailed information
            if use_id:
                item_details = parse_func(item_summary["id"], name)
            else:
                item_details = parse_func(item_summary["url"], name)

            if post_process_hook:
                post_process_hook(item_details, item_summary)

            # Construct output file path and write data
            output_file = data_dir / f"{sanitize_filename(name)}.md"
            with open(output_file, "w") as f:
                write_func(item_details, f)

            print(f"Successfully processed {name}")
        except Exception as e:
            print(f"Error processing {name}: {str(e)}")


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
        process_data(
            args,
            "champions",
            "champion",
            get_champions,
            parse_champion_details,
            write_champion_data,
        )

    # Process runes if requested
    if args.type in ["runes", "all"]:
        process_data(
            args,
            "runes",
            "rune",
            get_runes,
            parse_rune_details,
            write_rune_data,
            post_process_hook=_post_process_runes,
            use_id=True,
        )

    # Process items if requested
    if args.type in ["items", "all"]:
        process_data(
            args,
            "items",
            "item",
            get_items,
            parse_item_details,
            write_item_data,
            post_process_hook=_add_common_details,
            use_id=True,
        )




if __name__ == "__main__":
    main()
