import json
import sys
from pathlib import Path


current_dir = Path(__file__).parent
src_dir = (current_dir.parent / "src").resolve()
sys.path.append(str(src_dir))


if __name__ == "__main__":
    from data_handler import SerieA_DatabaseManager

    query = "q16"
    with open(f"src/prompts/fantasy_footaball/rag_queries/{query}.json", mode="r") as f:

        q = json.load(f)
        question = q["question"]
        query = q["query"]

    data_handler = SerieA_DatabaseManager(scraper=None)
    print(f"question is: {question}")
    results = []
    for result in data_handler.players_collection.aggregate(query):
        results.append(result)
    print(f"result is {results}")
