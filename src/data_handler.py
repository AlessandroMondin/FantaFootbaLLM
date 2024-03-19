from pymongo import MongoClient

from utils import logger, validate_year_range
from scrapers.serie_a_scraper import SerieA_Scraper


class SerieA_DatabaseManager:
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
        self._current_season = None

    @property
    def current_match_day(self):
        if self._current_match_day is None:
            self._current_match_day = self.scraper.get_current_match_day()
        return self._current_match_day

    @property
    # Retrieves from MongoDB the list of teams competing in the championship.
    # This information is added to the collection within the setup method.
    def current_season(self):
        if self._current_season is None:
            query = {"current_season": {"$exists": True}}
            projection = {"_id": 0, "current_season": 1}

            document = self.championship_collection.find_one(query, projection)
            if document and "current_season" in document:
                # 'serie_a_teams' field is found, use it.
                self._current_season = document["current_season"]

            elif self._current_season is None or self._current_season == {}:
                self._current_season = self.scraper.get_current_season()
                self.championship_collection.insert_one(
                    {"current_season": self._current_season}
                )

        return self._current_season

    @property
    # Retrieves from MongoDB the list of teams competing in the championship.
    # This information is added to the collection within the setup method.
    def serie_a_teams(self):
        if self._serie_a_teams is None:
            query = {"serie_a_teams": {"$exists": True}, "season": self.current_season}
            projection = {"_id": 0, "serie_a_teams": 1}

            document = self.championship_collection.find_one(query, projection)
            if document and "serie_a_teams" in document:
                # 'serie_a_teams' field is found, use it.
                self._serie_a_teams = document["serie_a_teams"]

            elif self._serie_a_teams is None or self.serie_a_teams == {}:
                self._serie_a_teams = self.scraper.get_team_names()
                self.championship_collection.insert_one(
                    {"serie_a_teams": self._serie_a_teams, "season": self.current_season}
                )

        return self._serie_a_teams

    @property
    # Retrieves all the players of the championship. Either by retrieving them from
    # the dataset or by downloading them from the web.
    def serie_a_players(self):
        if self._serie_a_players is None:
            query = (
                {"serie_a_players": {"$exists": True}, "season": self.current_season},
                {"serie_a_players": 1, "_id": 0},
            )
            self._serie_a_players = self.championship_collection.find_one(*query)
            if self._serie_a_players == {} or self._serie_a_players is None:
                self._serie_a_players = self.scraper.get_player_names()
                self._serie_a_players = self.championship_collection.insert_one(
                    {"serie_a_teams": self._serie_a_teams, "season": self.current_season}
                )
        return self._serie_a_players

    @property
    # Retrieves from mongodb the lastest analysed match day.
    def last_analysed_match(self):
        if self._last_analysed_match is None:
            # query to get the value of the last_analysed_match_day
            query = (
                {"season": self.current_season},
                {"_id": 0, "last_analysed_match_day": 1},
            )
            self._last_analysed_match = self.championship_collection.find_one(*query)
            # mongo query return both key, values pairs, we want only the values

            if self._last_analysed_match is None or self._last_analysed_match == {}:
                self._last_analysed_match = 0
                self.championship_collection.insert_one(
                    {
                        "last_analysed_match_day": self._last_analysed_match,
                        "season": self.current_season,
                    }
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
        find_query = {"serie_a_players": {"$exists": True}, "season": self.current_season}
        self.championship_collection.update_one(find_query, update_query)

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

    def update_players_past_matches(self, season="2023-24"):
        # Check if the season is in a valid format
        valid_season = validate_year_range(season)
        if valid_season is False:
            raise ValueError(
                f"The value of the argument `season` must be like: '2023-24'. Got value {season}"
            )

        while self.last_analysed_match < self.current_match_day:
            match_day = self.last_analysed_match + 1
            for team in self.serie_a_teams:
                # Attempt to scrape with bs4 first
                team_game = self.scraper.get_team_performance(team, match_day, season)

                self.players_collection.update_one(
                    {"season": season, "team": team_game.pop("name")},
                    {"$push": team_game},
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
                "season": self.current_season,
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
    data_handler = SerieA_DatabaseManager(scraper)
    data_handler.update()
