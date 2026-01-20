from nodes.node import Node
from nodes.value_conclusion_line import ValueConclusionLine
from tokens.tokenizer import Tokenizer


def test_init():
    text_string = 'person\'s drinking habit IS \"social drinker\"'
    tokens = Tokenizer.get_tokens(text_string)
    nodes_list = list()
    result = True
    Node.reset()
    for index in range(100):
        node = ValueConclusionLine(text_string, tokens)
        nodes_list.append(node)

    for index in range(100):
        id = nodes_list[index].get_node_id()
        print("id: " + str(id))
        print("index: " + str(index))
        if id is not index:
            result = False

    assert result is True
