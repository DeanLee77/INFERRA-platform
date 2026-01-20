import logging
import string
import sys
from datetime import date
from logging.handlers import TimedRotatingFileHandler


class Logger:
    FORMATTER = logging.Formatter(
        '%(asctime)s :: %(name)s :: [%(levelname)s]  :: %(funcName)s :: %(lineno)d :: %(message)s'
    )

    today = date.today()
    d4 = today.strftime("%b-%d-%Y")
    LOG_FILE = "Nadia-logging/Nadia-Engine "+d4+".log"

    @staticmethod
    def __get_console_handler():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(Logger.FORMATTER)
        return console_handler

    @staticmethod
    def __get_file_handler() -> TimedRotatingFileHandler:
        TimedRotatingFileHandler
        file_handler = TimedRotatingFileHandler(Logger.LOG_FILE, 'midnight')
        file_handler.setFormatter(Logger.FORMATTER)
        return file_handler
    
    @staticmethod
    def get_logger(logger_name: string) -> logging:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)  # better to have too much log than not enough
        logger.addHandler(Logger.__get_console_handler())
        logger.addHandler(Logger.__get_file_handler())
        # with this pattern, it's rarely necessary to propagate the error up to parent
        logger.propagate = False
        return logger
