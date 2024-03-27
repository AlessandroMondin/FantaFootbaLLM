from langchain.prompts import PromptTemplate

style_concise = "informal and concise. Do not be verbose."
style_very_concise = "informal and very concise. Do not be verbose."

list_players_and_teams = """
If the input message contains names that could be referring to players, teams, or any
mentioned entities, return them in a list. This includes names that may not be
immediately recognizable as associated with football but are presented as potential
entities in the context of the message. Otherwise, return an empty list.

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

example 3:
<<INPUT>>
Oltre a immobile, chi sono gli altri attaccanti della Lazio?.

<<OUTPUT>>
["immobile", "Lazio"]

example 3:
<<INPUT>>
Immobile gioca nella lazio, istambul o nel nizza?.

<<OUTPUT>>
["immobile", "Lazio", "istambul", "nizza"]
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
Tell him that in order to use this chatbot, he needs to list them. The output should be {style}
"""

team_added_prompt = """
Tell the players how have added the listed players to their team.
However, if the <<NOT_RECOGNIZED_PLAYERS>> is not [], tell them that those
players were not recognized and were not added to the team. If you know that
those are not football players or are old players reply with a joke, otherwise
if you are not sure tell them to check do the following steps: 
1) Open this link: https://www.fantacalcio.it/serie-a/squadre
2) Select the team of the player
3) Click on "Rosa"
4) Click on the player and check the name present in the URL: for example given the URL
https://www.fantacalcio.it/serie-a/squadre/milan/rafael-leao/4510, copy use the name "rafael-leao" as in the URL.

<<NOT_RECOGNIZED_PLAYERS>>
{non_identified_players}

In your reply use the following style:
{style}

Finally tell the user that he can ask you these questions:
- Which should be my starting 11 for this matchday?
- Which modulo should I use?
- Should I put a player or another one?
- You can ask me to modify your team after a trade of players/remove a player that was 
    erroneously added to your team.
- You can ask stats about players like how many goals has Leao scored this year?
- Does this player scores when the other team plays with this modulo?
"""

translate_user_message = """
Please provide a literal translation where every word from the original message is
translated into English. If there are specific words that do not have a direct
translation or are names that should not be translated, include them in their original
form within the translated text. The translation should reflect the complete content and
structure of the original message, ensuring no word is omitted.

<<MESSAGE>>
{message}

<<OUTPUT>>
The translated message and the language used in <<MESSAGE>>, in a Python list format.
[translation, language]
"""


label_user_message = """

Incorporating your feedback, the prompt will now emphasize the importance of recognizing
entities related to players and teams, as well as include a broader perspective on what
constitutes a "research" inquiry through keywords and the understanding of
football-related entities. Let's refine the prompt to cover these aspects:

If there is any text prior to this prompt, consider it as <<HISTORY>>.

Based on the <<MESSAGE>> and <<HISTORY>> referred to as CONTENT, classify the inquiry
according to the following categories:
"info": This category is for CONTENT that seeks guidance on how to interact with the
chatbot. It covers questions like 'how can I use this chatbot' and 'what kind of
questions can I ask?'. These inquiries aim to understand the chatbot's functionalities
and are not related to football or fantasy football.
"research": This category includes CONTENT involving football and fantasy football,
particularly focusing on entities such as players and teams. It encompasses a wide range
of inquiries that might not explicitly use football terminology but are inherently about
football. For instance, questions comparing players ("who is better: Leao, Lautaro, or
Vlahovic?"), discussing player performances, strategies, and aspects of the game are
considered "research". Keywords that further identify a message as "research" include
assist, goal, midfielder, play, game, score, defense, attack, tactic, formation, league,
penalty, red card, etc.. Any message that discusses or mentions entities
related to football, whether it's about player comparisons, team performances, match
outcomes should be classified under this category.

"non_pertinent": This category is for CONTENT that does not fall into the 'info' or
'research' categories. It should be used for messages that are off-topic, unrelated to
the operational use of the chatbot, or to football and fantasy football inquiries.
This includes personal conversations or any questions outside the chatbot's designed
knowledge scope on football and user interaction guidance.

Content classification should focus on identifying the main intent and context of the
inquiry. If a message involves football entities or pertains to the football domain, even
abstractly or implicitly, it should be categorized as "research".


EXAMPLE:
<<MESSAGE>>
"How many goals has scored leao this year?"

<<OUTPUT>>
"research"

<<OUTPUT>>

<<MESSAGE>>
{message}

<<OUTPUT>>
Bear in mind, the output should contain only a single quotation mark.
"""

info_prompt = """
The user asked a <<MESSAGE>> asking infomation. Based on the message and the
points below, reply to his message.
Finally tell the user that he can ask you these questions:
- Which should be my starting 11 for this matchday?
- Which modulo should I use?
- Should I put a player or another one?
- You can ask me to modify your team after a trade of players/remove a player that was 
    erroneously added to your team.
- You can ask stats about players like how many goals has Leao scored this year?
- Does this player scores when the other team plays with this modulo?

<<MESSAGE>>
{message}
"""


