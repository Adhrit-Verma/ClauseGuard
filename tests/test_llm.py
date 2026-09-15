from clauseguard.llm import parse_json_response


def test_parse_json_response_plain():
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_response_strips_markdown_fence():
    text = '```json\n{"a": 1}\n```'
    assert parse_json_response(text) == {"a": 1}


def test_parse_json_response_strips_bare_fence():
    text = '```\n{"a": 1}\n```'
    assert parse_json_response(text) == {"a": 1}
