import sys
from pathlib import Path

current_dir = Path(__file__).parent
src_dir = (current_dir.parent / "src").resolve()
sys.path.append(str(src_dir))

from llm_interface import LLMInterface
from data_handler import SerieA_DatabaseManager
from scrapers.serie_a_scraper import SerieA_Scraper


if __name__ == "__main__":
    import yaml

    # Load the YAML file
    with open("src/bonus_malus.yaml", "r") as file:
        bonus_malus_table = yaml.safe_load(file)["bonus_malus_table"]
    scraper = SerieA_Scraper(bonus_malus_table=bonus_malus_table)
    data_manager = SerieA_DatabaseManager(scraper=scraper)
    smart_llm = LLMInterface(data_manager=data_manager)

    out = smart_llm.chat_debug("In che squadra gioca leao?")
    c = 1