queries_prompt = """
Given the question asked in <<MESSAGE>>, whose context can be understood within
<<HISTORY>>, translate the question into the <<OUTPUT>> pymongo query used to retrieve
the infomation. Bear in mind the <<OUTPUT>> must be a python executable code.
---
The self.data_manager.forecast_collection has the following schema and contains the
information on matchday that is going to be played.

---
The self.data_manager.players_collection has the following schema and contains for each
player their fantasy football scores.
Bear in mind, all the distinct bonus_malus are: {bonus_malus_names}'.
Bear in mind, add the distinct roles are: ['a', 'c', 'd', 'p'], a = attaccante,
c = centrocampista, d=difensore, p=portiere.

Player Collection Schema, 2 documents as example.
│
├── _id: 65f97dd9ab06d5603151f7dd
├── season: "2023-24"
├── team: "inter"
└── matches: Array[29]
    ├── [0]
    │   ├── match_day: 1
    │   ├── team_home: "inter"
    │   ├── team_away: "monza"
    │   ├── goal_team_home: 2
    │   ├── goal_team_away: 0
    │   ├── result: "win"
    │   └── players: Array[12]
    │       ├── [0]
    │       │   ├── name: "sommer"
    │       │   ├── role: "p"
    │       │   ├── adjective_performance: "Disoccupato"
    │       │   ├── grade: 6
    │       │   ├── fanta_grade: 6
    │       │   ├── bonus_malus: Array[0]
    │       │   └── description: "L'esordio in campionato è dei più semplici: qualche pallone smanacciato in uscita, nessuna parata di rilievo e una serata assolutamente tranquilla. Porta a casa il primo clean sheet stagionale."
    │       ├── [...]
    ├── [...]
    └── [28]
        ├── match_day: 29
        ├── team_home: "inter"
        ├── team_away: "napoli"
        ├── goal_team_home: 1
        ├── goal_team_away: 1
        ├── result: "tie"
        └── players: Array[N]
            ├── [0]
            │   ├── name: "sommer"
            │   ├── role: "p"
            │   ├── adjective_performance: "Incolpevole"
            │   ├── grade: 6
            │   ├── fanta_grade: 5
            │   ├── bonus_malus: Array[1]
            │   │   └── [0]
            │   │       ├── title: "Gol subiti"
            │   │       ├── value: "1"
            │   │       └── description: "Ordinaria amministrazione per lo svizzero, spettatore non pagante. Incolpevole sul gol subito."
            ├── [...]
            └── [N]
                ├── name: "thuram"
                ├── role: "a"
                ├── adjective_performance: "Pessimo"
                ├── grade: 5
                ├── fanta_grade: 5
                ├── bonus_malus: Array[0]
                └── description: "Probabilmente la peggior prestazione della sua stagione in Serie A. Tante scelte sbagliate e un paio di occasioni da gol dove poteva fare decisamente meglio."
---
<<HISTORY>>
{history}
---
EXAMPLES:
{examples}
---
<<MESSAGE>>
{message}


<<OUTPUT>>
Pymongo query, like "query" in the examples.
"""

