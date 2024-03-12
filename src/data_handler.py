import time
from typing import List, Dict, Generator, Tuple, Union
import yaml

import chromedriver_autoinstaller
import requests
import ssl

from bs4 import BeautifulSoup
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


from utils import scrape_error_handler

# certificate to download chrome driver
ssl._create_default_https_context = ssl._create_stdlib_context

# Load the YAML file
with open("src/bonus_malus.yaml", "r") as file:
    data = yaml.safe_load(file)

bonus_malus_table = data["bonus_malus_table"]

# IMPROVEMENT:
# Integrate FantaMaster forecast: https://www.fantamaster.it/probabili-formazioni-25-giornata-seriea-2023-2024-news/
# Integrate Mediaset player and match stats: https://www.sportmediaset.mediaset.it/pagelle/2023/serie-a/

# TODO
# FIX CAMPIONCINO DI PARDO
# Add all players to serie_a_stats
# Add user player in some collection
# How to match names? fuzzy?


class SerieADatabaseManager:
    """
    Class used to scrape information on Leghe Serie A and to store them into MongoDB.
    """

    HEADERS = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
    }
    MONGO_DB_NAME = "FantaCalcioLLM"
    MONGO_DB_SERIE_A_GEN_INFO = "user_serie_a_info"
    MONGO_DB_PLAYER_INFO = "players"
    MONGO_DB_NEXT_MATCH_FORECAST = "forecast_match_day"

    url_serie_a_gen_info = "https://www.fantacalcio.it/serie-a/classifica"
    url_players = "https://www.fantacalcio.it/serie-a/squadre"
    past_matches_url = "https://www.fantacalcio.it/pagelle/2023-24"
    forecast_match_url = "https://www.fantacalcio.it/probabili-formazioni-serie-a"

    def __init__(self, bonus_malus: dict = bonus_malus_table):
        self.bonus_malus_table = bonus_malus_table
        self.client = MongoClient("mongodb://localhost:27017/")
        # TODO: update at the end of the season
        if self.MONGO_DB_NAME not in self.client.list_database_names():
            self.setup_mongo()
        self.db = self.client[self.MONGO_DB_NAME]
        self.players_collection = self.db[self.MONGO_DB_PLAYER_INFO]
        self.championship_collection = self.db[self.MONGO_DB_SERIE_A_GEN_INFO]
        self.forecast_collection = self.db[self.MONGO_DB_NEXT_MATCH_FORECAST]

        # for properties
        self._current_match_day = None
        self._last_analysed_match = None
        self._serie_a_teams = None
        self._serie_a_players = None
        self._fanta_football_team = None

        # for methods
        self.driver = None

    def setup_mongo(self):
        """
        Creates mongoDB database, collections, add the teams and sets to 0 the first analysed matchday.
        """
        # to create db and collection
        db = self.client[self.MONGO_DB_NAME]
        db[self.MONGO_DB_PLAYER_INFO]
        db[self.MONGO_DB_NEXT_MATCH_FORECAST]
        self.championship_collection = db[self.MONGO_DB_SERIE_A_GEN_INFO]

        # to add 2 basic key to the collection: the name of the teams and the current match day
        # nb: the name of the teams are taken from the "url_serie_a_gen_info" because the names
        # are in the same format used by same website to index pages of the results.
        # the current match_day is used to

        serie_a_teams = self._scrape_teams(self.url_serie_a_gen_info)

        self.championship_collection.insert_one(
            {"serie_a_teams": serie_a_teams, "last_analysed_match_day": 0}
        )

    @property
    # Gets the current match day of the championship.
    #  Used to update data stored in mongodb up to the current match day.
    def current_match_day(self):
        if self._current_match_day is None:
            self._current_match_day = self._scrape_current_match_day(
                self.url_serie_a_gen_info
            )

        return self._current_match_day

    @property
    # Retrieves from mongodb the lastest analysed match day.
    def last_analysed_match(self):
        if self._last_analysed_match is None:
            # query to get the value of the last_analysed_match_day
            query = ({}, {"_id": 0, "last_analysed_match_day": 1})
            self._last_analysed_match = self.championship_collection.find_one(*query)
            # mongo query return both key, values pairs, we want only the values
            self._last_analysed_match = self._last_analysed_match[
                "last_analysed_match_day"
            ]

        return self._last_analysed_match

    @last_analysed_match.setter
    # Used to update the last_analysed_match_day after downloading and updating mongodb
    # with the latest games.
    def last_analysed_match(self, new_val: float):
        self._last_analysed_match = new_val
        # Optionally update the database to reflect this new value
        update_query = {"$set": {"last_analysed_match_day": new_val}}
        self.championship_collection.update_one({}, update_query)

    @property
    # Retrieves from MongoDB the list of teams competing in the championship.
    # This information is added to the collection within the setup method.
    def serie_a_teams(self):
        if self._serie_a_teams is None:
            query = ({}, {"_id": 0, "serie_a_teams": 1})

            self._serie_a_teams = self.championship_collection.find_one(*query)
            self._serie_a_teams = self._serie_a_teams["serie_a_teams"]

        return self._serie_a_teams

    @property
    # Retrieves all the players of the championship. Either by retrieving them from
    # the dataset or by downloading them from the web.
    def serie_a_players(self):
        if self._serie_a_players is None:
            query = (
                {"serie_a_players": {"$exists": True}},
                {"serie_a_players": 1, "_id": 0},
            )
            self._serie_a_players = self.championship_collection.find_one(*query)
            if self._serie_a_players == {} or self._serie_a_players is None:
                self.retrieve_players()
                self._serie_a_players = self.championship_collection.find_one(*query)
        return self._serie_a_players

    @property
    # Used to retrieve the fantafootball team of a given user.
    def fanta_football_team(self):
        if self._fanta_football_team is None:
            query = (
                {"user_players": {"$exists": True}},
                {"user_players": 1, "_id": 0},
            )
            self._fanta_football_team = self.championship_collection.find_one(*query)

        return self._fanta_football_team

    def update(self):
        """
        Updates all the MongoDB collections to contain the latest information available
        on the web.
        """
        self.update_players_past_matches()
        self.update_forecast_next_match()
        self.close_driver()

    def update_players_past_matches(self):
        """
        Updates and stores all the past matches of the players in the corresponding
        collection. This iteration continues until most recent match day.
        """
        while self.last_analysed_match < self.current_match_day:
            next_match_day = self.last_analysed_match + 1
            for team in self.serie_a_teams:

                url = f"{self.past_matches_url}/{team}/{next_match_day}"

                players_info = self._scrape_players_performance(url)
                if players_info is None:
                    players_info = self._selenium_scrape_players_performance(url=url)

                for player_info in players_info:

                    # Prepare the updated match stats.
                    grade = float(player_info["grade"].replace(",", "."))
                    total_bonus = self._total_bonus(player_info["bonus_malus"])
                    match_stats = {
                        "matchday": player_info["matchday"],
                        "adjective_performance": player_info["adjective_performance"],
                        "grade": grade,
                        "bonus_malus": player_info["bonus_malus"],
                        "grade_with_bm": grade + total_bonus,
                        "description": player_info["description"],
                    }

                    # If the entry does not exist, add the new match stats.
                    self.players_collection.update_one(
                        {
                            "name": player_info["name"],
                            "role": player_info["role"],
                            "team": player_info["team"],
                        },
                        {"$push": {"matchStats": match_stats}},
                        upsert=True,
                    )

            self.last_analysed_match += 1

    def _total_bonus(self, bonus_malus_player: Dict) -> float:
        """
        Computes the total bonus by summing individual bonuses and maluses

        Args:
            bonus_malus_player (Dict): dict containing for each bonus type (key)
                                        the corresponding value (+ or -)

        Returns:
            float: The total amount of bonus
        """
        return sum(
            self.bonus_malus_table[item["title"]] * int(item["value"])
            for item in bonus_malus_player
        )

    def update_forecast_next_match(self):
        """
        Retrieves information on the next matchday and stores them on MongoDB.
        """
        # Retrieve webpage
        competition_data = self._scrape_forecast_next_match(url=self.forecast_match_url)

        # Now, insert the competition data into the MongoDB collection
        self.forecast_collection.insert_one(
            {
                "current_match_day": self.current_match_day,
                "competitions": competition_data,
            }
        )

    @scrape_error_handler
    def _scrape_current_match_day(self, url: str) -> int:
        """Retrieves the current matchday.

        Args:
            url (str): URL used to get the matchday.

        Returns:
            current_matchday(int): current matchday of the championship
        """
        response = requests.get(url, headers=self.HEADERS)
        soup = BeautifulSoup(response.text, "html.parser")
        games = soup.find_all("td", "played x3")
        # in order to find the latest game we check for the max. The reason is that
        # some team might have played more matches compared to others (i.e. match has
        # been rescheduled etc.)
        current_matchday = 0
        for game in games:
            # get team name by subsetting url
            game = int(game.text)
            current_matchday = max(game, current_matchday)
        return current_matchday

    @scrape_error_handler
    def _scrape_teams(self, url: str = url_serie_a_gen_info) -> List:
        """
        Retrieves the names of the teams taking part of Serie A.

        Args:
            url (str, optional): URL used to get the team names. Defaults to url_serie_a_gen_info.

        Returns:
            List: List of the team names part of the championship.
        """
        serie_a_teams = []
        response = requests.get(url, headers=self.HEADERS)
        soup = BeautifulSoup(response.text, "html.parser")
        teams = soup.find_all("a", "team-name team-link main ml-2")
        for team in teams:
            # get team name by subsetting url
            team = team["href"].split("/")[-1]
            # the html contains duplicated (maybe mobile version?)
            if team not in serie_a_teams:
                serie_a_teams.append(team)

        return serie_a_teams

    @scrape_error_handler
    def _scrape_players_by_team(self, url: str = url_players + "inter") -> List[Dict]:
        """
        Retrieves the names of the players taking part of Serie A.

        Args:
            url (str, optional): URL used to get the players names. It need an url like
                                self.url_players + "team_name".

        Returns:
            List[Dict]: Returns a list of dictionaries where each dictionary is like
                        {"name": player_name, "role": player_role, "team": player_team}
        """
        team = url.split("/")[-1]
        team_players = []
        response = requests.get(url, headers=self.HEADERS)
        soup = BeautifulSoup(response.text, "html.parser")
        player_tags = soup.select(".player-info")
        for player in player_tags:
            name = player.select_one(".player-name")["href"]
            name = name.split("/")[-2]
            role = player.select_one(".role")["data-value"]
            team_players.append({"name": name, "role": role, "team": team})

        return team_players

    def retrieve_players(self):
        """
        Downloads all the SerieA players from the WEB and stores them in MongoDB.
        """
        players = []
        for team in self.serie_a_teams:
            url = f"{self.url_players}/{team}"
            team_players = self._scrape_players_by_team(url=url)
            players += team_players

        self.championship_collection.insert_one({"serie_a_players": players})

    @scrape_error_handler
    def _scrape_players_performance(self, url: str) -> Union[List[Dict], None]:
        """
        For each game of a given team, it returns a list of the performances of all the
        players of a given team who played a game. If any duplicated are found on the other
        hand, the function returns None. The reason is that duplicates are fake tags used
        by the website to confuse scrapers. If this function returns None, another scraper
        with Selenium will be used.


        Args:
            url (str): URL of the team game to analyse. Like: "https://www.fantacalcio.it/pagelle/2023-24/inter/1".

        Returns:
            List[Dict]: A list of dictionaries, each containing the performance data of a player.
        """

        team = url.split("/")[-2]
        next_match_day = self.last_analysed_match + 1
        url = f"{self.past_matches_url}/{team}/{next_match_day}"

        # Retrieve webpage
        response = requests.get(url)

        # Parse the content with Beautiful Soup
        soup = BeautifulSoup(response.text, "html.parser")

        player_info_list = []  # Initialize an empty list to store player info

        # many pages contain fake duplicates. If any duplicates are detected,
        # we return None.
        report = soup.select('article[class^="report pill pill-card"]')
        names = set()
        for r in report:
            name = r.find("a", class_="player-name player-link").find("span").text
            names.add(name)
            if name in names:
                return None

        for role in ["p", "d", "c", "a"]:
            report = soup.find_all("article", class_=f"report pill pill-card role-{role}")

            for player_tag in report:
                team = url.split("/")[-2]
                player_name_tag = player_tag.find("a", "player-name")
                if player_name_tag is None:
                    continue
                player_name = player_name_tag["href"].split("/")[-2]
                adjective_performance = player_tag.find(
                    "h3", "text-primary"
                ).text.replace("\n", "")
                grade = player_tag.find("div", class_="badge grade").text
                description = ""
                description_paragraphs = player_tag.select("div.col p")
                for desc_tag in description_paragraphs:
                    description += desc_tag.text
                bonus_malus = []
                for b_m in player_tag.find_all("figure", class_="icon bonus-icon"):
                    title = b_m.get("title", "").strip()
                    value = b_m.get("data-value", None)
                    bonus_malus.append({"title": title, "value": value})

                # Instead of yielding, append the player info to the list
                player_info_list.append(
                    {
                        "name": player_name,
                        "role": role,
                        "team": team,
                        "matchday": next_match_day,
                        "adjective_performance": adjective_performance,
                        "grade": grade,
                        "bonus_malus": bonus_malus,
                        "description": description,
                    }
                )

        return player_info_list

    @scrape_error_handler
    def _scrape_forecast_next_match(self, url) -> List:
        """
        Retrieves information on the next Serie A matchday.

        Args:
            url (str): url of the next matchday.

        Returns:
            List: A list containing all the forecasts of the following match.
        """
        response = requests.get(url)

        # Parse the content with Beautiful Soup
        soup = BeautifulSoup(response.text, "html.parser")

        all_formations = soup.find_all("div", class_="row col-sm")
        # TODO add comments
        all_comments = soup.find_all("section", "mt-4 match-comment")

        competition_data = []
        for formations in all_formations:
            teams_data = []

            for team in formations.find_all("div", class_=["card", "team-card"]):
                team_name = team.find("a", class_="player-name player-link")
                team_name = team_name["href"].split("/")[-3]
                team_formation = team.find("div", class_="h6 team-formation").text

                start_11_data = []
                reserves_data = []

                # rule: when element of a class, access it with .
                #       when descendent add a space
                start_11 = team.select("ul.player-list.starters li.player-item.pill")
                reserves = team.select("ul.player-list.reserves li.player-item.pill")

                for player in start_11:
                    player_name = player.find("a", class_="player-name player-link")[
                        "href"
                    ]
                    player_name = player_name.split("/")[-2]
                    player_role = player.find("span", class_="role")["data-value"]
                    percentage_of_playing = player.find("div", class_="progress-value")
                    percentage_of_playing = percentage_of_playing.text.strip().replace(
                        "%", ""
                    )
                    try:
                        percentage_of_playing = int(percentage_of_playing)
                    except ValueError:
                        percentage_of_playing = None
                    start_11_data.append(
                        {
                            "player_name": player_name,
                            "player_role": player_role,
                            "percentage_of_playing": percentage_of_playing,
                        }
                    )

                for player in reserves:
                    player_name = player.find("a", class_="player-name player-link")[
                        "href"
                    ]
                    player_name = player_name.split("/")[-2]
                    player_role = player.find("span", class_="role")["data-value"]
                    percentage_of_playing = player.find("div", class_="progress-value")
                    percentage_of_playing = percentage_of_playing.text.strip().replace(
                        "%", ""
                    )
                    try:
                        percentage_of_playing = int(percentage_of_playing)
                    except ValueError:
                        percentage_of_playing = None
                    reserves_data.append(
                        {
                            "player_name": player_name,
                            "player_role": player_role,
                            "percentage_of_playing": percentage_of_playing,
                        }
                    )

                teams_data.append(
                    {
                        "team_name": team_name,
                        "team_formation": team_formation,
                        "start_11": start_11_data,
                        "reserves": reserves_data,
                    }
                )

            # After collecting data for both teams, add it to the competition data list
            if len(teams_data) == 2:
                competition_data.append(
                    {
                        "team_home": teams_data[0]["team_name"],
                        "team_away": teams_data[1]["team_name"],
                        "team_home_forecast": {
                            "team_formation": teams_data[0]["team_formation"],
                            "start_11": teams_data[0]["start_11"],
                            "reserves": teams_data[0]["reserves"],
                        },
                        "team_away_forecast": {
                            "team_formation": teams_data[1]["team_formation"],
                            "start_11": teams_data[1]["start_11"],
                            "reserves": teams_data[1]["reserves"],
                        },
                    }
                )

        return competition_data

    def setup_selenium_driver(self):
        options = Options()
        # this works, options.headless = True fails.
        options.add_argument("--headless")
        chromedriver_autoinstaller.install()
        self.driver = webdriver.Chrome(options=options)

    def _selenium_scrape_players_performance(self, url) -> List:
        if self.driver is None:
            self.setup_selenium_driver()
        self.driver.get(url)

        next_match_day = self.last_analysed_match + 1
        team = url.split("/")[-2]
        players_info = []

        roles = ["p", "d", "c", "a"]  # Define the roles you are looking for

        try:
            for role in roles:
                # Construct the CSS selector based on the role
                role_selector = f"article.report.pill.pill-card.role-{role}"
                # Wait for the elements to be present
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, role_selector))
                )
                player_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, role_selector
                )

                for player in player_elements:
                    player_info_section = player.find_element(
                        By.CSS_SELECTOR, "div.player-info"
                    )

                    player_name_link = player_info_section.find_element(
                        By.CSS_SELECTOR, "a.player-name.player-link"
                    )
                    if not player_name_link.is_displayed():
                        continue
                    player_name = player_name_link.get_attribute("href").split("/")[-2]

                    adjective_performance = player_info_section.find_element(
                        By.CSS_SELECTOR, "h3.text-primary"
                    ).text.strip()

                    grade = player_info_section.find_element(
                        By.CSS_SELECTOR, ".badge.grade"
                    ).text.strip()

                    description_paragraphs = player_info_section.find_elements(
                        By.CSS_SELECTOR, "div.col p"
                    )
                    description = " ".join(
                        desc.text.strip() for desc in description_paragraphs
                    )

                    bonus_malus_elements = player_info_section.find_elements(
                        By.CSS_SELECTOR, "figure.icon.bonus-icon"
                    )
                    bonus_malus = []
                    for b_m in bonus_malus_elements:
                        title = b_m.get_attribute("title").strip()
                        value = b_m.get_attribute("data-value")
                        bonus_malus.append({"title": title, "value": value})

                    players_info.append(
                        {
                            "name": player_name,
                            "team": team,
                            "role": role,
                            "adjective_performance": adjective_performance,
                            "matchday": next_match_day,
                            "grade": grade,
                            "bonus_malus": bonus_malus,
                            "description": description,
                        }
                    )

        except Exception as e:
            print(f"Error during web scraping: {e}")

        return players_info

    def close_driver(self):
        if self.driver is not None:
            self.driver.quit()


if __name__ == "__main__":
    scraper = SerieADatabaseManager()
    scraper
