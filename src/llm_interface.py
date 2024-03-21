import ast
import os
from typing import List, Tuple

from dotenv import load_dotenv
from fuzzywuzzy import process
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage
from unidecode import unidecode


from prompts import (
    message_is_listing_players_prompt,
    no_players_in_the_message,
    team_added_prompt,
    label_user_message,
    info_prompt,
    style_concise,
    style_very_concise,
    queries_prompt,
)
from data_handler import SerieA_DatabaseManager
from scrapers.serie_a_scraper import SerieA_Scraper
from utils import logger

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")

load_dotenv(dotenv_path=dotenv_path)

gpt3_analyst = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-16k")
gpt4_analyst = ChatOpenAI(temperature=0, model="gpt-4")

gpt3_chat = ChatOpenAI(temperature=0.7, model="gpt-3.5-turbo-16k")
gpt4_chat = ChatOpenAI(temperature=0.7, model="gpt-4")


# TODO
# REFORMAT CHAT, USER MESSAGE/HISTORY since label user message is not working as it should.
# 2) ENR for messages (both teams and players).

# Improvements, queries using several collections: "Media di Adli all'andata vs al ritorno"
# to compute it 1) store all matches in a given collection 2) allow queries from player collection
# to call internally queries of this new collection.


class LLMInterface:
    """
    Class used to deliver smart insights and by translatating user prompts into query to MongoDB.
    """

    # threshold to identify players mentioned in the chat
    #  vs players present in the database
    fuzzy_threshold = 80

    def __init__(self, data_manager=None, max_message_history: int = 4) -> None:
        self.max_message_history = max_message_history
        self.data_manager = data_manager

        self.light_llm_analyst = gpt3_analyst
        self.heavy_llm_analyst = gpt3_analyst

        self.light_llm_chat = gpt3_chat
        self.heavy_llm_chat = gpt4_chat
        self.team_is_created = self.data_manager.fanta_football_team is not None
        # update the football stats with the latest matches / collect past data.
        self.data_manager.update()

        # for debug purpose
        self.history = []

    def chat_debug(self, message, history=""):

        prompt = self.prepare_prompt(prompt_template=label_user_message, message=message)
        prompt = self.langchain_format(prompt, self.history[-2:])
        out = self.light_llm_analyst.invoke(prompt).content
        category, eng_message = eval(out)

        if category == "info":
            prompt = self.prepare_prompt(prompt_template=info_prompt, message=message)
            prompt = self.langchain_format(prompt, self.history[-2:])
            response = self.light_llm_analyst.invoke(prompt).content
            return response
        elif category == "suggestion":
            pass
            # if self.team_is_created is False:
            #     prompt = self.prepare_prompt(
            #         message_is_listing_players_prompt, chat_history=message
            #     )
            #     prompt = self.langchain_format(prompt)
            #     user_players = self.light_llm_analyst.invoke(prompt).content

            #     if eval(user_players) != []:
            #         identified_players, non_identified_players = self.get_players(
            #             potential_players=user_players
            #         )
            #         _ = self.add_players(identified_players)
            #         self.team_is_created = True

            #         prompt = self.prepare_prompt(
            #             team_added_prompt,
            #             non_identified_players=non_identified_players,
            #             style=style_very_concise,
            #         )
            #         prompt = self.langchain_format(prompt, self.history)
            #         response = self.heavy_llm_chat.invoke(prompt).content
            #         return response

            #     else:
            #         prompt = self.prepare_prompt(
            #             no_players_in_the_message,
            #             message=message,
            #             style=style_concise,
            #         )
            #         prompt = self.langchain_format(prompt, self.history)
            #         response = self.light_llm_chat.invoke(prompt).content
            #         self.history.append([message, response])
            #         return response

        elif category == "research":
            prompt = self.prepare_prompt(
                prompt_template=queries_prompt,
                message=message,
                history=self.history[-1:],
            )
            prompt = self.langchain_format(prompt, self.history[-2:])
            query = self.heavy_llm_analyst.invoke(prompt).content
            out = list(self.multiline_eval(query))
            self.history.append([message, query])
            return [out, query]

        elif category == "team_management":
            pass

        else:
            pass

        # TODO: Further integration with prepare_prompt as needed for other functionalities.

    def multiline_eval(self, expr):
        "Evaluate several lines of input, returning the result of the last line"
        # Assuming 'self' is defined and has `data_manager.players_collection`
        context = {
            "self": self,
        }
        tree = ast.parse(expr, mode="exec")
        eval_expr = ast.Expression(tree.body[-1].value)
        exec_expr = ast.Module(tree.body[:-1], type_ignores=[])
        exec(compile(exec_expr, "<string>", "exec"), context)
        return eval(compile(eval_expr, "<string>", "eval"), context)

    def is_query_safe(query):
        # Example check: very basic and needs expansion
        return query.startswith("self.data_manager")

    def execute_query_safe(self, query):
        if not self.is_query_safe(query):
            logger.error("Query does not start with allowed operations")
            # TODO return different error
            return "UNSAFE QUERY"

        return query

    def execute_query_safely(self, query):
        safe_query = self.parse_and_validate_query(query)
        out = eval(
            safe_query
        )  # Still risky, consider alternatives or ensure strict validation
        return out

    def prepare_prompt(self, prompt_template: str, **placeholders):
        prompt = PromptTemplate.from_template(template=prompt_template)
        return prompt.format(**placeholders)

    def langchain_format(self, message, history=[]):
        history_langchain_format = []
        buffer = self.max_message_history // 2
        history = history[-buffer:]
        for human, ai in history:
            history_langchain_format.append(HumanMessage(content=human))
            history_langchain_format.append(AIMessage(content=ai))
        history_langchain_format.append(HumanMessage(content=message))
        return history_langchain_format

    def get_players(self, potential_players: List) -> Tuple[List, List]:

        all_players = self.data_manager.serie_a_players["serie_a_players"]
        ground_truth_names = [g["name"] for g in all_players]

        identified_players = []
        non_identified_players = []

        for user_written_name in eval(potential_players):
            user_written_name = unidecode(user_written_name)
            # Extract the best match above the threshold
            identified = False
            best_match, score = process.extractOne(user_written_name, ground_truth_names)
            if score >= self.fuzzy_threshold:
                # identified_players.append((user_written_name, best_match, score))
                identified_players.append(best_match)
                identified = True

            if identified is False:
                non_identified_players.append(user_written_name)

        return identified_players, non_identified_players

    def add_players(self, list_of_players):
        # players list of players not already part of player team.
        new_players = []
        already_part_of_team = []
        for player in list_of_players:
            # Check if the player is already present
            player_exists = self.data_manager.championship_collection.find_one(
                {"user_players": player}
            )

            if not player_exists:
                # If the player doesn't exist, append to the new players list
                new_players.append(player)
            else:
                already_part_of_team.append(player)

        # If there are new players, add them as a new document
        if new_players:
            self.data_manager.championship_collection.insert_one(
                {"user_players": new_players}
            )
        return already_part_of_team


# if __name__ == "__main__":

#     smart_llm = LLMInterface()

#     # gr.ChatInterface(
#     #     fn=smart_llm.chat_debug,
#     # ).launch()

if __name__ == "__main__":
    import yaml

    # Load the YAML file
    with open("src/bonus_malus.yaml", "r") as file:
        bonus_malus_table = yaml.safe_load(file)["bonus_malus_table"]
    scraper = SerieA_Scraper(bonus_malus_table=bonus_malus_table)
    data_manager = SerieA_DatabaseManager(scraper=scraper)
    smart_llm = LLMInterface(data_manager=data_manager)
    print("Welcome to the LLM Chat Interface. Type 'quit' to exit.")

    while True:
        message = input("You: ")
        if message.lower() == "quit":
            break
        response = smart_llm.chat_debug(message)
        print("Bot:", response)
