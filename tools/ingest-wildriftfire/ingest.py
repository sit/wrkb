import requests
from bs4 import BeautifulSoup


def main():
    url = "https://www.wildriftfire.com/"
    response = requests.get(url)
    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

    soup = BeautifulSoup(response.content, "html.parser")

    # Find the section containing champion links.  The provided HTML has two sections with champion links.
    # This selects the first one, which appears to be more comprehensive.
    champion_section = soup.find("div", string="Wild Rift Champion Build Guides").find_parent()

    # Extract champion names from the links
    champion_names = [a.text for a in champion_section.find_all("a")]

    # Print the extracted champion names
    for champion in champion_names:
        print(champion)


if __name__ == "__main__":
    main()
