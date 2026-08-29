"""Gerrit XSSI-aware API client.

Every Gerrit JSON body starts with ``)]}'`` on its own line, to defeat cross-site
script inclusion. That prefix is not valid JSON and is not expressible in OpenAPI, so
the generated client cannot know about it. :class:`GerritApiClient` subclasses the
generated ``ApiClient`` and strips the guard before deserialization -- no edits to
generated code, so it survives regeneration (this package lives outside the generated
``gerrit_client`` package, like the Go SDK's separate ``gerritxssi`` package).
"""
from typing import Optional

from gerrit_client.api_client import ApiClient

_GUARD = ")]}'\n"


def strip(response_text: str) -> str:
    """Strip Gerrit's leading ``)]}'`` XSSI guard when present; a no-op otherwise, so it
    is safe to apply to every response (text/plain and binary bodies don't start with
    it)."""
    if isinstance(response_text, str) and response_text.startswith(_GUARD):
        return response_text[len(_GUARD):]
    return response_text


class GerritApiClient(ApiClient):
    """An :class:`ApiClient` that strips Gerrit's XSSI guard before JSON deserialization.

    ``ApiClient.response_deserialize`` routes every JSON body through ``deserialize``;
    overriding it here is the single injection point (Python's generated client, unlike
    Rust's blocking reqwest, exposes one).
    """

    def deserialize(self, response_text: str, response_type: str, content_type: Optional[str]):
        return super().deserialize(strip(response_text), response_type, content_type)
