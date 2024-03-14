import logging
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
    A decorator used for scraping functions. It logs errors if the scraper fails.
    """

    # for debugging purposes
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log the exception
            if "url" in kwargs:
                logger.error(f"Error scraping {kwargs['url']}: {e}")
            else:
                logger.error(f"Error in {func.__name__}: {e}")
            # Optionally, re-raise the error if you want the exception to be thrown after logging
            # raise

    return wrapper


if __name__ == "__main__":

    @scrape_error_handler
    def ciao():
        return "str" + 1

    ciao()
