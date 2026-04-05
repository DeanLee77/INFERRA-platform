"""
Logger Module.
Provides centralized logging functionality for PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

import logging
import sys
from datetime import date
from logging.handlers import TimedRotatingFileHandler
from typing import Optional


class Logger:
    """
    Logger provides centralized logging with console and file handlers.
    
    Access Levels:
    - Public: Static API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Class Variables (Name Mangling)
    # -------------------------------------------------------------------------
    __FORMATTER: logging.Formatter = logging.Formatter(
        '%(asctime)s :: %(name)s :: [%(levelname)s] :: %(funcName)s :: %(lineno)d :: %(message)s'
    )
    __today: date = date.today()
    __d4: str = __today.strftime("%b-%d-%Y")
    __LOG_FILE: str = f"Nadia-logging/Nadia-Engine {__d4}.log"

    # -------------------------------------------------------------------------
    # Private Access Level: Static Helpers (Double Underscore)
    # -------------------------------------------------------------------------
    @staticmethod
    def __get_console_handler() -> logging.StreamHandler:
        """
        Private Helper: Creates console logging handler.
        
        Returns:
            Configured StreamHandler for console output
        """
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(Logger.__FORMATTER)
        return console_handler

    @staticmethod
    def __get_file_handler() -> TimedRotatingFileHandler:
        """
        Private Helper: Creates file logging handler with rotation.
        
        Returns:
            Configured TimedRotatingFileHandler for file output
        """
        file_handler = TimedRotatingFileHandler(Logger.__LOG_FILE, 'midnight')
        file_handler.setFormatter(Logger.__FORMATTER)
        return file_handler

    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_logger(logger_name: str) -> logging.Logger:
        """
        Public API: Gets or creates a logger instance.
        
        Args:
            logger_name: Name for the logger instance
            
        Returns:
            Configured logging.Logger instance
        """
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers to avoid duplicates
        if not logger.handlers:
            logger.addHandler(Logger.__get_console_handler())
            logger.addHandler(Logger.__get_file_handler())
        
        # Prevent error propagation to parent loggers
        logger.propagate = False
        return logger