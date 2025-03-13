import httpx
from bs4 import BeautifulSoup
import argparse
from pathlib import Path

from champion import get_champions, parse_champion_details, write_champion_data

BASE_URL = "https://www.wildriftfire.com"


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

    with httpx.Client() as client:
        response = client.get(BASE_URL)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        champions = get_champions(soup, BASE_URL)

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
            write_champion_data(champion_data, args.kb)
            print(f"Successfully processed {champion['name']}")
        except Exception as e:
            print(f"Error processing {champion['name']}: {str(e)}")


if __name__ == "__main__":
    main()
