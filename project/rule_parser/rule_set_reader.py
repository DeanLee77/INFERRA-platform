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
        except IOError as e:
            msg = "Sorry, the file does not exist in the path: " + file_path
            logging.error(msg)

    def set_file_with_binary(self, file_binary) -> None:
        try:
            temp_byte = b''.join(file_binary)
            byte = io.BytesIO(temp_byte)
            self.__bufferedReader = io.BufferedReader(byte)
            logging.info("reading a file as a binary")
        except IOError as e:
            msg = "Sorry, the binary file does not exit"
            logging.error(msg)

    def set_file_with_text(self, text) -> None:
        try:
            with io.BytesIO(bytes(text, 'utf8')) as b:
                with io.BufferedReader(b) as file:
                    self.set_file_with_binary(file.readlines())
                    logging.info("reading a file as text")
        except IOError as e:
            msg = "Sorry, there is no Input string"
            logging.error(msg)

    def get_next_line(self) -> str:
        line = ""
        try:
            line = self.__bufferedReader.readline().decode('utf8')
        except IOError as e:
            msg = "No lines to read"
            logging.error(msg)

        if line == "":
            try:
                self.__bufferedReader.close()
            except IOError as e:
                msg = "No buffered reader to close"
                logging.error(msg)

        return line

