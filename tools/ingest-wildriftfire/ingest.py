import requests
from bs4 import BeautifulSoup


def main():
    url = "https://www.wildriftfire.com/"
    response = requests.get(url)
    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

    soup = BeautifulSoup(response.content, "html.parser")

    # Find the champion grid div using its specific class
    champion_section = soup.find("div", class_="wf-home__champions wm")
    if champion_section:
        champion_links = champion_section.find_all("a")
        champions = []
        for link in champion_links:
            champion_name = link.get_text(strip=True)
            champion_url = link.get("href")
            if champion_name and champion_url:  # Ensure we have both name and URL
                champions.append({"name": champion_name, "url": champion_url})

        # Print the extracted champion names
        for champion in champions:
            print(f"{champion['name']} - {champion['url']}")
    else:
        print("Error: Could not find champion grid section on the page")


if __name__ == "__main__":
    main()