suggestion_analysis_prompt = """
Here below the rules of italian Fantasy football:
---
Lo scopo è quello del guidare una fantasquadra, formata da veri calciatori delle squadre del campionato italiano alla conquista del fantascudetto di Lega.
L'esito di ogni partita si basa sulle reali prestazioni degli 11 calciatori che formano settimanalmente la fantasquadra.
Una lega è costituita da un numero di persone variabile tra 4 e 10: per quanto sia aritmeticamente possibile schierare fino a 20 squadre (quante quelle del campionato di Serie A), giocando in più di 10 persone aumenta il rischio per ciascun giocatore di non avere a disposizione un numero sufficiente di calciatori per schierare 11 titolari. Ciascun giocatore funge sia da presidente (in occasione dell'asta acquista i calciatori) sia da allenatore della propria fantasquadra.
La rosa di ciascuna fantasquadra è composta da 25 calciatori:
3 portieri,
8 difensori,
8 centrocampisti,
6 attaccanti.
Le singole gare di campionato sono giocate da una Fantasquadra formata da 11 titolari suddivisi nei rispettivi ruoli in base ai moduli.
Ufficialmente sono ammessi i moduli 4-4-2, 4-3-3, 3-3-4, 4-5-1, 5-3-2, 5-4-1, 4-2-4,[1]. Varianti al regolamento permettono l'impiego anche di schieramenti quali il 3-4-3, 3-5-2 [1].
Le fantasquadre si affrontano in una serie di partite il cui esito è determinato dalla somma dei voti assegnati in pagella dai quotidiani (prevalentemente La Gazzetta dello Sport e in misura minore il Corriere dello Sport), da siti internet come Sportmediaset e Gazzetta.it e dai punti "bonus" e "malus" dovuti a diverse variabili:
+3 punti per ogni gol segnato
+3 punti per ogni rigore parato (portiere)
+2 punti per ogni rigore segnato[2]
+1 punto per ogni assist effettuato
-0,5 punti per ogni ammonizione
+1 portiere imbattuto
-1 punto per ogni gol subito dal portiere
-1 punto per ogni espulsione
-2 punti per ogni autorete
-3 punti per un rigore sbagliato
La tabella di conversione in gol dei punteggi ottenuti dalla somma di voti e bonus/malus è storicamente la seguente:
Meno di 66 punti: 0 gol
Da 66 a 71.5 punti: 1 gol
Da 72 a 77.5 punti: 2 gol
Da 78 a 83.5 punti: 3 gol
Da 84 a 89.5 punti: 4 gol
Da 90 a 95.5 punti: 5 gol
Da 96 a 101.5 punti: 6 gol
E così via ogni 6 punti un gol
Tuttavia nel corso degli anni la Federazione Fantacalcio ha apportato modifiche alla tabella[3], portando nella stagione 2002/2003 la soglia per il 3° gol da 78 a 77 punti e assegnando i gol successivi ogni 4 punti (4 gol con 81 punti, 5 con 85 punti, 6 con 89 punti e così via)[3][4].
Nel momento in cui un giocatore nella formazione titolare non ha ricevuto voto, subentra il voto dei giocatori schierati in panchina. Nel caso in cui nessun giocatore tra i titolari o i panchinari riceva votazione subentrerà la riserva d'ufficio, il cui voto sarà considerato essere sempre un 4[5]; tale riserva si può usare solo una volta, se più giocatori non giocano gli altri non avranno punteggio e si giochera in inferiorità numerica.[6] Nel caso in cui un fantallenatore abbia solo giocatori subentrati a gara iniziata e non abbia titolari in un determinato ruolo, il voto viene conteggiato al giocatore subentrato.
Qualora dovesse esserci il rinvio di una o più partite il Regolamento Ufficiale del Fantacalcio prevede per gli scontri lo stand-by della gara, con successiva aggiunta di voti bonus e malus alla ripresa della gara. In caso di sospensione definitiva si attesta il 6 d'ufficio ai partecipanti e il 5,5 ai portieri. Alcune tipologie di fantacalcio, come quelle di Repubblica e Facebook, invece prevedono il 6 d'ufficio per tutti, compresi i portieri.
La classifica del campionato di Lega è stabilita per punteggio, con attribuzione di 3 punti per la partita vinta, 1 punto per la partita pareggiata e zero punti per la partita persa.
Il fantacampionato termina quando sono state giocate tutte le partite previste dal calendario. La squadra col maggior numero di punti è dichiarata "Campione di Lega".
La formazione dovrà essere comunicata a seconda dei regolamenti o entro l'inizio della prima partita in programma nella giornata o trenta minuti prima di tale orario. Nel caso in cui la formazione non venga inserita prima del termine stabilito, diverrà attiva la formazione schierata nella giornata precedente, senza alcuna penalizzazione.
---
What you need to do is based on there rule the <<MESSAGE>> and the <<STATISTICS>>, you should give an <<ANSWER>>
to allow the user to make the best possible decision.

<<MESSAGE>>
{message}

<<STATISTICS>>
{statistics}

<<ANSWER>>
"""

result_explanation_prompt = """
POV: You are an expert of fantasy-footaball analysis.
The user asked a <<QUESTION>>, and the <<QUERY_RESULTS>> is in MongoDB format.
You need to translate <<QUERY_RESULTS>> into human language.
If <<QUERY_RESULTS>> is [] or "query failed", tell the user that he must specify the whole
statistic within the message since this system strugges to memorize the subject of the
discussion. Also tell him that is the instruction was clear, the statistics couldn't be
retrieved.
If <<NON_IDENTIFIED_ENTITIES>> is not [], explain <<OUTPUT>> in that those entities within
the user message could not be matched with read data and therefore the answer does not
include them. Again, use the same the user used in <<QUESTION>> and <<HISTORY>>.

<<QUESTION>>
{question}

<<HISTORY>>
{history}

<<NON_IDENTIFIED_ENTITIES>>
{non_identified_entities}

<<QUERY_RESULTS>>
{query_results}

<<OUTPUT>>
Reply in {language}. Do not be verbose.
"""

correct_json_prompt = """
The following <<DATA STRUCTURE>> might contain syntax errors, like missing parenthesis.
the <<OUTPUT>> need to by the same data strucure CORRECTED of eventual errors.
return <<OUTPUT>>

<<DATA STRUCTURE>>
{data_structure}

<<OUTPUT>>
"""
