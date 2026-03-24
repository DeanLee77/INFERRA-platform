import re
from project.constants import TokenizerMatcherConstant
from project.tokens import Token
from project.loggers import Logger


logging: Logger = Logger.get_logger(__name__)


class Tokenizer:

    # the order of Pattern in the array of 'matchPatterns' is extremely important because some patterns won't work
    # if other patterns are invoked earlier than them especially 'I' pattern.
    # 'I' pattern must come before 'U' pattern, 'Url' pattern must come before 'L' pattern within current patterns.

    match_patterns = tuple(TokenizerMatcherConstant.get_all_matcher())
    token_type = ("S", "R", "I", "C", "Q", "Url", "Id", "Ha", "Da", "De", "O", "No", "Pa", "Se", "Fu", "U", "M", "L")



    @classmethod
    def get_tokens(cls, text: str) -> Token:
        if text is None:
            raise ValueError("Tokenizer input text cannot be None")

        token_string_list = []
        token_list = []
        token_string = ''
        original_text = text
        
        while len(text) > 0:
            matched = False
            for i in range(len(cls.match_patterns)):
                try:
                    match = re.match(cls.match_patterns[i], text)
                    if match:
                        group = match.group(0)
                        
                        if cls.token_type[i] != 'S':
                            token_string_list.append(cls.token_type[i])
                            token_list.append(group.strip())
                            token_string += str(cls.token_type[i])
                        
                        text = text[len(group):].strip()
                        matched = True
                        break
                except re.error as e:
                    logging.exception("Regex error in pattern %s: %s", cls.token_type[i], e)
                    continue

            if not matched:
                logging.warning("No token match found for remaining text '%s' from original input '%s'", text, original_text)
                token_string = "WARNING"
                break

        tokens = Token(token_list, token_string_list, token_string)
        return tokens

