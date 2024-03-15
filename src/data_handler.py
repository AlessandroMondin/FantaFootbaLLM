from pymongo import MongoClient

from utils import logger
from scrapers.serie_a_scraper import SerieA_Scraper


class SerieADatabaseManager:
    """
    Class used to scrape information on Leghe Serie A and to store them into MongoDB.
    """

    MONGO_DB_NAME = "FantaCalcioLLM"
    MONGO_DB_SERIE_A_GEN_INFO = "user_serie_a_info"
    MONGO_DB_PLAYER_INFO = "players"
    MONGO_DB_NEXT_MATCH_FORECAST = "forecast_match_day"

    def __init__(self, scraper):
        self.scraper = scraper
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

    @property
    def current_match_day(self):
        if self._current_match_day is None:
            self._current_match_day = self.scraper.get_current_match_day()
        return self._current_match_day

    @property
    # Retrieves from MongoDB the list of teams competing in the championship.
    # This information is added to the collection within the setup method.
    def serie_a_teams(self):
        if self._serie_a_teams is None:
            query = ({}, {"_id": 0, "serie_a_teams": 1})

            self._serie_a_teams = self.championship_collection.find_one(*query)

            if self._serie_a_teams is None or self.serie_a_teams == {}:
                self._serie_a_teams = self.scraper.get_team_names()
                self.championship_collection.insert_one(
                    {"serie_a_teams": self._serie_a_teams}
                )
            else:
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
                self._serie_a_players = self.scraper.get_player_names()
                self._serie_a_players = self.championship_collection.find_one(*query)
        return self._serie_a_players

    @property
    # Retrieves from mongodb the lastest analysed match day.
    def last_analysed_match(self):
        if self._last_analysed_match is None:
            # query to get the value of the last_analysed_match_day
            query = ({}, {"_id": 0, "last_analysed_match_day": 1})
            self._last_analysed_match = self.championship_collection.find_one(*query)
            # mongo query return both key, values pairs, we want only the values

            if self._last_analysed_match == None or self._last_analysed_match == {}:
                self._last_analysed_match = 0
                self.championship_collection.insert_one(
                    {"last_analysed_match_day": self._last_analysed_match}
                )
            else:
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

    def update(self):
        """
        Updates all the MongoDB collections to contain the latest information available
        on the web.
        """
        self.update_players_past_matches()
        self.update_forecast_next_match()

    def update_players_past_matches(self):
        while self.last_analysed_match < self.current_match_day:
            match_day = self.last_analysed_match + 1
            for team in self.serie_a_teams:
                # Attempt to scrape with bs4 first
                players_info = self.scraper.get_team_performance(team, match_day)
                # Fallback to Selenium if bs4 returns None

                for player_info in players_info:
                    match_stats = {
                        "matchday": player_info["matchday"],
                        "adjective_performance": player_info["adjective_performance"],
                        "grade": player_info["grade"],
                        "bonus_malus": player_info["bonus_malus"],
                        "fanta_grade": player_info["fanta_grade"],
                        "description": player_info["description"],
                    }

                    self.players_collection.update_one(
                        {
                            "name": player_info["name"],
                            "role": player_info["role"],
                            "team": player_info["team"],
                        },
                        {"$push": {"matchStats": match_stats}},
                        upsert=True,
                    )
            logger.info(
                f"Stored match {match_day}, still {self.current_match_day - match_day} to be stored."
            )
            self.last_analysed_match += 1

    def update_forecast_next_match(self):
        """
        Retrieves information on the next matchday and stores them on MongoDB.
        """
        # Retrieve webpage
        competition_data = self.scraper.get_forecast_next_match()

        # Now, insert the competition data into the MongoDB collection
        self.forecast_collection.insert_one(
            {
                "current_match_day": self.current_match_day,
                "competitions": competition_data,
            }
        )


if __name__ == "__main__":
    import yaml

    # Load the YAML file
    with open("src/bonus_malus.yaml", "r") as file:
        bonus_malus_table = yaml.safe_load(file)["bonus_malus_table"]

    scraper = SerieA_Scraper(bonus_malus_table)
    data_handler = SerieADatabaseManager(scraper)
    data_handler.update()
