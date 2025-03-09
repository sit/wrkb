import requests
from bs4 import BeautifulSoup
import argparse
from urllib.parse import urljoin

BASE_URL = "https://www.wildriftfire.com"


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


def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description="Ingest Wild Rift champion data")
    parser.add_argument(
        "--champion",
        "-c",
        help="Specific champion to update (default: all champions)",
        required=False,
    )
    args = parser.parse_args()

    url = "https://www.wildriftfire.com/"
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    champions = get_champions(soup, args.champion)

    if not champions:
        if args.champion:
            print(f"No champion found matching '{args.champion}'")
        else:
            print("No champions found")
        return

    # Print the extracted champion names
    for champion in champions:
        print(f"{champion['name']} - {champion['url']}")


if __name__ == "__main__":
    main()
