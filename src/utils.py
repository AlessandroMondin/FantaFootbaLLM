import logging
import re
import traceback

from functools import wraps


def get_logger(logger_name: str, logger_level: int = logging.DEBUG) -> logging.Logger:
    # Configure logger
    logger = logging.getLogger(logger_name)  # Use the provided logger_name
    logger.setLevel(logger_level)  # Use the provided logger_level
    # Prevent the logger from propagating messages to ancestor loggers
    logger.propagate = False

    # Check if logger already has handlers
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logger_level)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


logger = get_logger(__file__)


def scrape_error_handler(func):
    """
    A decorator used for scraping functions. It logs errors if the scraper fails, including the line number.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Extract the current traceback
            tb = traceback.format_exc()
            # Log the exception with traceback
            if "url" in kwargs:
                logger.error(f"Error scraping {kwargs['url']}: {e}\nTraceback: {tb}")
            else:
                logger.error(f"Error in {func.__name__}: {e}\nTraceback: {tb}")
            # Optionally, re-raise the error if you want the exception to be thrown after logging
            # raise

    return wrapper


def validate_year_range(year_range):
    # Regex to match the pattern YYYY-YY
    pattern = r"(\d{4})-(\d{2})"
    match = re.match(pattern, year_range)
    # Does not match the pattern
    if not match:
        return False

    start_year, end_year_suffix = match.groups()
    end_year = start_year[:2] + end_year_suffix  # Construct the full end year

    # Check if the end year is start year + 1
    return int(end_year) == int(start_year) + 1
