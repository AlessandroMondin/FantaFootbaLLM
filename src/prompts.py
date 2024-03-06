from langchain.prompts import PromptTemplate


recognize_players_prompt = """
Given the following text, if you recognize names (players) return them in a list of dicts
like -- [{{'player_name': player_name, 'team': team}}].--
If the team is not specified, the default value is None.
If no player is identified in the text, return an empty list: []."

<< INPUT >>
{chat_history}
"""


no_players_in_the_message = """
<< INPUT >>
{previous_message}

<< OUTPUT >>
In the previous message, the user user did not list the players of his/her football team. 
Tell him that without listing player he cannot proceed. Be informal and not verbose.
"""
