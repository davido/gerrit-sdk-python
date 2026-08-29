"""Unit tests for gerrit_xssi.strip -- the )]}' guard removal that keeps Gerrit's XSSI
prefix out of json.loads. GerritApiClient calls it before deserialization."""
from gerrit_xssi import strip


def test_strips_the_guard():
    assert strip(")]}'\n{\"id\": 1}") == "{\"id\": 1}"


def test_passes_through_bodies_without_the_guard():
    assert strip("{\"id\": 1}") == "{\"id\": 1}"
    assert strip("plain text") == "plain text"
    assert strip("") == ""
