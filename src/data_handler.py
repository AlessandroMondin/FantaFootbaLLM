from typing import List, Dict, Generator, Tuple
import yaml
from pymongo import MongoClient
import requests
from bs4 import BeautifulSoup

from utils import scrape_error_handler

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

    def update_players_past_matches(self):
        """
        Updates and stores all the past matches of the players in the corresponding
        collection. This iteration continues until most recent match day.
        """
        while self.last_analysed_match < self.current_match_day:
            next_match_day = self.last_analysed_match + 1
            for team in self.serie_a_teams:
                url = f"{self.past_matches_url}/{team}/{next_match_day}"

                for player_info in self._scrape_player_performace_match(url):

                    # Check if the player's match stats for the specific matchday already exist.
                    existing_entry = self.players_collection.find_one(
                        {
                            "name": player_info["name"],
                            "role": player_info["role"],
                            "team": player_info["team"],
                            "matchStats": {
                                "$elemMatch": {"matchday": player_info["matchday"]}
                            },
                        }
                    )

                    # Prepare the updated match stats.
                    grade = float(player_info["grade"].replace(",", "."))
                    total_bonus = self._total_bonus(player_info["bonus_malus"])
                    updated_match_stats = {
                        "matchday": player_info["matchday"],
                        "adjective_performance": player_info["adjective_performance"],
                        "grade": grade,
                        "bonus_malus": player_info["bonus_malus"],
                        "grade_with_bm": grade + total_bonus,
                        "description": player_info["description"],
                    }

                    # If the entry exists, update the existing match stats.
                    if existing_entry:
                        self.players_collection.update_one(
                            {
                                "name": player_info["name"],
                                "role": player_info["role"],
                                "team": player_info["team"],
                                "matchStats.matchday": player_info["matchday"],
                            },
                            {"$set": {"matchStats.$": updated_match_stats}},
                        )
                    else:
                        # If the entry does not exist, add the new match stats.
                        self.players_collection.update_one(
                            {
                                "name": player_info["name"],
                                "role": player_info["role"],
                                "team": player_info["team"],
                            },
                            {"$push": {"matchStats": updated_match_stats}},
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
    def _scrape_player_performace_match(
        self,
        url: str,
    ) -> Generator[Tuple[Dict, Dict], None, None]:
        """
        For each game of a given team, it yields the performance of a given player.
        The reason why a generator is used because player stats are contained into
        the team stats and we want to return player stats. However, this way we can
        make sure 1) to make a single request for each player 2) make sure that if the
        request to the browser fails, we are notified thanks to the scrape_error_handler
        decorator

        Args:
            url (str): URL of the team game to analyse. Like: "https://www.fantacalcio.it/pagelle/2023-24/inter/1".

        Yields:
            Generator[Tuple[Dict, Dict], None, None]: _description_
        """

        team = url.split("/")[-2]
        next_match_day = self.last_analysed_match + 1
        url = f"{self.past_matches_url}/{team}/{next_match_day}"

        # Retrieve webpage
        response = requests.get(url)

        # Parse the content with Beautiful Soup
        soup = BeautifulSoup(response.text, "html.parser")

        # due to the html of:
        # https://www.fantacalcio.it/pagelle/2023-24/inter/1
        for role in ["p", "d", "c", "a"]:

            report = soup.find_all(
                "article", class_=f"report pill pill-card role-{role}"
            )

            for player_tag in report:
                team = url.split("/")[-2]
                player_name_tag = player_tag.find("a", "player-name")
                # some of the children tags do not contain players information
                # and therefore we skip them.
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
                    # Extracting the title and data-value, if data-value is not available it defaults to None
                    title = b_m.get("title", "").strip()
                    value = b_m.get("data-value", None)
                    bonus_malus.append({"title": title, "value": value})

                yield {
                    "name": player_name,
                    "role": role,
                    "team": team,
                    "matchday": next_match_day,
                    "adjective_performance": adjective_performance,
                    "grade": grade,
                    "bonus_malus": bonus_malus,
                    "description": description,
                }

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


if __name__ == "__main__":
    scraper = SerieADatabaseManager()
    scraper
