from langchain.prompts import PromptTemplate

style_concise = "informal and concise. Do not be verbose."
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

label_user_message = """
The question of <<MESSAGE>> and given very last messages of the <<HISTORY>> are referred below as CONTEXT.
Where <<HISTORY>> is the described in the text preceeding this prompt.
Based on the rule described here below you need to classify the message.
- "suggestion": if the CONTENT asks a question like "what is the best
 modulo I can use next match with which players? Which team should I use for my next match?"
- "research": if the CONTENT asks a question like: What is the average score of this player in the last 3 matches he played?
 How many goals has this player scoared? How many yellow card has this player taken? How many goals has this team scored in the last 5 matches?
How many goals has this goalkeeper received in the last 5 matches? Does this player score more when the other team uses which module?
- "team_management": if the CONTENT asks a question like: I have traded "player 1" and "player 2" for "player 3" and "player 4". Can you show me
    my players? Can you delete "player a" from my team?
- "info": if CONTENT refards information on how to use the chatbot, which questions to ask etc.
- "unknown": if the CONTENT does not concern none of the categories listed above.

<<MESSAGE>>
{message}

<<OUTPUT>>
Return either "suggestion", "research", "info", "team_management", "unknown"
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
Given the question asked in <<MESSAGE>>, which can be contextualised with <<HISTORY>>, you need to translate the question into a
pymongo query used to retrieve the infomation asked. You should return in <<OUTPUT>> the query. Bear in mind the <<OUTPUT>>
must be a python executable code, so just return the query withoud any other words so that eval(<<OUTPUT>>) executes the query.
The pymongo contains 3 collections: "self.data_manager.forecast_collection", "self.data_manager.players_collection", "self.data_manager.championship_collection".
---
The self.data_manager.forecast_collection has the following schema and contains the information on matchday that is going to be played.
Collection
│
├── _id: 65e9dbed6b4ba469cc4aa8b8
├── current_match_day: 27
└── competitions: Array[10]
    └── [0]
        ├── team_home: "napoli"
        ├── team_away: "torino"
        ├── team_home_forecast
        │   ├── team_formation: "4-3-3"
        │   ├── start_11: Array[11]
        │   │   ├── [0] - {{ player_name: "meret", player_role: "p", percentage_of_playing: 90 }}
        │   │   ├── [...]
        │   │   └── [10] - {{ ... }}
        │   └── reserves: Array[11]
        │       ├── [0] - {{ player_name: "gollini", player_role: "p", percentage_of_playing: 5 }}
        │       ├── [...]
        │       └── [10] - {{ ... }}
        └── team_away_forecast
            ├── team_formation: "3-4-1-2"
            ├── start_11: Array[11]
            │   ├── [0] - {{ ... }}
            │   ├── [...]
            │   └── [10] - {{ ... }}
            └── reserves: Array[8]
                ├── [0] - {{ ... }}
                └── [7] - {{ ... }}
---
The self.data_manager.players_collection has the following schema and contains for each player their
fantasy football scores. 
Bear in mind, all the distinct bonus_malus are: 'Ammonizione', 'Assist', 'Autorete', 'Espulsione', 'Gol segnati', 'Gol subiti', 'Rigori parati', 'Rigori sbagliati', 'Rigori segnati'.
Bear in mind, add the disticct roles are: ['a', 'c', 'd', 'p'], a = attaccante, c = centrocampista, d=difensore, p=portiere.
Here an example of the the document present within the self.players_collection for the goal-keeper 'sommer'

Player Document
│
├── _id: 65eed774d007ec44ea5c9e07
├── name: "rafael-leao"
├── role: "a"
├── team: "milan"
└── matchStats: Array[23]
    ├── [0] - {{ ... }}
    ├── [1]
    │   ├── matchday: 2
    │   ├── adjective_performance: "Determinante"
    │   ├── grade: 7
    │   ├── bonus_malus: Array[1]
    │   │   └── [0]
    │   │       ├── title: "Assist"
    │   │       ├── value: "1"
    │   │       ├── grade_with_bm: 8
    │   │       └── description: "Una cosa buona, una no, una buona, una no. Salta spesso Schuurs, ma po…"
    ├── [2]
    │   ├── matchday: 3
    │   ├── adjective_performance: "Pornografico"
    │   ├── grade: 7.5
    │   ├── bonus_malus: Array[1]
    │   │   └── [0]
    │   │       ├── title: "Gol segnati"
    │   │       ├── value: "1"
    │   │       ├── grade_with_bm: 10.5
    │   │       └── description: "L'ennesima serata da superstar. Quando punta l'avversario sfreccia in …"
    ├── [...]
    └── [22] - {{ ... }}

---
The self.data_manager.championship_collection contains all the players of the user:
An example of the document listing the players of the user:
User Document
│
├── _id: 65edc8b23ce059ef45753cee
└── user_players: Array[26]
    ├── [0]: "calhanoglu"
    ├── [1]: "celik"
    ├── [2]: "ostigard"
    ├── [3]: "djuric"
    ├── [4]: "swiderski"
    ├── [5]: "contini"
    ├── [6]: "zielinski"
    ├── [7]: "tomori"
    ├── [8]: "calafiori"
    ├── [9]: "gatti"
    ├── [10]: "baschirotto"
    ├── [11]: "kayode"
    ├── [12]: "politano"
    ├── [13]: "el-shaarawy"
    ├── [14]: "jankto"
    ├── [15]: "zambo-anguissa"
    ├── [16]: "musah

    
EXAMPLES:
---
1)
<<MESSAGE>>
How many goals has leao scored this year?

<<HISTORY>>

<<OUTPUT>>
self.data_manager.player_collection.aggregate([
    {{"$match": {{"name": "rafael-leao"}}}},
    {{"$unwind": "$matchStats"}},
    {{"$unwind": "$matchStats.bonus_malus"}},
    {{"$match": {{"matchStats.bonus_malus.title": "Gol segnati"}}}},
    {{"$project": {{
        "name": 1,
        "role": 1,
        "team": 1,
        "goals": {{
            "$toInt": "$matchStats.bonus_malus.value"
        }}
    }},
    {{"$group": {{
        "_id": {{
            "name": "$name",
            "role": "$role",
            "team": "$team"
        }},
        "totalGoals": {{"$sum": "$goals"}}
    }}
])

2)
<<MESSAGE>>
Who is the player who has received the most yellow cards and who has received the least?

<<HISTORY>>

<<OUTPUT>>
self.data_manager.players_collection.aggregate([
    {{"$unwind": "$matchStats"}},
    {{"$unwind": "$matchStats.bonus_malus"}},
    {{"$match": {{"matchStats.bonus_malus.title": "Ammonizione"}}, 
    {{"$group": {{
        "_id": "$name",
        "totalYellowCards": {{"$sum": {{"$toInt": "$matchStats.bonus_malus.value"}}
    }},
    {{
        "$facet": {{
            "mostYellowCards": [
                {{"$sort": {{"totalYellowCards": -1}}}},
                {{"$limit": 1}}
            ],
            "fewestYellowCards": [
                {{"$sort": {{"totalYellowCards": 1}}}},
                {{"$limit": 1}}
            ]
        }}
    }}
])

3)
<<MESSAGE>>
Was Calhanoglu's average higher in the first 10 games or in the last 5?

<<HISTORY>>

<<OUTPUT>>
self.data_manager.players_collection.aggregate([
    {{"$match": {{"name": "calhanoglu"}}}},
    {{"$unwind": "$matchStats"}},
    {{
        "$group": {{
            "_id": "$name",
            "averageGradeFirst10": {{
                "$avg": {{
                    "$cond": [
                        {{"$lte": ["$matchStats.matchday", 10]}},
                        "$matchStats.grade",
                        "$$REMOVE",
                    ]
                }}
            }},
            "averageGradeLast5": {{
                "$avg": {{
                    "$cond": [
                        {{"$gte": ["$matchStats.matchday", 23]}},
                        "$matchStats.grade",
                        "$$REMOVE",
                    ]
                }}
            }},
        }}
    }},
    {{"$project": {{"_id": 0, "averageGradeFirst10": 1, "averageGradeLast5": 1}}}},
])

4)
<<MESSAGE>>
Ehi, how many goals per game has giroud scored this year??

<<HISTORY>>

<<OUTPUT>>
self.data_manager.players_collection.aggregate([
    {{ "$match": {{ "name": "giroud" }} }},
    {{ "$addFields": {{ "numberOfGames": {{ "$size": "$matchStats" }} }} }},  # Assuming each document in matchStats represents a game
    {{ "$unwind": "$matchStats" }},
    {{ "$unwind": "$matchStats.bonus_malus" }},
    {{ "$match": {{ "matchStats.bonus_malus.title": "Gol segnati" }} }},
    {{ "$group": {{
        "_id": "$name",
        "totalGoals": {{ "$sum": {{ "$toInt": "$matchStats.bonus_malus.value" }} }},
        "numberOfGames": {{ "$first": "$numberOfGames" }}
    }} }},
    {{ "$project": {{
        "_id": 0,
        "name": "$_id",
        "totalGoals": 1,
        "goalsPerGame": {{ "$divide": ["$totalGoals", "$numberOfGames"] }}
    }} }}
])


---

<<MESSAGE>>
{message}

<<HISTORY>>
{history}

<<OUTPUT>>
Pymongo query to reply what is asked in message.
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
