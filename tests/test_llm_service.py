"""llm_service.extract_json_object — direct regression coverage for a
real bug found during live testing with gemini-3.5-flash: JSON mode
sometimes appends redundant extra closing braces after a complete,
valid object (observed live, not a theoretical concern — e.g.
'{"a": 1}\\n}\\n}\\n}'). The old "first { to last }" greedy regex
swallowed those as part of the "extracted" JSON, breaking json.loads
with "Extra data" errors. Fixed by decoding exactly one JSON value from
the first '{' and ignoring whatever follows.
"""
import json

import pytest

from app.services import llm_service


def test_extracts_clean_json_unchanged():
    assert json.loads(llm_service.extract_json_object('{"a": 1}')) == {"a": 1}


def test_extracts_json_with_one_trailing_brace():
    """The exact failure mode observed live with gemini-3.5-flash."""
    assert json.loads(llm_service.extract_json_object('{"a": 1}\n}')) == {"a": 1}


def test_extracts_json_with_many_trailing_braces():
    assert json.loads(llm_service.extract_json_object('{"a": 1}\n}\n}\n}\n}')) == {"a": 1}


def test_extracts_json_wrapped_in_markdown_fences():
    assert json.loads(llm_service.extract_json_object('```json\n{"a": 1}\n```')) == {"a": 1}


def test_extracts_json_with_leading_and_trailing_commentary():
    text = 'Sure, here is the JSON you asked for: {"a": 1} — hope that helps!'
    assert json.loads(llm_service.extract_json_object(text)) == {"a": 1}


def test_extracts_first_of_multiple_json_objects():
    """If the model emits more than one JSON-looking blob, take the
    first complete one rather than trying to merge or picking the last."""
    text = '{"a": 1} and also maybe {"a": 2}'
    assert json.loads(llm_service.extract_json_object(text)) == {"a": 1}


def test_preserves_nested_objects_and_arrays():
    text = '{"a": {"b": [1, 2, 3]}, "c": "text with { and } inside a string"}\n}'
    result = json.loads(llm_service.extract_json_object(text))
    assert result == {"a": {"b": [1, 2, 3]}, "c": "text with { and } inside a string"}


def test_raises_on_no_json_object_present():
    with pytest.raises(ValueError):
        llm_service.extract_json_object("no json here at all")


def test_raises_on_malformed_json():
    with pytest.raises(ValueError):
        llm_service.extract_json_object('{"a": this is not valid}')
