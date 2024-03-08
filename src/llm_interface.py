import os
from typing import List, Tuple

import gradio as gr
from fuzzywuzzy import process
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage

from dotenv import load_dotenv
from prompts import (
    message_is_listing_players_prompt,
    recognize_players_prompt,
    no_players_in_the_message,
    style_concise,
    style_very_concise,
)
from data_handler import SerieADatabaseManager
from utils import logger

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")

load_dotenv(dotenv_path=dotenv_path)

gpt3 = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-16k")
gpt4 = ChatOpenAI(temperature=0, model="gpt-4")


class LLMInterface:
    """
    Class used to deliver smart insights and to translate user prompts into query to MongoDB.
    """

    # threshold to identify players mentioned in the chat
    #  vs players present in the database
    fuzzy_threshold = 80

    def __init__(self) -> None:
        self.data_manager = SerieADatabaseManager()
        self.light_llm = gpt3
        self.heavy_llm = gpt4
        self.team_is_created = self.data_manager.fanta_football_team is not None

        # for debug purpose
        self.history = []

    def langchain_format(self, message, history):
        history_langchain_format = []
        for human, ai in history:
            history_langchain_format.append(HumanMessage(content=human))
            history_langchain_format.append(AIMessage(content=ai))
        history_langchain_format.append(HumanMessage(content=message))
        return history_langchain_format

    def chat_debug(self, message, history=""):
        if self.team_is_created is False:
            prompt = PromptTemplate.from_template(
                template=message_is_listing_players_prompt
            )
            prompt = prompt.format(chat_history=message)
            prompt = self.langchain_format(prompt, self.history)
            user_players = self.light_llm.invoke(prompt).content

            if eval(user_players) != []:

                # gpt4 available to the public has a context window of 8k token and
                # therefore we need to split the list of players into two prompts.
                identified_players, non_identified_players = self.get_players(
                    potential_players=user_players
                )
                c = 1

            else:
                prompt = PromptTemplate.from_template(
                    template=no_players_in_the_message
                )
                prompt = prompt.format(message=message, style=style_very_concise)
                prompt = self.langchain_format(prompt, [])
                response = self.light_llm(prompt)
                return response
        else:
            # TODO:
            # Update Team Prompts and Query
            # Add and delete players Prompts and Query
            # Suggestions Prompts and Queries
            pass

    def get_players(self, potential_players: List) -> Tuple[List, List]:

        all_players = self.data_manager.serie_a_players["serie_a_players"]
        ground_truth_names = [g["name"] for g in all_players]

        identified_players = []
        non_identified_players = []

        for user_written_name in eval(potential_players):
            # Extract the best match above the threshold
            identified = False
            _, score = process.extractOne(user_written_name, ground_truth_names)
            if score >= self.fuzzy_threshold:
                # identified_players.append((user_written_name, best_match, score))
                identified_players.append(user_written_name)
                identified = True

            if identified is False:
                non_identified_players.append(user_written_name)

        return identified_players, non_identified_players


if __name__ == "__main__":
    import time

    smart_llm = LLMInterface()
    # start = time.time()
    # message = "Ciao, potresti spiegarmi come si usa il chatbot?"
    # smart_llm.chat_debug(message)
    # print(f"message took: {time.time() - start}")
    start = time.time()
    message = "ok: ho radunovic, sportiello, gollini, maignan, faraoni, bastoni, mancini, tomori, calafiorni, gatti, baschirotto, kayode, politano, el sharawi, jankto, anguissa, musah, bajrami, de ketelare, reinders, duvan zapata, scamacca, caputo, thuram, dia, okafor and anche il grande sedorf."
    smart_llm.chat_debug(message)
    print(f"message took: {time.time() - start}")

    # gr.ChatInterface(
    #     fn=smart_llm.chat_debug,
    # ).launch()
