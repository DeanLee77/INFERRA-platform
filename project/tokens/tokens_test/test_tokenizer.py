from typing import Optional
from project.tokens import Tokenizer
from project.tokens import Token
import os
import re


def test_get_tokenizer():
    with open(os.path.dirname(__file__) + '/tokenizer_testing.txt') as f:
        lines = f.readlines()
        line_tracking = 0
        text_string = ''
        tk: Optional[Token]
        expected_result = True

        for line in lines:
            line = line.strip();
            if line != '' and not re.match(r"^/.*", line):
                if line_tracking == 0:
                    text_string = line
                    tk = Tokenizer.get_tokens(line)
                    line_tracking += 1
                elif line_tracking == 1:
                    if tk.get_tokens_string() != line:
                        expected_result = False
                    else:
                        line_tracking = 0

        assert expected_result is True
