from difflib import SequenceMatcher
import os

import gradio as gr
from fuzzywuzzy import fuzz
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

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")

load_dotenv(dotenv_path=dotenv_path)

gpt3 = ChatOpenAI(temperature=1.0, model="gpt-3.5-turbo-16k")
gpt4 = ChatOpenAI(temperature=0, model="gpt-4")


class LLMInterface:
    """
    Class used to deliver smart insights and to translate user prompts into query to MongoDB.
    """

    def __init__(self) -> None:
        self.data_manager = SerieADatabaseManager()
        self.light_llm = gpt3
        self.heavy_llm = gpt4
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

    async def get_players(self, message: str):
        num_players = len(self.data_manager.serie_a_players["serie_a_players"])
        segment_size = max(num_players // 10, 1)  # Ensure segment size is at least 1
        segments = []

        # Split the players into 10 segments
        for i in range(10):
            start_index = i * segment_size
            # For the last segment, ensure it includes the end of the list
            end_index = None if i == 9 else start_index + segment_size
            segments.append(
                self.data_manager.serie_a_players["serie_a_players"][
                    start_index:end_index
                ]
            )

        # Process each segment asynchronously
        user_players_futures = []
        for segment in segments:
            formatted_prompt = recognize_players_template.format(
                list_of_all_players=segment,
                user_message=message,
            )
            formatted_prompt = self.langchain_format(formatted_prompt, history)
            # Assuming heavy_llm is an async function
            future = self.heavy_llm(formatted_prompt)
            user_players_futures.append(future)

        # Wait for all futures to complete
        user_players_responses = await asyncio.gather(*user_players_futures)

    def chat_debug(self, message, history=""):
        if self.team_is_created is False:
            prompt = PromptTemplate.from_template(
                template=message_is_listing_players_prompt
            )
            prompt = prompt.format(chat_history=message)
            prompt = self.langchain_format(prompt, self.history)
            contains_players = self.light_llm(prompt).content

            if eval(contains_players) is True:
                prompt = PromptTemplate.from_template(template=recognize_players_prompt)

                # gpt4 available to the public has a context window of 8k token and
                # therefore we need to split the list of players into two prompts.
                num_players = len(self.data_manager.serie_a_players["serie_a_players"])
                half_index = num_players // 2
                first_half_players = self.data_manager.serie_a_players[
                    "serie_a_players"
                ][:half_index]
                second_half_players = self.data_manager.serie_a_players[
                    "serie_a_players"
                ][half_index:]
                prompt_1 = prompt.format(
                    list_of_all_players=first_half_players,
                    user_message=message,
                )
                prompt_2 = prompt.format(
                    list_of_all_players=second_half_players,
                    user_message=message,
                )
                prompt_1 = self.langchain_format(prompt_1, [])
                prompt_2 = self.langchain_format(prompt_2, [])
                user_players_1 = self.heavy_llm(prompt_1)
                user_players_2 = self.heavy_llm(prompt_2)

                user_players = eval(user_players_1) + eval(user_players_2)

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
