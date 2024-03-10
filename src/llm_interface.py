import os
from typing import List, Tuple

import gradio as gr
from dotenv import load_dotenv
from fuzzywuzzy import process
from langchain_core.language_models.chat_models import BaseChatModel
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
from data_handler import SerieADatabaseManager
from utils import logger

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")

load_dotenv(dotenv_path=dotenv_path)

gpt3_analyst = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-16k")
gpt4_analyst = ChatOpenAI(temperature=0, model="gpt-4")

gpt3_chat = ChatOpenAI(temperature=0.7, model="gpt-3.5-turbo-16k")
gpt4_chat = ChatOpenAI(temperature=0.7, model="gpt-4")


class LLMInterface:
    """
    Class used to deliver smart insights and by translatating user prompts into query to MongoDB.
    """

    # threshold to identify players mentioned in the chat
    #  vs players present in the database
    fuzzy_threshold = 80

    def __init__(self, max_message_history: int = 4) -> None:
        self.max_message_history = max_message_history
        self.data_manager = SerieADatabaseManager()
        self.light_llm_analyst = gpt3_analyst
        self.heavy_llm_analyst = gpt3_analyst

        self.light_llm_chat = gpt3_chat
        self.heavy_llm_chat = gpt4_chat
        self.team_is_created = self.data_manager.fanta_football_team is not None

        # for debug purpose
        self.history = []

    def chat_debug(self, message, history=""):
        if self.team_is_created is False:
            prompt = self.prepare_prompt(
                message_is_listing_players_prompt, chat_history=message
            )
            prompt = self.langchain_format(prompt)
            user_players = self.light_llm_analyst.invoke(prompt).content

            if eval(user_players) != []:
                identified_players, non_identified_players = self.get_players(
                    potential_players=user_players
                )
                _ = self.add_players(identified_players)
                self.team_is_created = True

                prompt = self.prepare_prompt(
                    team_added_prompt,
                    non_identified_players=non_identified_players,
                    style=style_very_concise,
                )
                prompt = self.langchain_format(prompt, self.history)
                response = self.heavy_llm_chat.invoke(prompt).content
                return response

            else:
                prompt = self.prepare_prompt(
                    no_players_in_the_message,
                    message=message,
                    style=style_very_concise,
                )
                prompt = self.langchain_format(prompt, self.history)
                response = self.light_llm_chat.invoke(prompt).content
                self.history.append([message, response])
                return response
        else:
            prompt = self.prepare_prompt(
                prompt_template=label_user_message, message=message
            )
            prompt = self.langchain_format(prompt, self.history[-2:])
            category = self.light_llm_analyst.invoke(prompt).content

            if category == "info":
                prompt = self.prepare_prompt(
                    prompt_template=info_prompt, message=message
                )
                prompt = self.langchain_format(prompt, self.history[-2:])
                response = self.light_llm_analyst.invoke(prompt).content
                return response
            elif category == "suggestion":
                pass
                # prompt = self.prepare_prompt(
                #     prompt_template=q, message=message
                # )
                # prompt = self.langchain_format(prompt, self.history[-2:])
                # response = self.heavy_llm_analyst.invoke(prompt).content
                # try:
                #     eval(response)
                # except:
                #     return
                # potential_responses = []
                # for query in response:
                #     try:
                #         out = eval(query)
                #         if out not in [None, {}]:
                #             potential_responses.append(out)

                #         prompt = self.prepare_prompt(
                #         prompt_template=queries_prompt, message=message
                #             )
                #         prompt = self.langchain_format(prompt, self.history[-2:])
                #         response = self.heavy_llm_analyst.invoke(prompt).content

            elif category == "research":
                prompt = self.prepare_prompt(
                    prompt_template=queries_prompt, message=message
                )
                prompt = self.langchain_format(prompt, self.history[-2:])
                query = self.heavy_llm_analyst.invoke(prompt).content
                out = eval(query)
                return out

            elif category == "team_management":
                pass

            else:
                pass

            # TODO: Further integration with prepare_prompt as needed for other functionalities.

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
            best_match, score = process.extractOne(
                user_written_name, ground_truth_names
            )
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
#     message = "Ciao, potresti spiegarmi come si usa il chatbot?"
#     response = smart_llm.chat_debug(message)
#     print(response)

#     # message = "ok: ho calhanoglu, celik, ostigard, Milan Đurić, swiderski, contini baranovsky, zielinki, tomori, calafiorni, gatti, baschirotto, kayode, politano, el sharawi, jankto, anguissa, musah, bajrami, de ketelare, reinders, duvan zapata, scamacca, caputo, thuram, dia, okafor and anche il grande sedorf."
#     # response = smart_llm.chat_debug(message)
#     # print(response)

#     message = "Ok dammi la migliore formazione che posso utilizzare questa giornata, e spiegami il motivo della tua scelta."
#     # message = "Ok ho scambiato tomori per kalulu."
#     # message = "Mi hai messo in formazione il giocatore x, toglilo."
#     # message = "Chi mi consigli di mettere tra Leao e Lautaro?"
#     smart_llm.chat_debug(message)
#     print(response)

#     # gr.ChatInterface(
#     #     fn=smart_llm.chat_debug,
#     # ).launch()

if __name__ == "__main__":
    smart_llm = LLMInterface()
    print("Welcome to the LLM Chat Interface. Type 'quit' to exit.")

    while True:
        message = input("You: ")
        if message.lower() == "quit":
            break
        response = smart_llm.chat_debug(message)
        print("Bot:", response)
