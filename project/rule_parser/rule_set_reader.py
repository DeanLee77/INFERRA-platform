import io
from project.rule_parser import ILineReader
from project.loggers import Logger

logging: Logger = Logger.get_logger(__name__)


class RuleSetReader(ILineReader):

    __bufferedReader = None
    def create(self):
        self.__bufferedReader = None

    def set_file_with_path(self, file_path) -> None:
        try:
            self.__bufferedReader = open(file_path, "rb")
            logging.info("reading a file by its path")
        except OSError as e:
            msg = "Sorry, the file does not exist in the path: " + file_path
            logging.error(msg)
            raise FileNotFoundError(msg) from e

    def set_file_with_binary(self, file_binary) -> None:
        if file_binary is None:
            raise ValueError("file_binary cannot be None")
        try:
            temp_byte = b''.join(file_binary)
            byte = io.BytesIO(temp_byte)
            self.__bufferedReader = io.BufferedReader(byte)
            logging.info("reading a file as a binary")
        except (TypeError, ValueError, OSError) as e:
            msg = "Sorry, the binary file does not exit"
            logging.error(msg)
            raise ValueError(msg) from e

    def set_file_with_text(self, text) -> None:
        if text is None:
            raise ValueError("text cannot be None")
        try:
            with io.BytesIO(bytes(text, 'utf8')) as b:
                with io.BufferedReader(b) as file:
                    self.set_file_with_binary(file.readlines())
                    logging.info("reading a file as text")
        except (OSError, TypeError, ValueError) as e:
            msg = "Sorry, there is no Input string"
            logging.error(msg)
            raise ValueError(msg) from e

    def get_next_line(self) -> str:
        if self.__bufferedReader is None:
            raise RuntimeError("No file has been loaded into RuleSetReader")

        line = ""
        try:
            line = self.__bufferedReader.readline().decode('utf8')
        except OSError as e:
            msg = "No lines to read"
            logging.error(msg)
            raise RuntimeError(msg) from e

        if line == "":
            try:
                self.__bufferedReader.close()
            except OSError as e:
                msg = "No buffered reader to close"
                logging.error(msg)
                raise RuntimeError(msg) from e

        return line

