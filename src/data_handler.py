import glob
import hashlib
import json

from pymongo import MongoClient
from qdrant_client import models, QdrantClient
from sentence_transformers import SentenceTransformer

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

    QDRANT_COLLECTION_BASENAME = "fantasy_football"
    RAG_QUERIES = "src/prompts/fantasy_footaball/rag_queries/*json"

    def __init__(
        self,
        scraper,
        encoder: SentenceTransformer = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
    ):
        self.scraper = scraper
        self.encoder = encoder
        # SETUP MONGO DB COLLECTIONS
        self.client = MongoClient("mongodb://localhost:27017/")
        if self.MONGO_DB_NAME not in self.client.list_database_names():
            self.setup_mongo()
        self.db = self.client[self.MONGO_DB_NAME]
        self.players_collection = self.db[self.MONGO_DB_PLAYER_INFO]
        self.championship_collection = self.db[self.MONGO_DB_SERIE_A_GEN_INFO]
        self.forecast_collection = self.db[self.MONGO_DB_NEXT_MATCH_FORECAST]

        # SETUP QDRANT COLLECTIONS
        self.qdrant = QdrantClient("localhost", port=6333)
        collections = self.qdrant.get_collections()
        collections = [collection.name for collection in collections.collections]

        # or order to create different collections based on the encoder used, we
        # we create a unique hash based on the encoder modules. Probably other, smoother
        # ways could be adopted.
        hash_object = hashlib.sha256(str(self.encoder.modules).encode())
        hex_dig = hash_object.hexdigest()
        self.qdrant_collection = self.QDRANT_COLLECTION_BASENAME + hex_dig

        if self.qdrant_collection not in collections:

            self.setup_qdrant()

        self.qdrant_update()

        # for properties
        self._current_match_day = None
        self._last_analysed_match = None
        self._serie_a_teams = None
        self._serie_a_players = None
        self._fanta_football_team = None
        self._current_season = None
        self._posticipated_matches = None

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

    @property
    def current_match_day(self):
        if self._current_match_day is None:
            self._current_match_day = self.scraper.get_current_match_day()
            self.championship_collection.update_one(
                {"current_match_day": {"$exists": True}, "season": self.current_season},
                {"$set": {"current_match_day": self._current_match_day}},
                upsert=True,
            )

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
                    {
                        "serie_a_teams": self._serie_a_teams,
                        "season": self.current_season,
                    }
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
                self._serie_a_players = []
                for team in self.serie_a_teams:
                    team_players = self.scraper.get_player_names(team)
                    self._serie_a_players += team_players
                self.championship_collection.insert_one(
                    {
                        "serie_a_players": self._serie_a_players,
                        "season": self.current_season,
                    }
                )
            else:
                self._serie_a_players = self._serie_a_players["serie_a_players"]
        return self._serie_a_players

    @property
    # Retrieves all the players of the championship. Either by retrieving them from
    # the dataset or by downloading them from the web.
    def posticipated_matches(self):
        if self._posticipated_matches is None:
            query = (
                {
                    "posticipated_matches": {"$exists": True},
                    "season": self.current_season,
                },
                {"posticipated_matches": 1, "_id": 0},
            )
            document = self.championship_collection.find_one(*query)
            if document is None:
                self._posticipated_matches = []
            else:
                self._posticipated_matches = document["posticipated_matches"]

        return self._posticipated_matches

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
        find_query = {
            "last_analysed_match_day": {"$exists": True},
            "season": self.current_season,
        }
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

        for match in self.posticipated_matches:
            team, match_day, season = match
            team_game = self.scraper.get_team_performance(team, match_day, season)
            if team_game is None:
                continue

            self.players_collection.update_one(
                {"season": season, "team": team_game.pop("name")},
                {
                    "$push": {
                        "matches": {
                            "$each": [team_game["matches"]],
                            # because of 0 indexing
                            "$position": match_day - 1,
                        }
                    }
                },
                upsert=True,
            )

            self.remove_missing_match(match)

        while self.last_analysed_match < self.current_match_day:
            match_day = self.last_analysed_match + 1
            for team in self.serie_a_teams:
                # Attempt to scrape with bs4 first
                team_game = self.scraper.get_team_performance(team, match_day, season)

                if team_game is None:
                    self.add_missing_match([team, match_day, season])
                    continue

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

    def add_missing_match(self, match_details):

        # Update the database
        self.championship_collection.update_one(
            {"season": self.current_season, "posticipated_matches": {"$exists": True}},
            {"$push": {"posticipated_matches": match_details}},
            upsert=True,
        )

    def remove_missing_match(self, match_details):
        # Remove the match from the database
        self.championship_collection.update_one(
            {"season": self.current_season, "posticipated_matches": {"$exists": True}},
            {"$pull": {"posticipated_matches": match_details}},
        )

    def setup_qdrant(self):
        self.qdrant.create_collection(
            collection_name=self.qdrant_collection,
            vectors_config=models.VectorParams(
                # Vector size is defined by used model
                size=self.encoder.get_sentence_embedding_dimension(),
                distance=models.Distance.COSINE,
            ),
        )

        documents = []
        for document in sorted(glob.glob(self.RAG_QUERIES)):
            with open(document, "r") as f:
                document = json.load(f)
                documents.append(document)

        logger.info("Uploading embeddings to QDRANT")
        self.qdrant.upload_points(
            collection_name=self.qdrant_collection,
            points=[
                models.PointStruct(
                    id=idx,
                    vector=self.encoder.encode(doc["question"]).tolist(),
                    payload=doc,
                )
                for idx, doc in enumerate(documents)
            ],
        )

    def qdant_retrieve(self, message: str, retrive_n_queries=5):
        hits = self.qdrant.search(
            collection_name=self.qdrant_collection,
            query_vector=self.encoder.encode(message).tolist(),
            limit=retrive_n_queries,
        )
        hits = [hit.payload for hit in hits]
        return hits

    def qdrant_update(self):
        num_queries_uploaded = self.qdrant.count(
            collection_name=self.qdrant_collection
        ).count

        queries_located = sorted(glob.glob(self.RAG_QUERIES))
        num_queries_located = len(queries_located)

        if num_queries_located > num_queries_uploaded:
            queries_located = queries_located[num_queries_uploaded:]
            logger.info(
                f"Identified {len(queries_located)} new queries: uploading them to QDRANT"
            )
            documents = []
            for document in sorted(glob.glob(self.RAG_QUERIES)):
                with open(document, "r") as f:
                    document = json.load(f)
                    documents.append(document)

            ids = list(range(num_queries_uploaded, num_queries_located))

            self.qdrant.upload_points(
                collection_name=self.qdrant_collection,
                points=[
                    models.PointStruct(
                        id=idx,
                        vector=self.encoder.encode(doc["question"]).tolist(),
                        payload=doc,
                    )
                    for idx, doc in zip(ids, documents)
                ],
            )


if __name__ == "__main__":
    import yaml

    # Load the YAML file
    with open("src/bonus_malus.yaml", "r") as file:
        bonus_malus_table = yaml.safe_load(file)["bonus_malus_table"]

    scraper = SerieA_Scraper(bonus_malus_table)
    data_handler = SerieA_DatabaseManager(scraper)
    data_handler.update()
