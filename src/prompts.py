from langchain.prompts import PromptTemplate

style_concise = "informal and concise."
style_very_concise = "informal and very concise. Do not be verbose."

message_is_listing_players_prompt = """
If the input massage contains names of players return True,
otherwise return False.

<< INPUT >>
{chat_history}

<< OUTPUT >>
True or False
"""


no_players_in_the_message = """
<< INPUT >>
{message}

<< OUTPUT >>
In the previous message, the user user did not list the players of his/her 
fantasy-football team. fantasy-football is fantacalcio in italian.
Tell him to list them band then he will be able to continue. The output should be {style}
"""

recognize_players_prompt = """
Given the names listed in <<LIST>>, return a sublist of <<LIST>> of the dictionaries
where the key 'name' is included in <<MESSAGE>>. Consider that typos can be present in
 <<MESSAGE>>.

EXAMPLE:
<<INPUT>>
{{'serie_a_players': [{{'name': 'audero', 'role': 'p', 'team': 'inter'}},
                    {{'name': 'di-gennaro', 'role': 'p', 'team': 'inter'}},
                    {{'name': 'sommer', 'role': 'p', 'team': 'inter'}},
                    {{'name': 'dimarco', 'role': 'd', 'team': 'inter'}},
                    {{'name': 'de-vrij', 'role': 'd', 'team': 'inter'}}]
}}

<<MESSAGE>>
"ok bro, I have maignan, sommer, parenzo, and de-vrij."

<<OUTPUT>>
[{{'name': 'sommer', 'role': 'p', 'team': 'inter'}},
{{'name': 'de-vrij', 'role': 'd', 'team': 'inter'}}]

<< INPUT >>
{list_of_all_players}

<<MESSAGE>>
{user_message}

<< OUTPUT >>
Sublist of players contained in <<OUTPUT>> and <<MESSAGE>>
as explained and shown in the EXAMPLE.
"""

if __name__ == "__main__":
    print(
        recognize_players_prompt.format(list_of_all_players="ciao", user_message="lol")
    )
