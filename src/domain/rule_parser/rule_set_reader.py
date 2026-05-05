"""
Rule Set Reader Module.
Handles reading rule sets from various input sources (file path, binary, text).
Implements access levels and strong typing where appropriate.
"""

import io
from typing import Optional, Union, List
from src.domain.rule_parser.i_line_reader import ILineReader
from src.shared.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class RuleSetReader(ILineReader):
    """
    RuleSetReader reads rule sets from various input sources.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self):
        """
        Public Constructor: Initializes RuleSetReader.
        """
        # Private instance variable (initialized in __init__ to avoid shared state)
        self.__buffered_reader: Optional[io.BufferedReader] = None

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (File Loading)
    # -------------------------------------------------------------------------
    def create(self) -> None:
        """
        Public API: Creates/resets the reader.
        """
        self.__buffered_reader = None

    def set_file_with_path(self, file_path: str) -> None:
        """
        Public API: Sets file to read from file path.
        
        Args:
            file_path: Path to the rule file
            
        Raises:
            FileNotFoundError: If file does not exist
        """
        try:
            self.__buffered_reader = open(file_path, "rb")
            _logger.info(f"Reading a file by its path: {file_path}")
        except OSError as e:
            msg = f"Sorry, the file does not exist in the path: {file_path}"
            _logger.error(msg)
            raise FileNotFoundError(msg) from e

    def set_file_with_binary(self, file_binary: Union[bytes, List[bytes]]) -> None:
        """
        Public API: Sets file to read from binary data.
        
        Args:
            file_binary: Binary data as bytes or list of bytes
            
        Raises:
            ValueError: If file_binary is None or invalid
        """
        if file_binary is None:
            raise ValueError("file_binary cannot be None")
        try:
            if isinstance(file_binary, list):
                temp_byte = b''.join(file_binary)
            else:
                temp_byte = file_binary
            byte = io.BytesIO(temp_byte)
            self.__buffered_reader = io.BufferedReader(byte)
            _logger.info("Reading a file as a binary")
        except (TypeError, ValueError, OSError) as e:
            msg = "Sorry, the binary file does not exist"
            _logger.error(msg)
            raise ValueError(msg) from e

    def set_file_with_text(self, text: str) -> None:
        """
        Public API: Sets file to read from text string.
        
        Args:
            text: Text content of the rule file
            
        Raises:
            ValueError: If text is None or invalid
        """
        if text is None:
            raise ValueError("text cannot be None")
        try:
            with io.BytesIO(bytes(text, 'utf8')) as b:
                with io.BufferedReader(b) as file:
                    self.set_file_with_binary(file.readlines())
            _logger.info("Reading a file as text")
        except (OSError, TypeError, ValueError) as e:
            msg = "Sorry, there is no Input string"
            _logger.error(msg)
            raise ValueError(msg) from e

    def get_next_line(self) -> str:
        """
        Public API: Gets the next line from the input source.
        
        Returns:
            Next line as string
            
        Raises:
            RuntimeError: If no file has been loaded or no lines to read
        """
        if self.__buffered_reader is None:
            raise RuntimeError("No file has been loaded into RuleSetReader")
        
        line = ""
        try:
            line = self.__buffered_reader.readline().decode('utf8')
        except OSError as e:
            msg = "No lines to read"
            _logger.error(msg)
            raise RuntimeError(msg) from e
        
        if line == "":
            try:
                self.__buffered_reader.close()
            except OSError as e:
                msg = "No buffered reader to close"
                _logger.error(msg)
                raise RuntimeError(msg) from e
        
        return line

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _is_reader_open(self) -> bool:
        """
        Protected Helper: Checks if reader is open.
        
        Returns:
            True if reader is open, False otherwise
        """
        return self.__buffered_reader is not None and not self.__buffered_reader.closed

    def _close_reader(self) -> None:
        """
        Protected Helper: Closes the buffered reader.
        """
        if self.__buffered_reader is not None:
            try:
                self.__buffered_reader.close()
            except OSError as e:
                _logger.error(f"Error closing reader: {e}")
            finally:
                self.__buffered_reader = None
