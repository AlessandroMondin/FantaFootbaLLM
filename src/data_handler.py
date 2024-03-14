import time
import yaml
from typing import List, Dict

import chromedriver_autoinstaller
import requests
import ssl

from bs4 import BeautifulSoup
from pymongo import MongoClient
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


from utils import scrape_error_handler, logger

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

    HEADERS = [
        {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
        },
        {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"
        },
        {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36"
        },
    ]
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
        self.request_count = 0
        self.current_user_agent_index = 0
        self.request_limit = None

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
        while self.last_analysed_match < self.current_match_day:
            next_match_day = self.last_analysed_match + 1
            for team in self.serie_a_teams:
                url = f"{self.past_matches_url}/{team}/{next_match_day}"

                # Attempt to scrape with bs4 first
                players_info = self._scrape_players_performance(url)
                # Fallback to Selenium if bs4 returns None

                for player_info in players_info:
                    grade = player_info["grade"]
                    total_bonus = self._total_bonus(player_info["bonus_malus"])
                    match_stats = {
                        "matchday": player_info["matchday"],
                        "adjective_performance": player_info["adjective_performance"],
                        "grade": grade,
                        "bonus_malus": player_info["bonus_malus"],
                        "grade_with_bm": grade + total_bonus,
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
                f"Stored match {self.last_analysed_match+1}, still {self.current_match_day - (self.last_analysed_match + 1)} to be stored."
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
        response = requests.get(url, headers=self.HEADERS[0])
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
        response = requests.get(url, headers=self.HEADERS[0])
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
        response = requests.get(url, headers=self.HEADERS[0])
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

    @scrape_error_handler
    def _extract_player_info(self, element, source, url: str):
        next_match_day = self.last_analysed_match + 1
        player_info_list = []

        roles = ["p", "d", "c", "a"]
        for role in roles:
            role_selector = f"article.report.pill.pill-card.role-{role}"
            report = self.get_elements_by_css(
                css_selector=role_selector,
                source=source,
                element=element,
                webdriver_wait=True,
            )
            for player_tag in report:
                team = url.split("/")[-2]
                player_name_tag = self.get_elements_by_css(
                    "a.player-name", source=source, element=player_tag
                )[0]
                if player_name_tag is None:
                    continue
                player_name_tag = self.get_elements_by_css(
                    "", source=source, element=player_name_tag, attribute_name="href"
                )[0]
                player_name = player_name_tag.split("/")[-2]
                adjective_performance = self.get_elements_by_css(
                    source=source, css_selector="h3.text-primary", element=player_tag
                )[0]
                adjective_performance = adjective_performance.text.replace("\n", "")

                grade = self.get_elements_by_css(
                    source=source, css_selector="div.badge.grade", element=player_tag
                )[0]

                grade = float(grade.text.replace(",", "."))
                description = ""
                description = self.get_elements_by_css(
                    source=source, css_selector="div.col p", element=player_tag
                )[0]
                description = description.text
                bonus_malus = []

                bonuses_maluses = self.get_elements_by_css(
                    source=source,
                    css_selector="figure.icon.bonus-icon",
                    element=player_tag,
                )
                for b_m in bonuses_maluses:
                    title = self.get_elements_by_css(
                        source=source,
                        css_selector="",
                        element=b_m,
                        attribute_name="title",
                    )[0]

                    value = self.get_elements_by_css(
                        source=source,
                        css_selector="",
                        element=b_m,
                        attribute_name="data-value",
                    )[0]
                    value = int(value)
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

    def get_elements_by_css(
        self,
        css_selector,
        source,
        element=None,
        attribute_name=None,
        webdriver_wait=False,
    ) -> List:
        """
        Fetch elements or their attributes using a CSS selector with either BeautifulSoup or Selenium.

        Args:
            css_selector (str): The CSS selector to find elements by.
            source (str): Indicates whether to use 'bs4' or 'selenium'.
            element (Optional[Union[BeautifulSoup, WebElement]]): The element to search within. If None, search within the whole page.
            attribute_name (Optional[str]): The name of the attribute to extract from the found elements. If None, return the elements themselves.

        Returns:
            List[Union[Tag, WebElement, str]]: A list of found elements or their attributes. If is the attribute_name is specified, it returns a string.
        """

        if source == "bs4":
            if css_selector != "":
                element = element.select(css_selector)
            else:
                element = [element]
            if attribute_name:
                element = [elem.get(attribute_name, "") for elem in element]

        elif source == "selenium":
            if css_selector != "":
                if webdriver_wait:
                    element = self._get_elements_selenium(css_selector, element)
                else:
                    element = element.find_elements(By.CSS_SELECTOR, css_selector)
            else:
                element = [element]
            if attribute_name:
                element = [
                    elem.get_attribute(attribute_name)
                    for elem in element
                    if elem.is_displayed()
                ]
            else:
                element = [elem for elem in element if elem.is_displayed()]

        return element

    def _determine_source(self, url, css_selector, callback):
        """Fetch content from URL and process it using a CSS selector and a callback function."""
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        while "ERROR" in soup.find("title").text:
            logger.warning(
                "Rate limit error encountered. Sleeping for 2 minutes and 30 seconds."
            )
            time.sleep(150)
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
        elements = soup.select(css_selector)
        result = [callback(element) for element in elements]
        return "selenium" if len(result) != len(set(result)) else "bs4"

    def _scrape_players_performance(self, url: str):
        def extract_player_name(element):
            """Extract and return the player's name from a BeautifulSoup tag."""
            return element.find("a", class_="player-name player-link").find("span").text

        source = self._determine_source(
            url=url,
            css_selector='article[class^="report pill pill-card"]',
            callback=extract_player_name,
        )
        element = self._get_initial_element(url, source)
        player_info_list = self._extract_player_info(element, source, url)
        return player_info_list

    def _get_initial_element(self, url, source, request_limit=15):
        self.request_limit = request_limit  # Update request limit if provided
        if source == "selenium":
            self.request_count += 1  # Increment request count
            if self.driver is None or self.request_count >= self.request_limit:
                if self.driver is not None:
                    self.close_driver()  # Close the existing driver if it exists
                self.setup_selenium_driver()  # Setup a new driver
                self.request_count = (
                    0  # Reset request count after refreshing the driver
                )

            self.driver.get(url)
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            while "ERROR" in soup.find("title").text:
                logger.warning(
                    "Rate limit error encountered. Sleeping for 2 minutes and 30 seconds."
                )
                time.sleep(150)
                response = requests.get(url)
                soup = BeautifulSoup(response.text, "html.parser")

            return self.driver
        else:
            current_header = self.current_user_agent_index
            response = requests.get(url, headers=self.HEADERS[current_header])
            self.current_user_agent_index = (self.current_user_agent_index + 1) % len(
                self.HEADERS
            )
            soup = BeautifulSoup(response.text, "html.parser")
            while "ERROR" in soup.find("title").text:
                logger.warning(
                    "Rate limit error encountered. Sleeping for 2 minutes and 30 seconds."
                )
                time.sleep(150)
                response = requests.get(url)
                soup = BeautifulSoup(response.text, "html.parser")
            return soup

    def _get_elements_selenium(self, css_selector, driver):
        """Retrieve elements using Selenium, waiting until they are loaded."""
        try:
            # Wait up to 10 seconds before throwing a TimeoutException unless
            # it finds the element to return based on the css_selector.
            elements = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, css_selector))
            )
            return elements
        except TimeoutException:
            print("Timeout while waiting for elements.")
            return []

    def setup_selenium_driver(self):
        options = Options()
        options.add_argument("--headless")
        # Cycle through the user agents
        user_agent = self.HEADERS[self.current_user_agent_index]
        options.add_argument(f"user-agent={user_agent}")
        chromedriver_autoinstaller.install()
        self.driver = webdriver.Chrome(options=options)
        # Update index for next user agent, cycle back to start if at end of list
        self.current_user_agent_index = (self.current_user_agent_index + 1) % len(
            self.HEADERS
        )

    def close_driver(self):
        if self.driver is not None:
            self.driver.quit()
            self.driver = None


if __name__ == "__main__":
    scraper = SerieADatabaseManager()
    scraper.update()
