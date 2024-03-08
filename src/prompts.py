from langchain.prompts import PromptTemplate

style_concise = "informal and concise."
style_very_concise = "informal and very concise. Do not be verbose."

message_is_listing_players_prompt = """
If the input massage contains names of players return them in a list.
Otherwise return an empty list.

EXAMPLES:
///
example 1:
<<INPUT>>
Ciao, come si usa questo chatbot?

<<OUTPUT>>
[]

example 2:
<<INPUT>>
I miei giocatori sono Mike mAIGNAN, El sharawi, Baschirotto.

<<OUTPUT>>
["Mike mAIGNAN", "El sharawi", "Baschirotto"]
///

<< INPUT >>
{chat_history}

<< OUTPUT >>
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
Given the names listed in <<INPUT>>, return a sublist of <<INPUT>> of the dictionaries
where the key 'name' is included in <<MESSAGE>>. Consider that typos can be present in
 <<MESSAGE>>.

EXAMPLES:
///
example 1:
<<INPUT>>
{{'name': 'audero', 'role': 'p', 'team': 'inter'}}


<<MESSAGE>>
"ok bro, I have maignan, sommer, parenzo, and de-vrij."

<<OUTPUT>>
{{}}

example 2:
<<INPUT>>
{{'name': 'maignan', 'role': 'p', 'team': 'milan'}}


<<MESSAGE>>
"ok bro, I have Mike Maignann, sommer, parenzo, and de-vrij."

<<OUTPUT>>
{{'name': 'maignan', 'role': 'p', 'team': 'milan'}}
///
<<INPUT>>
{player_dict}

<<MESSAGE>>
{user_message}

<< OUTPUT >>
<<INPUT>> if name is included in <<MESSAGE>>
"""

recognize_players_prompt = """
Return <<INPUT>> if the key "name" is present in <<MESSAGE>>. Otherwise return {{}}

<<INPUT>>
{player_dict}

<<MESSAGE>>
{user_message}
"""

if __name__ == "__main__":
    print(
        recognize_players_prompt.format(list_of_all_players="ciao", user_message="lol")
    )
