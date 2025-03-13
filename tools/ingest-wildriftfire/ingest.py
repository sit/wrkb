import argparse
from pathlib import Path
import re
from champion import get_champions, parse_champion_details, write_champion_data


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

    # Create champions directory
    champions_dir = args.kb / "champions"
    champions_dir.mkdir(parents=True, exist_ok=True)

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


if __name__ == "__main__":
    main()
