import sys
from pathlib import Path

# Adjust the path to find the `src` directory
current_dir = Path(__file__).parent
src_dir = (current_dir.parent / "src").resolve()
sys.path.append(str(src_dir))

from data_handler import SerieADatabaseManager

if __name__ == "__main__":
    scraper = SerieADatabaseManager()
    scraper.scrape()
