from difflib import SequenceMatcher
import os

import gradio as gr
from fuzzywuzzy import fuzz
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage

from dotenv import load_dotenv
from prompts import recognize_players_prompt, no_players_in_the_message
from data_handler import SerieADatabaseManager

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")

load_dotenv(dotenv_path=dotenv_path)

gpt3 = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-0613")
gpt4 = ChatOpenAI(temperature=1.0, model="gpt-4")


class LLMInterface:
    """
    Class used to deliver smart insights and to translate user prompts into query to MongoDB.
    """

    def __init__(self) -> None:
        self.data_manager = SerieADatabaseManager()
        self.light_llm = gpt3
        self.team_is_created = self.data_manager.fanta_football_team is not None

        # for debug purpose
        self.history = []

    # def chat(self, message, history):
    #     if self.team_is_created is False:
    #         prompt = PromptTemplate.from_template(template=recognize_players_prompt)
    #         message = prompt.format(question=message)
    #     else:
    #         pass

    #     history_langchain_format = []
    #     for human, ai in history:
    #         history_langchain_format.append(HumanMessage(content=human))
    #         history_langchain_format.append(AIMessage(content=ai))
    #     history_langchain_format.append(HumanMessage(content=message))
    #     response = ""
    #     for chunk in self.light_llm.stream(history_langchain_format):
    #         response += chunk.content
    #         yield response

    def langchain_format(self, message, history):
        history_langchain_format = []
        for human, ai in history:
            history_langchain_format.append(HumanMessage(content=human))
            history_langchain_format.append(AIMessage(content=ai))
        history_langchain_format.append(HumanMessage(content=message))
        return history_langchain_format

    def chat_debug(self, message, history=""):
        if self.team_is_created is False:
            prompt = PromptTemplate.from_template(template=recognize_players_prompt)
            prompt = prompt.format(chat_history=message)
            prompt = self.langchain_format(prompt, self.history)
            players = self.light_llm(prompt).content
            try:
                players = eval(players)
                if players == []:
                    prompt = PromptTemplate.from_template(
                        template=no_players_in_the_message
                    ).format(previous_message=message)

                    prompt = self.langchain_format(prompt, self.history)
                    response = self.light_llm(prompt).content
                    self.history.append([message, response])
                    return response
                else:
                    self.data_manager.serie_a_players
                    matched_players = []
                    not_matched_players = []
                    for prompt_player in players:
                        is_matched = False
                        prompt_player = prompt_player["name"]
                        for verified_player in self.data_manager.serie_a_players[
                            "serie_a_players"
                        ]:
                            if is_matched:
                                break

                            verified_player = verified_player["name"]

                            if fuzz.partial_ratio(prompt_player, verified_player) > 80:
                                matched_players.append(prompt_player)
                                is_matched = True

                        if is_matched == False:
                            not_matched_players.append(prompt_player)

                    # TODO: add players to MongoDB
                    #       create prompt to tell which players have been added and which are not.

                    pass
            except:
                # TODO: create prompt to explain that the query failed??
                pass
        else:
            # TODO:
            # Update Team Prompts and Query
            # Add and delete players Prompts and Query
            # Suggestions Prompts and Queries
            pass


if __name__ == "__main__":
    import time

    smart_llm = LLMInterface()
    start = time.time()
    message = "Ciao, potresti spiegarmi come si usa il chatbot?"
    smart_llm.chat_debug(message)
    print(f"message took: {time.time() - start}")
    start = time.time()
    message = "ok: ho radunovic, sportiello, gollini, maignan, faraoni, bastoni, mancini, tomori, calafiorni, gatti, baschirotto, kayode, politano, el sharawi, jankto, anguissa, musah, bajrami, de ketelare, reinders, duvan zapata, scamacca, caputo, thuram, dia, okafor and anche il grande sedorf."
    smart_llm.chat_debug(message)
    print(f"message took: {time.time() - start}")

    # gr.ChatInterface(
    #     fn=smart_llm.chat_debug,
    # ).launch()
