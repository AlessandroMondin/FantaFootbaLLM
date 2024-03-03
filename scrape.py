import json

from pymongo import MongoClient
import requests
from bs4 import BeautifulSoup, NavigableString

client = MongoClient("mongodb://localhost:27017/")
db = client["app_database"]
players_collection = db["players"]
championship_collection = db["serie_a_stats"]

HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
}

serie_a_teams = []
last_stored_matchday = championship_collection.find_one("current_matchday")
# first time app is used
if last_stored_matchday is None:
    last_stored_matchday = 1
    championship_collection.insert_one({"last_stored_matchday": 1})

url_teams = "https://www.fantacalcio.it/serie-a/classifica"

response = requests.get(url_teams, headers=HEADERS)
soup = BeautifulSoup(response.text, "html.parser")
teams = soup.find_all("a", "team-name team-link main ml-2")
games = soup.find_all("td", "played x3")
for team in teams:
    # get team name by subsetting url
    team = team["href"].split("/")[-1]
    # the html contains duplicated (maybe mobile version?)
    if team not in serie_a_teams:
        serie_a_teams.append(team)

current_matchday = 0
for game in games:
    # get team name by subsetting url
    game = game.text
    # try to convert string match day to int.
    # In case it would not be possible, we skit
    # to the next tag.
    try:
        game = int(game)
    except:
        continue
    current_matchday = max(game, current_matchday)


while last_stored_matchday < current_matchday:
    for team in serie_a_teams:

        url = (
            f"https://www.fantacalcio.it/pagelle/2023-24/{team}/{last_stored_matchday}"
        )

        # Retrieve webpage
        response = requests.get(url)

        # Parse the content with Beautiful Soup
        soup = BeautifulSoup(response.text, "html.parser")

        # Initialize a list to hold all player data

        report = soup.find("div", class_="report-list")

        for container in report.children:
            # Skip any NavigableString objects, which are not tags
            if isinstance(container, NavigableString):
                continue

            team = url.split("/")[-2]
            player_name_tag = container.find("a", "player-name")
            # some of the children tags do not contain players information
            # and therefore we skip them.
            if player_name_tag is None:
                continue
            player_name = player_name_tag.text.replace("\n", "")
            adjective_performance = container.find("h3", "text-primary").text.replace(
                "\n", ""
            )
            grade = container.find("div", class_="badge grade").text
            description = ""
            description_paragraphs = container.select("div.col p")
            for desc_tag in description_paragraphs:
                description += desc_tag.text
            bonus_malus = []
            for b_m in container.find_all("figure", class_="icon bonus-icon"):
                # Extracting the title and data-value, if data-value is not available it defaults to None
                title = b_m.get("title", "").strip()
                value = b_m.get("data-value", None)
                bonus_malus.append({"title": title, "value": value})

            players_collection.update_one(
                {"name": player_name},
                {
                    "$push": {
                        "matchStats": {
                            "matchday": last_stored_matchday,
                            "adjective_performance": adjective_performance,
                            "grade": grade,
                            "bonus_malus": bonus_malus,
                            "description": description,
                        }
                    }
                },
                upsert=True,
            )

    last_stored_matchday += 1

championship_collection.update_one(
    {"last_stored_matchday": last_stored_matchday}, upsert=True
)

# Define the filename for the JSON file
filename = "players_data.json"

# Write the data to a JSON file
with open(filename, "w") as file:
    json.dump(players_data, file, ensure_ascii=False, indent=4)

print(f"Data successfully written to {filename}")
