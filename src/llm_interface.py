import ast
import os
from typing import Dict, List, Tuple

import gradio as gr
from dotenv import load_dotenv
from fuzzywuzzy import process
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage
from unidecode import unidecode


from prompts.fantasy_footaball.prompts import (
    list_players_and_teams,
    translate_user_message,
    label_user_message,
    info_prompt,
    queries_prompt,
    result_explanation_prompt,
    correct_json_prompt,
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

    def __init__(
        self,
        data_manager=None,
        max_message_history: int = 4,
        retrieve_n_queries=8,
        multilingual=True,
    ) -> None:
        self.max_message_history = max_message_history
        self.retrieve_n_queries = retrieve_n_queries
        self.data_manager = data_manager
        self.multilingual = multilingual

        self.light_llm_analyst = gpt3_analyst
        self.heavy_llm_analyst = gpt3_analyst

        self.light_llm_chat = gpt3_chat
        self.heavy_llm_chat = gpt4_chat
        self.team_is_created = self.data_manager.fanta_football_team is not None
        # update the football stats with the latest matches / collect past data.
        self.data_manager.update()

        # for debug purpose
        self.history = []

        self.bonus_malus_names = list(
            self.data_manager.scraper.bonus_malus_table.keys()
        )

    def chat_debug(self, message, history=""):
        # condition to avoid translating to english a
        # user message written in english.
        if self.multilingual is True:
            eng_message, source_language = self.translate_message(message)

        else:
            eng_message, source_language = message, "english"

        category = self.categorize_message(eng_message)

        if category == "info":
            response = self.handle_info_message(message)
            return response

        elif category == "research":
            response = self.handle_research_category(
                original_message=message,
                eng_message=eng_message,
                source_language=source_language,
            )
            return response

        else:
            # TODO: write prompt for the non-pertinent message.
            pass

    def translate_message(self, message):
        prompt = self.prepare_prompt(
            prompt_template=translate_user_message, message=message
        )
        prompt = self.langchain_format(prompt, self.history[-2:])

        eng_message, source_language = eval(
            self.light_llm_analyst.invoke(prompt).content
        )

        return eng_message, source_language

    def categorize_message(self, message):
        prompt = self.prepare_prompt(
            prompt_template=label_user_message, message=message
        )
        prompt = self.langchain_format(prompt, self.history[-2:])
        out = self.light_llm_analyst.invoke(prompt).content
        try:
            return eval(out)
        except Exception as e:
            return out

    def handle_info_message(self, message):
        prompt = self.prepare_prompt(prompt_template=info_prompt, message=message)
        prompt = self.langchain_format(prompt, self.history[-2:])
        response = self.light_llm_analyst.invoke(prompt).content
        return response

    def handle_research_category(self, eng_message, original_message, source_language):
        # Logic for handling 'research' category, including invoking LLMs,
        # mapping entities, generating and executing queries
        prompt = self.prepare_prompt(list_players_and_teams, chat_history=eng_message)
        prompt = self.langchain_format(prompt)
        entities = self.light_llm_analyst.invoke(prompt).content

        # replace entities identified in the string with
        # the named used in the database.
        mappings, non_identified_entities = self.map_entities(
            potential_entities=entities
        )

        query_results = []
        query = None
        # if the query contains some mappings to players / teams present in the db
        # we the methods generates a query whose results are appended to
        # query_results.
        if mappings != {}:
            # substitue the entities in the user message with the ones present in
            # the database. Otherwise queries could not be executed correctly.
            for old, new in mappings.items():
                eng_message = eng_message.replace(old, new)

            # Retrieving the queries closest to the ones of the user.
            # Retrieval Augmented Generation
            closest_queries = self.data_manager.qdant_retrieve(
                eng_message, self.retrieve_n_queries
            )
            prompt_history = (
                self.history[-1:] if len(self.history) > 1 else self.history
            )
            prompt = self.prepare_prompt(
                prompt_template=queries_prompt,
                bonus_malus_names=self.bonus_malus_names,
                examples=self.double_braces(str(closest_queries)),
                message=eng_message,
                history=prompt_history,
            )
            prompt = self.langchain_format(prompt, [])
            # generate the mongodb query.
            query = self.heavy_llm_analyst.invoke(prompt).content
            # The following block is used to handle post-processing
            # to make sure that the query can be executed by pymongo.

            try:
                try:
                    query = self.multiline_eval(query)
                    if isinstance(query, tuple):
                        query = list(query)
                    if (
                        isinstance(query, dict)
                        and "query" in query
                        and isinstance(query["query"], list)
                    ):
                        query = list(query["query"])
                except SyntaxError:
                    prompt = self.prepare_prompt(
                        prompt_template=correct_json_prompt, data_structure=query
                    )
                    prompt = self.langchain_format(prompt, [])
                    query = self.light_llm_analyst.invoke(prompt).content
                    query = self.multiline_eval(query)

                outputs = self.data_manager.players_collection.aggregate(query)
                for out in outputs:
                    query_results.append(out)

            except Exception as e:
                query_results = "query failed"
        # The following block is responsible to translate the mongodb query into
        # human language and to provide the response to the user.
        prompt = self.prepare_prompt(
            prompt_template=result_explanation_prompt,
            question=original_message,
            non_identified_entities=non_identified_entities,
            query_results=query_results,
            history=self.history[-1:],
            language=source_language,
        )
        prompt = self.langchain_format(prompt, [])
        out = self.heavy_llm_chat.invoke(prompt).content
        gpt_response = {"query": query, "response": out}
        self.history.append([original_message, str(gpt_response)])
        return out

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

    def map_entities(self, potential_entities: List) -> Tuple[Dict, List]:

        all_players = self.data_manager.serie_a_players
        player_names = [g["name"] for g in all_players]
        team_names = self.data_manager.serie_a_teams
        all_entities = player_names + team_names

        identified_entities = {}
        non_identified_entities = []

        for user_written_name in eval(potential_entities):
            user_written_name = unidecode(user_written_name)
            # Extract the best match above the threshold
            identified = False
            best_match, score = process.extractOne(user_written_name, all_entities)
            if score >= self.fuzzy_threshold:
                # identified_players.append((user_written_name, best_match, score))
                identified_entities[user_written_name] = best_match
                identified = True

            if identified is False:
                non_identified_entities.append(user_written_name)

        return identified_entities, non_identified_entities

    def double_braces(self, input_str):
        """
        Adds an additional brace before each occurrence of "{" or "}" in the input string.

        Parameters:
        - input_str (str): The input string to process.

        Returns:
        - str: The modified string with doubled braces.
        """
        modified_str = ""
        for char in input_str:
            if char == "{":
                modified_str += "{{"
            elif char == "}":
                modified_str += "}}"
            else:
                modified_str += char
        return modified_str


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
    smart_llm = LLMInterface(data_manager=data_manager, retrieve_n_queries=5)

    # gr.ChatInterface(
    #     fn=smart_llm.chat_debug,
    # ).launch()
    print("Welcome to the LLM Chat Interface. Type 'quit' to exit.")

    while True:
        message = input("You: ")
        if message.lower() == "quit":
            break
        response = smart_llm.chat_debug(message)
        print("Bot:", response)
